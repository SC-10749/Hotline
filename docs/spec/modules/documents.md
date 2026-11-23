# 文档解析与向量化（documents）

> 模块路径：`python_backend/modules/documents/`（`service.py` / `parser.py` / `ppt.py`）
> 前端对应：`frontend/src/App.vue`（文档面板：上传、切分预览、版本、补偿）、`frontend/src/modules/artifacts/ArtifactList.vue`（产物与文件展示）
> 状态：现状说明（以代码为准，冲突时以代码为准并修正本文档）

## 上传与 MinerU 精度解析管线

### 入口

- `POST /document/upload` —— 上传文档，同步返回转换后的文档记录
- `python_backend/modules/documents/service.py:DocumentService.upload` —— 落记录、跑管线、写版本
- `python_backend/modules/documents/service.py:MineruClient.convert` —— 提交一个文件并取回结果包字节

### 行为

- 路由先校验文件非空且不超过 `max_file_size`；文件名只取 basename，不保留目录层级。
- `.md` / `.markdown` 直通：内容原样写成 `full.md`，`convertedVia=markdown`，不调用 MinerU。
- 其它类型走 MinerU：`POST /api/v4/file-urls/batch` 取 `batch_id` 与预签名 URL → PUT 上传字节 → 轮询 `/api/v4/extract-results/batch/{batch_id}`。
- 预签名上传对 Content-Type 敏感：先带按文件名猜测的 MIME，收到 403 再用空 Content-Type 重试一次，其它非 2xx 直接报错。
- 轮询间隔取 `mineru_poll_interval` 秒、超过 `mineru_timeout` 秒报超时；`state=done` 取 `full_zip_url`，`state=failed` 报服务端 `err_msg`；业务码非 0 或未配置 `MINERU_TOKEN` 时抛 `DocumentError`。

### 关键实现

- `service.py:MineruClient._call` / `_upload` / `_poll` —— 接口调用、预签名上传重试、结果轮询
- `service.py:extract_archive` / `find_markdown` —— 结果包经 `safe_extract` 解压；优先 `full.md`，否则取归档里第一个 `.md`
- 配置项：`MINERU_TOKEN`、`DODO_MINERU_BASE_URL`、`DODO_MINERU_MODEL_VERSION`、`DODO_MINERU_POLL_INTERVAL`、`DODO_MINERU_TIMEOUT`

## Markdown 结果发布、图片托管与图注

### 入口

- `python_backend/modules/documents/service.py:DocumentPipeline.run` —— 一份文件进、可发布 Markdown 出
- `python_backend/modules/documents/service.py:publish_images` / `caption_images` —— 上传图片、改写引用、写图注

### 行为

- 转换结果整体写成 `docs/<docId>/document.md`（`text/markdown; charset=utf-8`），URL 记入记录的 `markdownUrl`。
- 图片标签按正则匹配：`http://`、`https://`、`data:`、`//` 开头视为外部引用原样保留；本地引用解析后逃出解包根目录的同样当外部引用跳过。
- 上传成功的图片对象名为 `docs/<docId>/<相对路径>`，内容类型按文件名猜测；访问地址由对象存储给出（本地后端为 `/doc-asset/<对象名>`）。只有被 Markdown 引用到的图片才入对象存储。
- 图注：未配置多模态 Key 时跳过全部图片并记告警；否则把图片以 base64 data URL 内联发给多模态 `/chat/completions`（本地对象地址托管模型访问不到），单张超过 8MB 直接跳过，成功后以 `> 图注：<描述>` 追加在图片标签后，单张失败只记告警不中断整篇转换。
- 记录写入 `imageCount`、`captionCount`、`charCount`、`version`（已有版本数 + 1），并向版本表写一条版本与图片映射。

### 关键实现

- `service.py:VisionCaptioner.describe` / `CAPTION_PROMPT` / `MAX_IMAGE_BYTES` —— 图注提示词固定为一句话客观描述，不猜测文档上下文
- `python_backend/modules/storage/objects.py:ObjectStorage.public_url` —— 本地后端把文件路径转成可访问地址
- 配置项：`DODO_MULTIMODAL_MODEL`、`DODO_MULTIMODAL_BASE_URL`、`DODO_MULTIMODAL_API_KEY`

## 父子块切分、向量化与预览

### 入口

- `POST /document/{doc_id}/vectorize` —— 手动触发向量化
- `python_backend/modules/documents/service.py:DocumentService.vectorize` —— 向量化总入口
- `GET /document/{doc_id}/preview` —— 分段明细与图片描述预览

