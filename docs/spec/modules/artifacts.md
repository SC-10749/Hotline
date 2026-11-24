# 产物与文件登记（artifacts）

> 模块路径：`python_backend/modules/artifacts/`（`store.py` 登记与查询）
> 前端对应：`frontend/src/modules/artifacts/`（`ArtifactList.vue` 产物列表、`CodeMapPage.vue` 代码地图页）
> 状态：现状说明（以代码为准，冲突时以代码为准并修正本文档）

## 产物登记

### 入口

- `python_backend/modules/artifacts/store.py:ArtifactStore.register` —— 写入一条产物登记
- `python_backend/modules/artifacts/store.py:register_generated_file` —— 按磁盘文件大小与摘要登记
- `python_backend/modules/artifacts/store.py:register_legacy_artifact` —— 队列外产出的登记，用会话 id 顶替 run id
- `python_backend/modules/artifacts/store.py:legacy_run_id` —— 无会话 id 时生成 `legacy-<时间戳>-<序号>` 兜底

### 行为

- 归属只认显式传入的 `run_id`，不从文件名或目录扫描推断。
- `name` 必须是纯文件名（等于 `PurePosixPath(name).name`），不含反斜杠与控制字符；`size` 不得为负；`sha256` 必须是小写 64 位十六进制。
- `storage_backend` 只接受 `local` 与 `minio`；`storage_key` 必须是相对 POSIX 路径，绝对路径、含 `..`、含反斜杠或冒号一律拒绝，抛 `ValueError('无效的产物登记信息')`。
- 唯一键是 `(run_id, storage_backend, storage_key)`：完全相同的重复登记返回原记录（`artifact_id` 不变）；同键但字段不同抛 `ValueError('产物位置已登记，不能覆盖原始记录')`。
- `owner` 必填且非空（规格 S-013）：空归属登记直接 `ValueError('产物登记必须带归属身份')`；长度不超过 200。老库没有 `owner` 列时构造时自动补列，历史记录归属为空串。

### 关键实现

- `python_backend/modules/artifacts/store.py:ArtifactStore.register` —— 先 `INSERT ... ON CONFLICT DO NOTHING` 再回读比对，保证并发下不覆盖原记录。
- `python_backend/modules/artifacts/store.py:register_generated_file` —— 读文件字节算 sha256；异常时返回 `(None, 异常类名)` 而不是抛错，调用方仍可把文件交回用户。

## 运行产物的生成与发布

### 入口

- `python_backend/workers/execution_worker.py:ExecutionWorker._events_for_run` —— ppt 代理结束后生成、登记并发布产物
- `python_backend/workers/execution_worker.py:build_worker` —— 用 `data/artifacts.db` 装配产物库

### 行为

- 只有 `agent == 'ppt'` 且运行以 `complete` 收尾时才生成产物；运行报错或被取消时不生成、不登记。
- 生成目录是 `DODO_GENERATED_DIR/<run_id>`；local 后端登记相对路径，minio 后端登记 `ppt/<run_id>/<文件名>`，先上传对象再删除本地临时文件。
- 登记成功后依次发 `artifact` 事件（带产物元数据）、`text` 事件（正文里带下载路径）、`complete` 事件；登记失败时运行判为 `failed`，只发 `error` 事件，失败详情不写进事件流。

### 关键实现

- `python_backend/modules/artifacts/store.py:artifact_metadata` —— 对外元数据：不含 `storage_key`，带 `ageDays` 与 `download` 路径。
- `python_backend/workers/execution_worker.py:ExecutionWorker._events_for_run` —— 生成过程中被取消时保留已登记的产物，并以 `error` 事件收尾；产物库未装配时直接报错。

## 列表与分页

### 入口

- `GET /harness/artifacts` —— 列出登记产物
- `python_backend/modules/artifacts/store.py:ArtifactStore.list` —— 条件查询与分页
- `frontend/src/modules/artifacts/ArtifactList.vue` —— 控制台「产物与存储」页的列表

