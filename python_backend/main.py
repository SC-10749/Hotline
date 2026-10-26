from __future__ import annotations

import json
import mimetypes
import os
import posixpath
import shutil
import sys
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from uuid import uuid4

from .agents import AgentEngine, TaskManager
from .config import settings
from .models import FileInfo, now_iso
from .object_store import ObjectStorage
from .parser import parse_file
from .ppt import generate_ppt
from .storage import Storage
from .vector_store import PgVectorStore


settings.ensure_dirs()
storage = Storage(settings)
object_store = ObjectStorage(settings)
tasks = TaskManager(settings)
vector_store = PgVectorStore(settings)
engine = AgentEngine(settings, storage, tasks, vector_store)


def result(data=None, message="操作成功", code=200):
    return {"code": code, "message": message, "data": data}


class Handler(BaseHTTPRequestHandler):
    server_version = "DodoAgentPython/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def _headers(self, content_type="application/json; charset=utf-8", length=None):
        self.send_header("Content-Type", content_type)
        if length is not None:
            self.send_header("Content-Length", str(length))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept, Cache-Control")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")

    def _json(self, payload, status=HTTPStatus.OK):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._headers(length=len(body))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, message, status=HTTPStatus.BAD_REQUEST):
        self._json(result(None, message, int(status)), status)

    def _query(self):
        parsed = urlparse(self.path)
        return parsed.path, {key: values[-1] for key, values in parse_qs(parsed.query).items()}

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self._headers(length=0)
        self.end_headers()

    def do_GET(self):
        path, query = self._query()
        try:
            if path in {"/", "/index.html"}:
                return self._serve_static("index.html", "text/html; charset=utf-8")
            if path.startswith("/generated/"):
                name = Path(unquote(path.rsplit("/", 1)[-1])).name
                return self._serve_generated(name)
            if path.startswith("/static/") or path.startswith("/js/") or path.startswith("/css/") or path == "/favicon.ico":
                relative = path.removeprefix("/static/").lstrip("/")
                return self._serve_static(relative, mimetypes.guess_type(relative)[0] or "application/octet-stream")
            if path == "/health":
                return self._json({"status": "UP", "service": "dodo-agent", "version": "python"})
            if path == "/file/list":
                files = [item.to_dict() for item in storage.list_files()]
                return self._json(result({"count": len(files), "files": files}))
            if path.startswith("/file/info/"):
                return self._file_info(unquote(path.rsplit("/", 1)[-1]))
            if path.startswith("/file/content/"):
                return self._file_content(unquote(path.rsplit("/", 1)[-1]))
            if path.startswith("/file/exists/"):
                file_id = unquote(path.rsplit("/", 1)[-1])
                return self._json(result(storage.get_file(file_id) is not None))
            if path == "/session/list":
                page = max(1, int(query.get("pageNum", "1")))
                size = max(1, min(1000, int(query.get("pageSize", "10"))))
                rows, total = storage.session_list((page - 1) * size, size)
                records = [{"conversationId": row.conversationId, "question": row.question,
                            "agentType": row.agentType, "fileid": row.fileid, "createTime": row.createTime} for row in rows]
                return self._json(result({"pageNum": page, "pageSize": size, "total": total, "records": records}))
            if path.startswith("/session/"):
                return self._session_detail(unquote(path.rsplit("/", 1)[-1]))
            if path == "/agent/stop":
                conversation_id = query.get("conversationId", "")
                stopped = tasks.stop(conversation_id)
                return self._json({"success": stopped, "message": "已停止执行" if stopped else "没有找到正在执行的任务"})
            agent_paths = {"/agent/chat/stream": "chat", "/agent/file/stream": "file",
                           "/agent/pptx/stream": "ppt", "/agent/deep/stream": "deep", "/agent/skills/stream": "skills"}
            if path in agent_paths:
                return self._stream(agent_paths[path], query)
            return self._error("资源不存在", HTTPStatus.NOT_FOUND)
        except (ValueError, KeyError) as exc:
            return self._error(str(exc))
        except Exception as exc:
            traceback.print_exc()
            return self._error(f"服务器内部错误: {exc}", HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self):
        path, _ = self._query()
        if path == "/file/upload":
            try:
                return self._upload()
            except Exception as exc:
                traceback.print_exc()
                return self._error(f"文件上传失败: {exc}")
        return self._error("资源不存在", HTTPStatus.NOT_FOUND)

    def do_DELETE(self):
        path, _ = self._query()
        if path.startswith("/file/"):
            file_id = unquote(path.rsplit("/", 1)[-1])
            info = storage.get_file(file_id)
            if not info:
                return self._error("文件不存在", HTTPStatus.NOT_FOUND)
            object_store.delete_url(info.minioPath)
            storage.delete_file(file_id)
            return self._json(result("文件删除成功"))
        if path.startswith("/session/"):
            conversation_id = unquote(path.rsplit("/", 1)[-1])
            existed = bool(storage.session_messages(conversation_id))
            deleted = storage.delete_session(conversation_id)
            return self._json(result("会话删除成功" if deleted else None,
                                     "会话删除成功" if deleted else "会话不存在", 200 if existed else 404),
                              HTTPStatus.OK if existed else HTTPStatus.NOT_FOUND)
        return self._error("资源不存在", HTTPStatus.NOT_FOUND)

    def _upload(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0 or content_length > settings.max_file_size:
            return self._error("文件为空或超过大小限制")
        content_type = self.headers.get("Content-Type", "")
        body = self.rfile.read(content_length)
        if "multipart/form-data" not in content_type:
            return self._error("请求必须是 multipart/form-data")
        # email.parser handles multipart boundaries without external dependencies.
        from email.parser import BytesParser
        from email.policy import default
        message = BytesParser(policy=default).parsebytes((f"Content-Type: {content_type}\r\n\r\n").encode() + body)
        part = next((item for item in message.walk() if item.get_filename()), None)
        if part is None:
            return self._error("缺少 file 字段")
        name = Path(part.get_filename()).name
        file_id = uuid4().hex
        suffix = Path(name).suffix.lower()
        content = part.get_payload(decode=True) or b""
        object_name = f"file-{file_id.replace('-', '')}.{suffix.lstrip('.') or 'bin'}"
        minio_path = object_store.upload_bytes(
            content,
            object_name,
            part.get_content_type() or "application/octet-stream",
        )
        target = settings.upload_dir / f"{file_id}{suffix}"
        if settings.file_storage_backend == "local":
            target = settings.upload_dir / object_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        full, truncated = parse_file(target, settings.max_text_length)
        info = FileInfo(fileId=file_id, fileName=name, fileType=target.suffix.lower().lstrip("."),
                        fileSize=len(content), minioPath=minio_path, extractedText=truncated,
                        createdAt=now_iso())
        info.embed = 1 if (
            len(full) >= settings.large_file_threshold
            and settings.vector_enabled
            and settings.embedding_api_key
        ) else 0
        if info.embed:
            chunks = [full[index:index + 500] for index in range(0, len(full), 450)]
            vector_store.add_chunks(file_id, chunks)
        storage.save_file(info)
        return self._json(result(info.to_dict()))

    def _file_info(self, file_id):
        info = storage.get_file(file_id)
        return self._json(result(info.to_dict() if info else None, "操作成功" if info else "文件不存在", 200 if info else 404))

    def _file_content(self, file_id):
        info = storage.get_file(file_id)
        if not info:
            return self._error("文件不存在", HTTPStatus.NOT_FOUND)
        content = info.extractedText
        return self._json(result({"content": content, "length": len(content)}))

    def _session_detail(self, conversation_id):
        rows = storage.session_messages(conversation_id)
        if not rows:
            return self._json(result(None, "会话不存在", 404), HTTPStatus.NOT_FOUND)
        return self._json(result({"conversationId": conversation_id, "agentType": rows[0].agentType,
                                  "fileid": rows[0].fileid, "messages": [row.to_dict() for row in rows]}))

    def _stream(self, agent, query):
        text = query.get("query", "").strip()
        conversation_id = query.get("conversationId", "").strip()
        file_id = query.get("fileId")
        if not text:
            return self._error("查询参数不能为空")
        if not conversation_id:
            return self._error("conversationId 不能为空")
        if agent == "file" and not file_id:
            return self._error("fileId 不能为空")
        if agent == "file" and not storage.get_file(file_id):
            return self._error("文件不存在", HTTPStatus.NOT_FOUND)
        if agent == "ppt":
            output = generate_ppt(text, settings.generated_dir)
            events = list(engine.stream(agent, conversation_id, text, file_id))
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
            events = engine.stream(agent, conversation_id, text, file_id)
        self.send_response(HTTPStatus.OK)
        self._headers("text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        for event in events:
            payload = json.dumps(event, ensure_ascii=False)
            self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()
        self.close_connection = True

    def _serve_static(self, name, content_type):
        source = Path(__file__).parent.parent / "static" / name
        if not source.exists():
            return self._error("静态资源不存在", HTTPStatus.NOT_FOUND)
        body = source.read_bytes()
        self.send_response(HTTPStatus.OK)
        self._headers(content_type, len(body))
        self.end_headers()
        self.wfile.write(body)

    def _serve_generated(self, name):
        # URL path segments are user controlled. Restrict downloads to a single
        # generated filename and keep the resolved path inside generated_dir.
        root = settings.generated_dir.resolve()
        source = (root / Path(name).name).resolve()
        if root not in source.parents or not source.is_file():
            return self._error("生成文件不存在", HTTPStatus.NOT_FOUND)
        body = source.read_bytes()
        safe_name = source.name
        self.send_response(HTTPStatus.OK)
        self._headers(mimetypes.guess_type(safe_name)[0] or "application/octet-stream", len(body))
        self.send_header("Content-Disposition", f'attachment; filename="{safe_name}"')
        self.end_headers()
        self.wfile.write(body)


def run() -> None:
    server = ThreadingHTTPServer((settings.host, settings.port), Handler)
    print(f"Dodo Agent Python backend listening on http://{settings.host}:{settings.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