### 行为

- 按 Markdown 标题层级切分，标题路径用 ` > ` 连接；代码围栏内的 `#` 不当标题；没有标题行时整篇算一节；只有标题、正文为空的节不产分块。
- 超长章节用滑动窗口切子块，切点优先段落、行、句号、空格，最早切点不早于窗口的 60%，overlap 被压到窗口一半以内；未超长的章节直接产出一个子块（`parentId` 为空），超长章节产出一个父块（整节正文，不向量化）与若干子块。
- 写入前先按文档 ID 删旧行，重试不留半截数据；子块元数据带 `fileid`、`chunkId`、`parentChunkId`、`heading`；向量库不可用或正文读不到时状态回退 `CONVERTED` 并记录原因。
- 关系图谱：对前 40 个子块抽三元组（每块最多 12 条），按文档 ID 整体替换关系表。
- 预览与实际切分共用 `plan_chunk_sections`，边界一致；返回章节字符数、是否存为父块、分块内容与统计（章节/父块/子块数、平均与最大子块字符数、图片数、有图注数），统计口径声明字符数包含 Markdown 标记与空白。
- 图片预览读 Markdown 里的图片标签：紧随的 `> 图注：` 记为「AI 图注」，没有时取紧随的「图 N：」行记为「原文说明」。

### 关键实现

- `service.py:build_chunks` / `split_sections` / `split_text` / `plan_chunk_sections` —— 父子块边界计算
- `python_backend/modules/retrieval/vector_store.py:PgVectorStore.index_document` —— 父块存正文、子块写入向量；配置项 `DODO_CHUNK_SIZE`、`DODO_CHUNK_OVERLAP`

## 私密路径与敏感内容排除

### 入口

- `python_backend/modules/documents/service.py:extract_archive` —— 结果包安全解压
- `python_backend/modules/documents/service.py:publish_images` —— 越界图片引用排除
- `python_backend/modules/retrieval/vector_store.py:PgVectorStore._embed` —— 嵌入前脱敏

### 行为

- MinerU 结果包经 `skills.registry.safe_extract` 解压：条目数与解压体积有上限，越界路径与软链接一律拒绝。
- 图片相对引用解析后必须仍在解包根目录内，否则当外部引用跳过，不写入对象存储；对象存储上传也拒绝空对象名与绝对路径，本地后端解析后的目标必须仍落在 `upload_dir` 内。
- 分块正文写向量库前经 `context_engineering.privacy.sanitize_text` 脱敏：去 `.env` 赋值、密钥串、域名与地址。
- 私密路径判定集中在 `privacy.private_path`：目录名 `private`、`secrets`、`.ssh` 等，文件名含 `.env`、`.local.`、`.private.`、`*.pem`、`*.key` 等。

### 关键实现

- `python_backend/modules/skills/registry.py:safe_extract` —— 条目数与体积上限、软链接与越界路径拒绝
- `python_backend/modules/context_engineering/privacy.py:private_path` / `sanitize_text`

## 失败补偿、事件总线与清理

### 入口

- `POST /document/compensate` —— 补偿扫描待向量化文档
- `python_backend/modules/documents/service.py:DocumentService.compensate` / `start_sweeper` / `stop_sweeper`
- `DELETE /document/{doc_id}` → `DocumentService.remove` —— 删除文档及其衍生数据

### 行为

- 转换失败时记录状态 `FAILED` 与错误信息，接口返回业务错误而不是 500。
- 转换成功发布 `document.converted` 事件，总线用线程池异步投递（最多 2 个工作线程），订阅者抛异常只打印日志；队列是进程内的，重启会丢事件，所以补偿是必需路径。
- 补偿扫描状态为 `CONVERTED` 或 `VECTORIZING` 的文档重新走向量化，默认 20 条，按创建时间升序；进程内另有后台清扫线程，间隔取 `doc_compensate_interval` 秒（配 0 关闭），外部调度器也可直接 POST `/document/compensate`。
- 同一文档重复向量化有进程内互斥，命中返回 `inProgress`；已 `VECTORIZED` 的返回 `alreadyVectorized`。
- 每次转换的临时解包目录在 `finally` 里整目录删除（正文以文本返回、图片已进对象存储）；删除文档时同时删向量行、关系行、Markdown 对象、版本记录与该文档的本地图片目录。

### 关键实现

