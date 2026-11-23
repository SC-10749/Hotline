# 存储适配（storage）

> 模块路径：`python_backend/modules/storage/`（`objects.py` 对象存储、`relational.py` 关系库）｜ 前端对应：`frontend/src/modules/storage/`（只有 `.gitkeep`，无独立前端模块）
> 状态：现状说明（以代码为准，冲突时以代码为准并修正本文档）
> 兼容入口：`python_backend/object_store.py`、`python_backend/storage.py` 只是把 `sys.modules` 指向新实现的别名，调用方仍可照旧导入。

## 对象存储（文件字节的落地与取回）

### 入口

- `python_backend/modules/storage/objects.py:ObjectStorage.upload_bytes` —— 写入字节流，返回可持久化的地址字符串
- `python_backend/modules/storage/objects.py:ObjectStorage.delete_url` —— 按已存地址删除对象
- `python_backend/modules/storage/objects.py:ObjectStorage.open_download` —— 打开对象读取流（只支持 minio）
- `python_backend/modules/storage/objects.py:ObjectStorage.public_url` —— 把存储地址翻译成浏览器可访问的地址
- `python_backend/modules/storage/objects.py:ObjectStorage.object_name` —— 从地址反解对象名
- `POST /file/upload` —— 上传后立即落对象存储并登记文件记录
- `GET /harness/artifacts/{artifact_id}/download` —— 产物下载走对象存储的读取流

### 行为

- 后端由 `DODO_FILE_STORAGE_BACKEND` 决定，取值只有 `minio` 与 `local`；其它值在构造时抛 `ValueError`。
- `upload_bytes` 拒绝空对象名和以 `/` 开头的绝对对象名，抛 `ValueError`。
- minio 后端：首次写入前 `_ensure_bucket` 检查并创建桶；`DODO_MINIO_PUBLIC_READ` 为真时再写入只读 `s3:GetObject` 的桶策略。
- minio 后端返回的地址形如 `<endpoint>/<bucket>/<quoted object name>`，对象名中的 `/` 保留、其余字符转义。
- local 后端返回 `local://<object name>` 形式的地址，文件真实落在 `DODO_UPLOAD_DIR` 下。
- `delete_url` 对空地址直接返回；local 后端删除文件且文件不存在也不报错，minio 后端调用 `remove_object`。
- `public_url` 只改写 local 地址：返回 `/doc-asset/<quoted object name>`；minio 地址原样返回。
- `object_name` 对 `local://` 前缀直接截取，对 http(s) 地址剥掉桶名前缀。
- `open_download` 在非 minio 后端时抛 `RuntimeError`；调用方据此判定「该产物所属存储当前未配置」。

### 关键实现

- `python_backend/modules/storage/objects.py:_local_path` —— 解析对象名落盘位置，越出 `upload_dir` 根目录即抛 `ValueError`。
- `python_backend/fastapi_app.py:doc_asset` —— 承接 local 后端的公开地址 `GET /doc-asset/{object_path:path}`，越界或非文件一律 404。
- `python_backend/workers/execution_worker.py:_events_for_run` —— 产物在 minio 后端先上传再删除本地临时文件；local 后端保留本地文件并以相对路径登记。
- `python_backend/api/routers/artifacts.py:create_artifact_router` —— 产物下载：local 走 `FileResponse`，minio 走 `open_download` 的 64 KiB 分块流。

## 本地开发实现（local 后端）

### 入口

- `python_backend/modules/storage/objects.py:ObjectStorage._local_path` —— local 后端的落盘路径解析
- `python_backend/config.py:Settings.file_storage_backend` —— 选择对象存储后端的配置项

### 行为

- `DODO_FILE_STORAGE_BACKEND` 不显式设置时，关系库后端是 `mysql` 则取 `minio`，否则取 `local`，即「生产跟 Java 服务、开发走本地文件」。
- 上传时自动创建目标目录。
- local 地址不能被浏览器直接访问，必须经 `public_url` 转成 `/doc-asset/...` 才可用于 markdown 里的图片引用。
- local 实现只覆盖上传、删除、公开地址；对象流读取在 local 后端不可用。

