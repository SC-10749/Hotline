from __future__ import annotations

import json
import mimetypes
import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .agents import AgentEngine, TaskManager
from .config import settings
from .documents import DocumentError, DocumentService
from .models import DocumentRecord, FileInfo, now_iso
from .object_store import ObjectStorage
from .parser import parse_file
from .ppt import generate_ppt
from .skill_center import Catalog
from .skills import SkillError, SkillRegistry
from .storage import Storage
from .vector_store import PgVectorStore

settings.ensure_dirs()
storage = Storage(settings)
object_store = ObjectStorage(settings)
tasks = TaskManager(settings)
vector_store = PgVectorStore(settings)
skills = SkillRegistry(settings)
documents = DocumentService(settings, storage, object_store, vector_store)
engine = AgentEngine(settings, storage, tasks, vector_store, skills, documents)

STATIC_DIR = Path(__file__).parent.parent / "static"
CONSOLE_DIR = STATIC_DIR / "console"
# Fused single-service mode: FastAPI serves the built Vue app from frontend/dist,
# so the page and the API share one origin and one port.
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"
# Hot-deploy probe: the page polls /__build and reloads itself when the backend
# restarts (boot id changes) or `vite build --watch` rewrites dist (build id).
SERVER_BOOT_ID = uuid4().hex
LIVE_RELOAD_SNIPPET = (
    "<script>(function(){var last=null;function check(){fetch('/__build',{cache:'no-store'})"
    ".then(function(r){return r.json()}).then(function(payload){var d=payload.data||payload;"
    "var id=d.boot+'|'+d.build;if(last!==null&&id!==last){location.reload();return}last=id;})"
    ".catch(function(){})}check();setInterval(check,1200)})();</script>"
)


def dist_fingerprint() -> str:
    try:
        return str((FRONTEND_DIST / "index.html").stat().st_mtime_ns)
    except OSError:
        return ""
CONSOLE_ACTIONS = {'save', 'bind', 'eval_case', 'eval_cases', 'evaluate', 'evolve', 'auto_evolve',
                   'run_case', 'judge', 'promote', 'rollback', 'metric', 'metrics'}


@asynccontextmanager
async def lifespan(_: FastAPI):
    documents.start_sweeper()
    yield
    documents.stop_sweeper()