- `service.py:DocumentEventBus` —— 进程内发布订阅；配置项 `DODO_DOC_COMPENSATE_INTERVAL`

## 普通文件上传与文本抽取

### 入口

- `POST /file/upload` —— 上传普通文件并抽取文本
- `python_backend/modules/documents/parser.py:parse_file` —— 按后缀抽文本
- `GET /file/list`、`GET /file/info/{file_id}`、`GET /file/content/{file_id}`、`GET /file/exists/{file_id}`、`DELETE /file/{file_id}`

### 行为

- 支持纯文本类（txt/md/csv/json/xml/html）、PDF（pypdf）、DOCX（python-docx）；图片文件只返回「已上传、未配置 OCR」的提示文案；其它后缀报「不支持的文件类型」。
- 抽取结果分全文与截断文本两份，截断上限取 `max_text_length`，超长时追加截断标记；文件同时写对象存储与本地 `upload_dir`。
- 正文长度达到 `large_file_threshold`、且向量库开启且 embedding key 存在时，按步长 450、窗口 500 切块写入向量库。

## PPT 生成

### 入口

- `python_backend/modules/documents/ppt.py:generate_ppt` —— 生成一份 PPTX 文件
- `python_backend/workers/execution_worker.py` —— ppt agent 流程里调用生成并登记产物

### 行为

- 用 python-pptx 生成 3 页固定模板：首页「AI 智能演示」放需求正文，第二页「核心内容」，第三页是实施步骤页（准备、执行、验证、迭代）；需求文本折叠空白后截断到 1200 字放进首页正文，需求为空直接抛 `ValueError`。
- 写盘后重新打开校验：文件缺失、为空或打不开就删掉并报错，不产出看起来成功的空文件。
- Worker 生成后登记为产物（artifacts），对象存储后端先上传再删本地文件，通过产物元数据给出下载地址；生成失败不登记产物。

## 数据与存储

- 关系库（SQLite / MySQL）：`ai_document`（文档记录）、`ai_document_version`（版本、Markdown 地址、图片映射、备注）。
- 对象存储（MinIO 或本地后端）：`docs/<docId>/document.md`、`docs/<docId>/<图片相对路径>`；本地后端落在 `upload_dir` 下，访问地址形如 `/doc-asset/<对象名>`。
- pgvector：分块表存子块与向量，父块表存整节正文（不向量化），关系表存三元组。
- 临时目录：`data/tmp/<docId>`，转换结束即删除；PPT 产物：`generated_dir/<runId>/<uuid>.pptx`，经 artifacts 登记后提供下载。

## 接口清单

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/document/upload` | 上传文档并同步完成转换 |
| `GET` | `/document/list` | 文档列表 |
| `POST` | `/document/{doc_id}/vectorize` | 父子分段切分并向量化 |
| `GET` | `/document/{doc_id}/preview` | 分段明细与图片描述预览 |
| `GET` | `/document/{doc_id}/versions` | 版本列表 |
| `POST` | `/document/compensate` | 补偿扫描未向量化文档 |
| `DELETE` | `/document/{doc_id}` | 删除文档及向量、对象、版本 |
| `POST` | `/file/upload` | 普通文件上传与文本抽取 |
| `GET` | `/file/list`、`/file/info/{file_id}`、`/file/content/{file_id}` | 文件列表、详情与抽取文本 |
| `DELETE` | `/file/{file_id}` | 删除文件与对象存储副本 |
| `POST` | `/agent/pptx/stream` | ppt agent 流式生成，产物登记在 artifacts |

## 边界与已知限制

- 没有 `MINERU_TOKEN` 时只有 Markdown 能转换，其它文件一律失败。
- MinerU 批量提交只上传第一个文件，轮询只取第一个任务结果；结果包只保留 Markdown 与被引用的图片，图注未配置多模态 Key 时跳过并记告警。
- 向量化失败不自动重试到成功，依赖补偿扫描或人工触发 `/document/{doc_id}/vectorize`。
- 父块只存正文不生成向量，召回靠子块命中后回填父块整节内容。
- 正文文件被清理后，预览与向量化都会报「读不到文档正文」。
- 上传接口不判定文件名是否属私密配置；私密排除只发生在结果包解压、对象存储写入与嵌入前脱敏三处。
- 本机没有可用 MySQL，整包导入 `python_backend.fastapi_app` 会在 `PgVectorStore` 连接处抛 `Access denied`，属于环境限制。