### 行为

- 查询参数：`runId`（按运行过滤）、`owner`（按归属身份过滤，传空串即只取未登记归属的记录）、`limit`（1-200，默认 100）、`offset`（≥0，默认 0）。
- 排序固定为 `created_at DESC, rowid DESC`；`total` 是同一条件下的总数，不随分页变化。
- 返回项经 `artifact_metadata` 收敛，不暴露 `storage_key`；每条附带 `ageDays`（登记至今的整天数）。
- 磁盘上存在但没登记过的文件不出现在列表里，列表只反映登记记录。

### 关键实现

- `python_backend/modules/artifacts/store.py:ArtifactStore.list` —— `limit` 再被夹到 `[1, 200]`，`offset` 夹到非负；`age_days` 对无法解析的时间戳按 0 天算（视为新登记）。

## 产物下载

### 入口

- `GET /harness/artifacts/{artifact_id}/download` —— 下载产物
- `python_backend/api/routers/artifacts.py:_local_file` —— local 后端的文件定位

### 行为

- 产物不存在返回 404；记录的存储后端与当前存储后端不一致返回 503（`产物所属存储当前未配置`）。
- local 后端走 `FileResponse`，按登记的 `content_type` 与文件名返回；响应头带 `Cache-Control: private, no-store` 与 `X-Content-Type-Options: nosniff`。
- minio 后端走对象存储读取流，64 KiB 分块转发，结束时释放连接；`Content-Disposition` 用 UTF-8 百分号编码文件名。
- 对象存储报错按错误码分流：对象不存在类（`NoSuchKey`/`NoSuchObject`/`NoSuchBucket`）返回 404，其它返回 503，响应体不回显存储方细节。

### 关键实现

- `python_backend/api/routers/artifacts.py:_local_file` —— 解析后的路径必须落在 `DODO_GENERATED_DIR` 之内；路径或其任一父级是符号链接即判 404。

## 文本预览

### 入口

- `GET /harness/artifacts/{artifact_id}/preview` —— 读取产物文本内容
- `python_backend/api/routers/artifacts.py:_is_previewable` —— 可预览类型判定

### 行为

- 可预览类型：`text/*`、`application/json`、`application/xml`、`application/xhtml+xml`、`application/javascript`、`application/yaml`、`application/x-yaml`，以及 `+json` / `+xml` 结尾的类型；其余返回 415。
- 只支持 local 后端：对象存储登记的产物返回 503（`对象存储暂不支持预览`）。
- 最多读 20000 字符（字节上限 80004），超出时 `truncated` 为 true，只返回前 20000 字符；内容按 UTF-8 解码，非法字节以替换字符兜底。
- 预览与下载同样先过归属校验。

## 归属身份校验

### 入口

- `python_backend/api/routers/artifacts.py:_check_owner` —— 下载与预览前的归属比对
- `python_backend/api/routers/artifacts.py:_owner_header_reader` —— 解析归属请求头名（受保护入口：`GET /harness/artifacts/{artifact_id}/download` 与 `.../preview`）

### 行为

- 记录的 `owner` 为空（历史登记）时**一律拒绝**：返回 403「产物未登记归属，无法访问」；有 `owner` 时请求必须带归属身份，缺失或空白返回 403，值不匹配返回 403。
- 归属值可以来自请求头或下载链接上的 `owner` 参数：请求头名取自 Harness 设置 `artifactOwnerHeader`，默认 `X-Harness-Owner`（设置改过名时默认名仍然兼容）；403 响应只说明缺哪个请求头或身份不匹配，不回显记录里的归属值。
- `artifact_metadata` 生成的下载链接会带上 `?owner=<归属值>`，聊天里的直接下载链接因此仍可用。

### 关键实现

- `python_backend/api/routers/artifacts.py:_owner_header_reader` —— 设置库按需创建并缓存实例，每次读取都取最新设置，改设置无需重启。

## 记录删除与过期清理