app = FastAPI(title="Dodo Agent", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def ok(data=None, message="操作成功", code=200):
    return {"code": code, "message": message, "data": data}


def fail(message: str, code: int = 400):
    return JSONResponse(ok(None, message, code), status_code=code)


@app.get("/health")
def health():
    return {"status": "UP", "service": "dodo-agent", "version": "fastapi"}


@app.get("/file/list")
def file_list():
    files = [item.to_dict() for item in storage.list_files()]
    return ok({"count": len(files), "files": files})


@app.get("/file/info/{file_id}")
def file_info(file_id: str):
    info = storage.get_file(file_id)
    if not info:
        return fail("文件不存在", 404)
    return ok(info.to_dict())


@app.get("/file/content/{file_id}")
def file_content(file_id: str):
    info = storage.get_file(file_id)
    if not info:
        return fail("文件不存在", 404)
    return ok({"content": info.extractedText, "length": len(info.extractedText)})


@app.get("/file/exists/{file_id}")
def file_exists(file_id: str):
    return ok(storage.get_file(file_id) is not None)


@app.post("/file/upload")
async def file_upload(file: UploadFile = File(...)):
    content = await file.read()
    if not content or len(content) > settings.max_file_size:
        return fail("文件为空或超过大小限制")
    name = Path(file.filename or "upload.bin").name
    file_id = uuid4().hex
    suffix = Path(name).suffix.lower()
    object_name = f"file-{file_id.replace('-', '')}.{suffix.lstrip('.') or 'bin'}"
    minio_path = object_store.upload_bytes(
        content,
        object_name,
        file.content_type or "application/octet-stream",
    )
    target = settings.upload_dir / f"{file_id}{suffix}"
    if settings.file_storage_backend == "local":
        target = settings.upload_dir / object_name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    full, truncated = parse_file(target, settings.max_text_length)
    info = FileInfo(
        fileId=file_id,
        fileName=name,
        fileType=target.suffix.lower().lstrip("."),
        fileSize=len(content),
        minioPath=minio_path,
        extractedText=truncated,
        createdAt=now_iso(),
    )
    info.embed = 1 if (
        len(full) >= settings.large_file_threshold
        and settings.vector_enabled
        and settings.embedding_api_key
    ) else 0
    if info.embed:
        chunks = [full[index:index + 500] for index in range(0, len(full), 450)]
        vector_store.add_chunks(file_id, chunks)
    storage.save_file(info)
    return ok(info.to_dict())


@app.delete("/file/{file_id}")
def file_delete(file_id: str):
    info = storage.get_file(file_id)
    if not info:
        return fail("文件不存在", 404)
    object_store.delete_url(info.minioPath)
    storage.delete_file(file_id)
    return ok("文件删除成功")


@app.post("/document/upload")
async def document_upload(file: UploadFile = File(...)):
    content = await file.read()
    if not content or len(content) > settings.max_file_size:
        return fail("文件为空或超过大小限制")
    name = Path(file.filename or "document.bin").name
    record = documents.upload(name, content)
    if record.status == "FAILED":
        return fail(record.errorMsg or "文档转换失败")
    return ok(record.to_dict())


@app.get("/document/list")
def document_list():
    items = [item.to_dict() for item in storage.list_documents()]
    return ok({"count": len(items), "documents": items})


@app.post("/document/compensate")
def document_compensate(limit: int = Query(20, ge=1, le=200)):
    return ok(documents.compensate(limit))


@app.get("/document/{doc_id}")
def document_info(doc_id: str):
    record = storage.get_document(doc_id)
    if not record:
        return fail("文档不存在", 404)
    return ok(record.to_dict())


@app.post("/document/{doc_id}/vectorize")
def document_vectorize(doc_id: str):
    record = storage.get_document(doc_id)
    if not record:
        return fail("文档不存在", 404)
    result = documents.vectorize(doc_id)
    if result.get("error"):
        return fail(f"无法向量化：{result['error']}")
    return ok(result)


@app.get("/document/{doc_id}/preview")
def document_preview(doc_id: str):
    result = documents.preview(doc_id)
    if result.get("error"):
        return fail(f"无法预览：{result['error']}", 404 if result["error"] == "文档不存在" else 400)
    return ok(result)


@app.get("/document/{doc_id}/versions")
def document_versions(doc_id: str):
    if not storage.get_document(doc_id):
        return fail("文档不存在", 404)
    return ok(storage.list_document_versions(doc_id))


@app.delete("/document/{doc_id}")
def document_delete(doc_id: str):
    if not documents.remove(doc_id):
        return fail("文档不存在", 404)
    return ok("文档删除成功")


@app.get("/skill/list")
def skill_list():
    items = [item.to_dict() for item in skills.list()]
    return ok({"count": len(items), "skills": items})


@app.post("/skill/upload")
async def skill_upload(file: UploadFile = File(...), entry: str = Form("")):
    content = await file.read()
    if not content or len(content) > settings.max_file_size:
        return fail("技能包为空或超过大小限制")
    try:
        skill = skills.install(content, Path(file.filename or "skill.zip").name, entry or None)
    except SkillError as exc:
        return JSONResponse({"code": 400, "message": str(exc), "data": {"entries": exc.entries}},
                            status_code=400)
    return ok(skill.to_dict(), "技能安装成功")


@app.post("/skill/{skill_id}/toggle")
def skill_toggle(skill_id: str, enabled: bool = Query(...)):
    skill = skills.set_enabled(skill_id, enabled)
    if not skill:
        return fail("技能不存在", 404)
    return ok(skill.to_dict())


@app.delete("/skill/{skill_id}")
def skill_delete(skill_id: str):
    if not skills.delete(skill_id):
        return fail("技能不存在", 404)
    return ok("技能删除成功")


def run_catalog(action: str, args: dict):
    """Open the skill catalog for one call; safe for the thread-pool endpoints."""
    catalog = Catalog(settings.skill_catalog_db)
    try:
        return catalog.call(action, args)
    finally:
        catalog.db.close()


@app.get("/console")
def console_index():
    index = CONSOLE_DIR / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="技能控制台页面不存在")
    return FileResponse(index)


