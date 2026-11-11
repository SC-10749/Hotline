from __future__ import annotations

import mimetypes
import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .infrastructure.service_registry import NacosRegistry, RegistryConfig
from python_backend.modules.documents.service import DocumentError, DocumentService
from .models import DocumentRecord, FileInfo, now_iso
from python_backend.modules.storage.objects import ObjectStorage
from python_backend.modules.documents.parser import parse_file
from python_backend.modules.skills.catalog import Catalog
from python_backend.modules.skills.registry import SkillError, SkillRegistry
from python_backend.modules.storage.relational import Storage
from python_backend.modules.retrieval.vector_store import PgVectorStore
from .application.execution_service import ExecutionApplicationService
from .infrastructure.queue import SqliteExecutionQueue
from python_backend.modules.execution.engine import ModelClient
from .api.routers.execution import create_execution_router
from .api.routers.context_engineering import create_context_router
from .modules.context_engineering.service import ContextService
from .api.routers.intent import create_intent_router
from .modules.intent import (ACTION_CATALOG, RETRIEVAL_CATALOG, ExampleVectorStore,
                              vector_config_from_settings)
from .api.routers.evaluation import create_evaluation_router, wait_for_background_runs
from .api.routers.release import create_release_router, stop_release_observation
from .api.routers.resources import create_resource_router
from .api.routers.registry import create_registry_router
from .api.routers.mcp import create_mcp_router
from .api.routers.governance import create_governance_router
from .api.routers.observability import create_observability_router
from .api.routers.artifacts import create_artifact_router
from .api.routers.code_map import create_code_map_router
from .api.routers.workspace_import import create_workspace_import_router
from .modules.artifacts.store import ArtifactStore
from .modules.retention.maintenance import start_retention_loop
from .modules.execution.scheduler import register_runner, stop_schedule_loop
from .api.routers.settings import create_settings_router
from .api.routers.schedules import create_schedule_runner, create_schedules_router
from .api.routers.bots import create_bots_router
from .api.routers.profile import create_profile_router
from .llm import probe_credential
from .infrastructure.evaluation_store import EvaluationStore
from .infrastructure.resource_store import ResourceStore
from .infrastructure.registry_store import RegistryStore
from .infrastructure.governance_store import GovernanceStore
from .infrastructure.notification_store import NotificationStore
from .infrastructure.settings_store import SettingsStore
from .infrastructure.scheduled_store import ScheduledStore
from .infrastructure.bot_store import BotStore
from .infrastructure.profile_store import ProfileStore
from .infrastructure.credential_store import CredentialStore

settings.ensure_dirs()
storage = Storage(settings)
object_store = ObjectStorage(settings)
vector_store = PgVectorStore(settings)
skills = SkillRegistry(settings)
documents = DocumentService(settings, storage, object_store, vector_store)
execution_store = SqliteExecutionQueue(settings.execution_db_path)
execution_service = ExecutionApplicationService(execution_store)
service_registry = NacosRegistry(RegistryConfig.from_environment(), settings.data_dir, execution_store.has_live_worker)
context_service = ContextService(settings) if settings.context_enabled else None
evaluation_store = EvaluationStore(settings.data_dir / "evaluation.db")
resource_store = ResourceStore(settings.data_dir / "harness-resources.db")
registry_store = RegistryStore(settings.data_dir / "harness-registry.db")
governance_store = GovernanceStore(settings.data_dir / "harness-governance.db")
notification_store = NotificationStore(settings.data_dir / "harness-notifications.db")
settings_store = SettingsStore(settings.data_dir / "harness-settings.db")
artifact_store = ArtifactStore(settings.data_dir / "artifacts.db")
scheduled_store = ScheduledStore(settings.data_dir / "harness-schedules.db")
bot_store = BotStore(settings.data_dir / "harness-bots.db")
profile_store = ProfileStore(settings.data_dir / "harness-profile.db")
credential_store = CredentialStore(settings.data_dir / "harness-credentials.db")

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
    await service_registry.start()
    documents.start_sweeper()
    register_runner(create_schedule_runner(scheduled_store, execution_service))
    retention_stop = start_retention_loop(
        {
            'execution': settings.execution_db_path,
            'governance': settings.data_dir / 'harness-governance.db',
            'artifacts': settings.data_dir / 'artifacts.db',
        },
        settings_store.get,
    )
    try:
        yield
    finally:
        await service_registry.stop()
        retention_stop.set()
        stop_schedule_loop()
        stop_release_observation()
        wait_for_background_runs(timeout=5)
        documents.stop_sweeper()