### 入口

- `python_backend/modules/artifacts/store.py:ArtifactStore.delete` —— 删除单条登记
- `python_backend/modules/artifacts/store.py:ArtifactStore.list_expired` / `ArtifactStore.expire` —— 按保留天数挑出并删除过期登记
- `POST /harness/artifacts/cleanup` —— 手动清理过期产物
- `python_backend/modules/retention/maintenance.py:purge_artifacts` —— 后台保留窗口清理

### 行为

- `delete` 只删登记行并返回是否命中，不碰磁盘文件；`expire(older_than_days)` 删除登记年龄 ≥ 天数的记录，只返回被删的 `artifact_id` 列表，文件留在原地。
- `POST /harness/artifacts/cleanup` 请求体为 `{"retentionDays": n, "deleteFiles": bool}`；`retentionDays` 小于 1 返回 400；返回 `removed` 计数与 `artifactIds` 列表。
- `deleteFiles` 为真时只删 local 后端记录对应的本地文件，单个文件失败不影响其它；对象存储文件一律不删。
- 后台保留循环按 `artifactRetentionDays`（默认 30）删除 `created_at` 早于截止时间的登记行，同样不删文件。

### 关键实现

- `python_backend/modules/retention/maintenance.py:run_retention` —— 产物窗口取 `artifactRetentionDays`，未配置时沿用 `auditRetentionDays`。
- `python_backend/fastapi_app.py:lifespan` —— 保留循环注册 `data/artifacts.db` 路径，默认每小时执行一次。

## 数据与存储

- 登记库：`DODO_DATA_DIR/artifacts.db`（SQLite），表 `run_artifact`。
- 字段：`artifact_id`（uuid4 hex）、`run_id`、`name`、`size`、`sha256`、`content_type`、`storage_backend`、`storage_key`、`owner`、`created_at`；唯一约束 `(run_id, storage_backend, storage_key)`，索引 `(run_id, created_at)`。
- 老库缺 `owner` 列时在构造阶段补齐，历史记录归属为空串；归属为空的记录现在会被拒绝下载，需要人工补归属后重试。
- 产物文件：local 后端落在 `DODO_GENERATED_DIR`（默认 `data/generated`）之下；minio 后端对象名为 `ppt/<run_id>/<文件名>`。
- 相关配置项：`DODO_DATA_DIR`、`DODO_GENERATED_DIR`、`DODO_FILE_STORAGE_BACKEND`；Harness 设置项 `artifactRetentionDays`、`artifactOwnerHeader`。

## 接口清单

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/harness/artifacts` | 列出登记产物（runId/owner 过滤 + 分页） |
| `GET` | `/harness/artifacts/{artifact_id}/download` | 下载产物（local 文件流 / minio 对象流代理） |
| `GET` | `/harness/artifacts/{artifact_id}/preview` | 预览文本类产物内容 |
| `POST` | `/harness/artifacts/cleanup` | 按保留天数清理过期登记，可选删除本地文件 |

## 边界与已知限制

- 没有对外的单条删除接口：`ArtifactStore.delete` 只在库内可用，且删登记不会删文件。
- 预览只支持 local 后端与文本类类型；对象存储产物无法预览。
- 下载与预览的归属校验依赖客户端自带请求头，不是登录态鉴权；`owner` 为空的旧产物对所有请求放行。
- 前端 `frontend/src/modules/artifacts/api.js` 把归属请求头名写死为 `X-Harness-Owner`，在 Harness 设置里改 `artifactOwnerHeader` 后前后端不一致。
- 清理不删对象存储文件：cleanup 与后台保留循环都只处理登记行，minio 对象随存储自身生命周期。
- 两套过期口径不同：`cleanup` 按整天数判定（`ageDays ≥ retentionDays`），后台保留循环按时间戳与截止时间比较。
- 只有 ppt 代理链路会自动登记产物；`register_legacy_artifact` 目前仅被测试使用，队列外产出没有自动登记入口。