@app.get("/console/{asset}")
def console_asset(asset: str):
    if Path(asset).name != asset or asset not in {"console.js", "console.css"}:
        raise HTTPException(status_code=404, detail="资源不存在")
    target = CONSOLE_DIR / asset
    if not target.is_file():
        raise HTTPException(status_code=404, detail="资源不存在")
    media = "text/javascript" if asset.endswith(".js") else "text/css"
    return FileResponse(target, media_type=f"{media}; charset=utf-8")


@app.get("/console/api/config")
def console_config():
    return ok({"project": settings.skill_project})


@app.get("/console/api/skills")
def console_skills(project: str | None = None):
    try:
        if project:
            return ok(run_catalog('runtime', {'project': project}))
        return ok(run_catalog('list', {}))
    except (ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        return fail(str(exc))


@app.post("/console/api/skills")
async def console_skills_action(request: Request):
    try:
        body = await request.json()
    except Exception:
        return fail("请求体必须是 JSON")
    action = body.get('action')
    if action not in CONSOLE_ACTIONS:
        return fail('不支持的技能操作')
    args = body.get('args') or {}
    if not isinstance(args, dict):
        return fail('args 必须是对象')
    try:
        return ok(run_catalog(action, args))
    except (ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        return fail(str(exc))


@app.get("/console/api/skill-evolution")
def console_skill_evolution(view: str = 'all'):
    actions = {'cases': 'eval_cases', 'metrics': 'metrics', 'runs': 'evolution_runs', 'rollouts': 'rollouts'}
    try:
        action = actions.get(view)
        if action:
            return ok(run_catalog(action, {}))
        if view != 'all':
            return fail('不支持的自进化视图')
        payload = {}
        for key, catalog_action in actions.items():
            payload[key] = run_catalog(catalog_action, {})
        return ok(payload)
    except (ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        return fail(str(exc), 502)


@app.get("/session/list")
def session_list(
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=1000),
):
    rows, total = storage.session_list((pageNum - 1) * pageSize, pageSize)
    records = [
        {
            "conversationId": row.conversationId,
            "question": row.question,
            "agentType": row.agentType,
            "fileid": row.fileid,
            "createTime": row.createTime,
        }
        for row in rows
    ]
    return ok({"pageNum": pageNum, "pageSize": pageSize, "total": total, "records": records})


@app.get("/session/{conversation_id}")
def session_detail(conversation_id: str):
    rows = storage.session_messages(conversation_id)
    if not rows:
        return fail("会话不存在", 404)
    return ok(
        {
            "conversationId": conversation_id,
            "agentType": rows[0].agentType,
            "fileid": rows[0].fileid,
            "messages": [row.to_dict() for row in rows],
        }
    )


@app.delete("/session/{conversation_id}")
def session_delete(conversation_id: str):
    existed = bool(storage.session_messages(conversation_id))
    deleted = storage.delete_session(conversation_id)
    if not existed:
        return fail("会话不存在", 404)
    return ok("会话删除成功" if deleted else None)


@app.get("/agent/stop")
def agent_stop(conversationId: str = Query(...)):
    stopped = tasks.stop(conversationId)
    return {"success": stopped, "message": "已停止执行" if stopped else "没有找到正在执行的任务"}


def _sse_stream(agent: str, query: str, conversation_id: str, file_id: str | None):
    if agent == "ppt":
        output = generate_ppt(query, settings.generated_dir)
        events = list(engine.stream(agent, conversation_id, query, file_id))
        ppt_url = object_store.upload_bytes(
            output.read_bytes(),
            f"ppt/{conversation_id}/{output.name}",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
        download_url = ppt_url if settings.file_storage_backend == "minio" else f"/generated/{output.name}"
        events.insert(-1, engine.event("text", f"\n下载文件: {download_url}"))
        if settings.file_storage_backend == "minio":
            output.unlink(missing_ok=True)
    else:
        events = engine.stream(agent, conversation_id, query, file_id)

    for event in events:
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


def _agent_stream(agent: str, query: str, conversationId: str, fileId: str | None = None):
    text = (query or "").strip()
    conversation_id = (conversationId or "").strip()
    file_id = (fileId or "").strip() or None
    if not text:
        raise HTTPException(status_code=400, detail="查询参数不能为空")
    if not conversation_id:
        raise HTTPException(status_code=400, detail="conversationId 不能为空")
    if agent == "file" and not file_id:
        raise HTTPException(status_code=400, detail="fileId 不能为空")
    if agent == "file" and not (storage.get_file(file_id) or storage.get_document(file_id)):
        raise HTTPException(status_code=404, detail="文件或文档不存在")
    return StreamingResponse(
        _sse_stream(agent, text, conversation_id, file_id),
        media_type="text/event-stream; charset=utf-8",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.get("/agent/chat/stream")
def chat_stream(query: str, conversationId: str):
    return _agent_stream("chat", query, conversationId)


@app.get("/agent/file/stream")
def file_stream(query: str, conversationId: str, fileId: str):
    return _agent_stream("file", query, conversationId, fileId)


@app.get("/agent/pptx/stream")
def pptx_stream(query: str, conversationId: str):
    return _agent_stream("ppt", query, conversationId)


@app.get("/agent/deep/stream")
def deep_stream(query: str, conversationId: str):
    return _agent_stream("deep", query, conversationId)


@app.get("/agent/skills/stream")
def skills_stream(query: str, conversationId: str, fileId: str | None = None):
    return _agent_stream("skills", query, conversationId, fileId)


@app.get("/doc-asset/{object_path:path}")
def doc_asset(object_path: str):
    """Serve images the local object storage backend produced for converted docs."""
    root = settings.upload_dir.resolve()
    target = (root / object_path).resolve()
    if root not in target.parents or not target.is_file():
        raise HTTPException(status_code=404, detail="文档资源不存在")
    return FileResponse(
        target,
        media_type=mimetypes.guess_type(target.name)[0] or "application/octet-stream",
    )


@app.get("/generated/{name}")
def generated_file(name: str):
    source = settings.generated_dir / Path(name).name
    if not source.exists() or not source.is_file():
        raise HTTPException(status_code=404, detail="生成文件不存在")
    return FileResponse(
        source,
        media_type=mimetypes.guess_type(source.name)[0] or "application/octet-stream",
        filename=source.name,
    )


@app.get("/__build")
def build_stamp():
    """Hot-deploy probe: boot id + frontend dist fingerprint for auto-reload."""
    return ok({"boot": SERVER_BOOT_ID, "build": dist_fingerprint()})


if os.environ.get("DODO_DEV_FRONTEND_URL"):
    @app.get("/")
    def dev_index():
        # Dev mode: the Vite server owns the page; sending 8888 visitors there
        # keeps one mental address while HMR runs on the Vite origin.
        return RedirectResponse(os.environ["DODO_DEV_FRONTEND_URL"], status_code=307)

else:
    # Decide per request: in hot-deploy mode the initial `vite build --watch`
    # can still be writing dist when this module is imported.
    @app.get("/")
    def index():
        index_file = FRONTEND_DIST / "index.html"
        if not index_file.is_file():
            return JSONResponse(
                ok(None, "前端尚未构建：请在项目根目录执行 npm --prefix frontend install && npm --prefix frontend run build，然后重启服务", 503),
                status_code=503,
            )
        html = index_file.read_text("utf-8")
        return HTMLResponse(
            html.replace("</body>", f"{LIVE_RELOAD_SNIPPET}</body>", 1),
            headers={"Cache-Control": "no-store"},
        )

    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets", check_dir=False), name="assets")

    @app.get("/favicon.ico")
    def favicon_file():
        target = STATIC_DIR / "favicon.ico"
        if not target.is_file():
            raise HTTPException(status_code=404, detail="图标不存在")
        return FileResponse(target)