### 关键实现

- `python_backend/modules/documents/service.py:publish_images` —— 文档解析出的图片按 `docs/<file_id>/<相对路径>` 上传，再用 `public_url` 把 markdown 里的引用改写成可访问地址。
- `python_backend/modules/documents/service.py:read_markdown` —— 读取时按 `local://` 或 `/doc-asset/` 前缀还原对象名，从 `upload_dir` 读文件。

## 关系库适配（MySQL 主路径与 SQLite 回退）

### 入口

- `python_backend/modules/storage/relational.py:Storage.__init__` —— 按 `DODO_STORAGE_BACKEND` 建连接池或打开 SQLite
- `python_backend/modules/storage/relational.py:Storage._execute` —— 统一执行入口，屏蔽两种方言
- `python_backend/modules/storage/relational.py:Storage._init_mysql` / `Storage._init_sqlite` —— 建表

### 行为

- `DODO_STORAGE_BACKEND` 只接受 `mysql` 与 `sqlite`，其它值抛 `ValueError`。
- mysql 后端用 `mysql-connector-python` 的 `MySQLConnectionPool`（池名 `dodo_python_pool`，大小 `DODO_MYSQL_POOL_SIZE`），连接开启 autocommit。
- sqlite 后端落在 `DODO_DATA_DIR/dodo.db`（`settings.db_path`），连接使用 `check_same_thread=False`，并用进程内 `RLock` 串行化写操作。
- 两种后端建同一批表：`ai_file_info`、`ai_session`、`ai_ppt_inst`、`ai_ppt_template`、`ai_document`、`ai_document_version`。
- 占位符统一写 `?`，MySQL 分支在 `_execute` 里替换成 `%s`。
- upsert 语法按后端分叉：sqlite 用 `ON CONFLICT ... DO UPDATE`，mysql 用 `ON DUPLICATE KEY UPDATE`。
- 开启 mysql 后端时若缺少 `mysql-connector-python`，构造时抛 `RuntimeError`。

### 关键实现

- `python_backend/modules/storage/relational.py:Storage._execute` —— 统一返回行、结果集或自增 id；sqlite 返回 cursor，mysql 返回 `lastrowid`。
- `python_backend/config.py:Settings` —— 配置项来源，见「数据与存储」。

## 文件记录与问答会话消息

### 入口

- `python_backend/modules/storage/relational.py:Storage.save_file` / `get_file` / `list_files` / `delete_file` —— 文件记录读写
- `python_backend/modules/storage/relational.py:Storage.save_question` / `update_answer` —— 一问一答落库
- `python_backend/modules/storage/relational.py:Storage.session_messages` / `context_messages` / `search_session_messages` / `session_list` / `delete_session` / `conversation_file_id` —— 会话消息读取与清理
- `python_backend/modules/storage/relational.py:Storage.save_document` / `get_document` / `list_documents` / `documents_by_status` / `delete_document` / `add_document_version` / `list_document_versions` —— 文档记录与版本
- `python_backend/modules/execution/engine.py:AgentEngine.stream` —— 问答主流程调用存取接口

### 行为

- 文件记录按 `file_id` 唯一，重复写入走 upsert；`minio_path` 字段存的是对象存储地址，不是文件路径。
- `save_question` 写入 `question`、`agent_type`、`fileid` 并返回自增行号；`update_answer` 补写 `answer`、`thinking`、`tools`、`reference`、`recommend`，后两者是结构化值时按 JSON 序列化。
- `session_messages` 按 id 升序返回整个会话；`context_messages` 取最近 N 条（默认 64）再反转为升序。
- `search_session_messages` 把查询切成最多 8 个词元做 `LIKE` 匹配，只返回 answer 非空且按 id 倒序的前 N 条（默认 6）。
- `session_list` 的标题取会话第一条消息，`agentType` 取最后一条消息的助手类型。
- `delete_session` 先判断会话是否存在，再依次删除 `ai_file_info`、`ai_ppt_inst`、`ai_session` 中该会话的行。
- 文档记录按 `doc_id` 唯一，版本表按 `(doc_id, version)` 唯一，`image_map` 以 JSON 存放。
- 返回给前端的结构体由 `python_backend/models.py` 的 `FileInfo`、`SessionMessage`、`DocumentRecord` 定义。