app = FastAPI(title="Hotline Agent", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(
    create_execution_router(
        execution_service,
        lambda file_id: bool(storage.get_file(file_id) or storage.get_document(file_id)),
        lambda: len(governance_store.list('pending')),
        workspace_exists=lambda workspace_id: resource_store.get_workspace(workspace_id) is not None,
    )
)
app.include_router(create_evaluation_router(evaluation_store, execution_service))
if context_service:
    app.include_router(create_context_router(context_service, storage.delete_session))
app.include_router(create_resource_router(resource_store))
app.include_router(create_workspace_import_router(resource_store, settings.data_dir / 'workspace-imports'))
app.include_router(create_registry_router(registry_store))
app.include_router(create_mcp_router(registry_store))
app.include_router(create_governance_router(execution_store.list_workers, governance_store, execution_store.set_worker_state, settings_store.get, notification_store, execution_store.list_worker_errors))
app.include_router(create_observability_router(execution_store.list_runs, execution_store.get_run, execution_store.get_events))
app.include_router(create_artifact_router(artifact_store, object_store))
app.include_router(create_code_map_router(settings.data_dir / 'code-map' / 'hotline'))
app.include_router(create_settings_router(settings_store))
app.include_router(create_schedules_router(scheduled_store, execution_service))
app.include_router(create_bots_router(bot_store))
app.include_router(create_profile_router(profile_store, credential_store, model_probe=probe_credential))
# 意图识别：第二层向量召回按 scope 各建一份缓存，未配置 embedding 时自动跳过。
_intent_vector_config = vector_config_from_settings(settings)
app.include_router(create_intent_router(ModelClient(settings).chat, {
    catalog.name: ExampleVectorStore(catalog, _intent_vector_config)
    for catalog in (ACTION_CATALOG, RETRIEVAL_CATALOG)
}))


def ok(data=None, message="操作成功", code=200):
    return {"code": code, "message": message, "data": data}


def fail(message: str, code: int = 400):
    return JSONResponse(ok(None, message, code), status_code=code)


@app.get("/health")
def health():
    return {"status": "UP", "service": "hotline-agent", "version": "fastapi"}


@app.get("/health/ready")
def readiness():
    worker_available = execution_store.has_live_worker()
    ready = worker_available and service_registry.available
    return JSONResponse(
        {"status": "UP" if ready else "DEGRADED", "service": "hotline-agent",
         "executionWorker": "available" if worker_available else "unavailable",
         "serviceRegistry": "available" if service_registry.available else "unavailable"},
        status_code=200 if ready else 503,
    )


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


@app.get('/skill/{skill_id}')
def skill_detail(skill_id: str):
    try:
        item = skills.detail(skill_id)
    except SkillError as exc:
        return fail(str(exc))
    if not item:
        return fail('技能不存在', 404)
    return ok(item)


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


app.include_router(create_release_router(run_catalog, settings.skill_project, evaluation_store.get_run, governance_store))


@app.get('/harness/skills/catalog')
def harness_skill_catalog():
    return ok(run_catalog('catalog_summary', {'project': settings.skill_project}))


@app.get('/harness/skills/catalog/version')
def harness_skill_version(name: str = Query(min_length=1, max_length=200), version: str = Query(min_length=1, max_length=100)):
    try:
        return ok(run_catalog('version_detail', {'name': name, 'version': version}))
    except ValueError as exc:
        return fail(str(exc), 404)


@app.get('/harness/skills/catalog/compare')
def harness_skill_compare(name: str = Query(min_length=1, max_length=200), baseVersion: str = Query(min_length=1, max_length=100), version: str = Query(min_length=1, max_length=100)):
    try:
        return ok(run_catalog('version_compare', {'name': name, 'baseVersion': baseVersion, 'version': version}))
    except ValueError as exc:
        return fail(str(exc), 404)


@app.get("/console")
def console_index():
    index = CONSOLE_DIR / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="技能控制台页面不存在")
    return FileResponse(index)


@app.get("/console/{asset}")
def console_asset(asset: str):
    if Path(asset).name != asset or asset not in {"console.js", "console.css", "tokens.css"}:
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
    scope = context_service.store.conversation(conversation_id) if context_service else None
    return ok(
        {
            "conversationId": conversation_id,
            "workspaceId": scope['workspace_id'] if scope else '',
            "agentType": rows[0].agentType,
            "fileid": rows[0].fileid,
            "messages": [row.to_dict() for row in rows],
        }
    )


@app.delete("/session/{conversation_id}")
def session_delete(conversation_id: str):
    existed = bool(storage.session_messages(conversation_id))
    deleted = storage.delete_session(conversation_id)
    if context_service:
        context_service.forget(conversation_id)
    if not existed:
        return fail("会话不存在", 404)
    return ok("会话删除成功" if deleted else None)


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