### 关键实现

- `python_backend/modules/execution/engine.py` —— 用 `save_question`/`update_answer` 写入每一轮问答，用 `context_messages`（上下文开启时）或 `session_messages` 拼历史，用 `search_session_messages` 做历史检索。
- `python_backend/fastapi_app.py:file_upload` —— 上传后同时写对象存储、落本地文件、登记 `ai_file_info`。

## 数据与存储

- 关系库：`DODO_STORAGE_BACKEND=mysql` 时用 `DODO_MYSQL_HOST`、`DODO_MYSQL_PORT`、`DODO_MYSQL_DATABASE`、`DODO_MYSQL_USER`、`DODO_MYSQL_PASSWORD`、`DODO_MYSQL_POOL_SIZE` 连接上述 `ai_` 六张表。
- SQLite 回退：`DODO_STORAGE_BACKEND=sqlite` 时数据库文件为 `DODO_DATA_DIR/dodo.db`。
- 对象存储：`DODO_MINIO_ENDPOINT`、`DODO_MINIO_ACCESS_KEY`、`DODO_MINIO_SECRET_KEY`、`DODO_MINIO_BUCKET`、`DODO_MINIO_PUBLIC_READ`。
- 目录：`DODO_DATA_DIR`（根）、`DODO_UPLOAD_DIR`（local 对象与文档图片）、`DODO_GENERATED_DIR`（产物文件）。
- 全部运行数据落在被 Git 忽略的 `data/` 目录下。

## 接口清单

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/file/upload` | 上传文件：写对象存储 + 登记 `ai_file_info` |
| `DELETE` | `/file/{file_id}` | 删除对象与文件记录 |
| `GET` | `/file/list` | 列出全部文件记录 |
| `GET` | `/file/info/{file_id}` | 读取单个文件记录 |
| `GET` | `/file/content/{file_id}` | 读取文件抽取文本 |
| `GET` | `/file/exists/{file_id}` | 判断文件记录是否存在 |
| `GET` | `/doc-asset/{object_path:path}` | 提供 local 后端对象的公开访问地址 |
| `GET` | `/session/list` | 会话分页列表（标题取首条、助手类型取末条） |
| `GET` | `/session/{conversation_id}` | 会话全部消息 |
| `DELETE` | `/session/{conversation_id}` | 删除会话及其文件、PPT 记录 |
| `GET` | `/harness/artifacts/{artifact_id}/download` | 产物下载（local 文件流 / minio 对象流） |
| `GET` | `/document/{doc_id}` | 读取文档记录 |
| `GET` | `/document/{doc_id}/versions` | 读取文档版本列表 |

## 边界与已知限制

- 本模块没有独立路由：`/file/*`、`/session/*`、`/document/*` 由 `python_backend/fastapi_app.py` 装配，产物路由由 `python_backend/api/routers/artifacts.py` 装配。
- `ai_` 六张表只在本模块内被读写；其他模块必须调用 `Storage` 的方法，不得直接连库查表或改表结构。
- 产物登记不落在本模块的库里：`python_backend/modules/artifacts/store.py` 用独立的 `run_artifact` 表（`data/artifacts.db`）。
- `ai_ppt_template` 建表后没有任何读写接口，只有 `ai_ppt_inst` 在删会话时被清理。
- `open_download` 只在 minio 后端可用；local 后端的产物下载走 `generated_dir` 下的文件读取，预览接口也只支持 local 后端。
- 关系库后端为 mysql 时会连带决定向量库与 Redis 的默认开关（`DODO_VECTOR_ENABLED`、`DODO_REDIS_ENABLED`），本模块自身不读写向量库。
