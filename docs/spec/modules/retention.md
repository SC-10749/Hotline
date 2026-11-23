# 数据保留与清理（retention）

> 模块路径：`python_backend/modules/retention/`（`maintenance.py` 清理逻辑，`test_retention.py` 用例）
> 前端对应：无独立前端模块；保留窗口只出现在 `frontend/src/HarnessApp.vue` 的 Harness 设置表单（「审计保留天数」输入框）
> 状态：现状说明（以代码为准，冲突时以代码为准并修正本文档）

## 运行历史与事件清理

### 入口

- `python_backend/modules/retention/maintenance.py:purge_execution_history` —— 按窗口删除执行库里的终态运行与过期事件
- `python_backend/modules/retention/test_retention.py:RetentionTest.test_execution_history_keeps_recent_rows` —— 只删过期行、保留新行

### 行为

- 目标库是 `DODO_DATA_DIR/execution.db`，涉及表 `execution_run` 与 `execution_event`。
- 运行行只删终态：状态为 `completed`/`failed`/`cancelled` 且 `created_at` 早于截止时间；`queued` 与 `running` 一直保留。
- 事件行单独按 `created_at` 删，不看运行状态：长跑运行的旧事件会被清掉，运行行仍在。
- 先删事件再删运行，返回 `{'runs': n, 'events': n}`；库文件不存在时返回零计数，不建库、不报错。
- 窗口天数小于 1 时按 1 天算。

### 关键实现

- `python_backend/modules/retention/maintenance.py:_cutoff` —— 截止时间是 UTC 字符串 `%Y-%m-%dT%H:%M:%SZ`，与执行库写入的时间戳格式一致。
- `python_backend/modules/retention/maintenance.py:_connect` —— sqlite 连接超时 30 秒；连接异常时先关连接再抛。

## 审批记录清理

### 入口

- `python_backend/modules/retention/maintenance.py:purge_approvals` —— 删除已裁决的审批记录
- `python_backend/modules/retention/test_retention.py:RetentionTest.test_pending_approvals_are_never_purged` —— 未裁决记录不被清

### 行为

- 目标库是 `DODO_DATA_DIR/harness-governance.db`，表 `harness_approval`。
- 删除条件是 `status != 'pending'` 且 `created_at` 早于截止时间：状态为 `pending` 的行永远不会被本模块删掉。
- 审批状态取值 `pending`/`approved`/`rejected`/`expired`；超时未裁决的请求由治理库改成 `expired`，之后按窗口正常清理。
- 判定只看 `created_at`，裁决时间 `decided_at` 不参与；返回删除条数。

### 关键实现

- `python_backend/infrastructure/governance_store.py:GovernanceStore.expire_pending` —— 把超时的 `pending` 改判为 `expired`。
- `python_backend/modules/retention/maintenance.py:purge_approvals` —— 用「不等于 pending」而不是白名单，新增裁决状态不会被误清。

## 产物登记过期清理

### 入口

- `python_backend/modules/retention/maintenance.py:purge_artifacts` —— 按产物窗口删除过期登记
- `python_backend/modules/retention/test_retention.py:RetentionTest.test_artifact_registrations_expire` —— 过期登记被删、新登记保留
- `POST /harness/artifacts/cleanup` —— 手动清理接口，归 `modules/artifacts` 所有

### 行为

- 目标库是 `DODO_DATA_DIR/artifacts.db`，表 `run_artifact`。
- 删除 `created_at` 早于截止时间的全部登记行，不看运行状态、不看产物是否被引用；只删登记行，磁盘文件与对象存储对象都不动。
- 窗口取 `artifactRetentionDays`，与审计窗口分开，未配置时沿用 `auditRetentionDays`。
- 手动 cleanup（`ArtifactStore.expire`）按整天数判定，后台循环按时间戳比较，两者口径不同。

## 定时清理循环与保留窗口来源

### 入口

- `python_backend/modules/retention/maintenance.py:start_retention_loop` —— 启动后台清理线程
- `python_backend/modules/retention/maintenance.py:run_retention` —— 按设置里的窗口执行清理
- `python_backend/fastapi_app.py:lifespan` —— 进程启动时注册循环，退出时 `retention_stop.set()`
- `GET /harness/settings` / `PUT /harness/settings` —— Harness 设置读写
- `frontend/src/HarnessApp.vue` —— 设置表单里的「审计保留天数」

### 行为

- 守护线程名 `harness-retention`，默认间隔 3600 秒；启动后不立即执行，先等满一个间隔。
- 每轮通过 `settings_provider()` 现场读设置，改设置不需要重启，下一个间隔生效。
- 循环内异常被全部吞掉（`except Exception: pass`），不写日志、不重试，下一轮照常跑。
- 停止靠 `threading.Event`：`set()` 后当前等待结束、循环退出。
- 只装配三个库路径：`execution.db`、`harness-governance.db`、`artifacts.db`；路径里没有的键直接跳过。
- 循环只在 FastAPI 网关进程里跑，执行 Worker 进程内没有这个循环。
- 窗口来自 Harness 设置项，不是环境变量：`auditRetentionDays`（审计与运行历史）、`artifactRetentionDays`（产物登记），默认 30、范围 1-3650，缺省或 0 值兜底为 30。
- 设置存在 `DODO_DATA_DIR/harness-settings.db` 的 `harness_settings` 表，保存时只保留默认键集合里的字段。
- 前端保存时整体回传服务端返回的设置对象；表单上没有产物保留天数输入框。

### 关键实现

- `python_backend/fastapi_app.py:lifespan` —— 用 `settings_store.get` 作为设置来源，退出时与其它后台循环一起回收。
- `python_backend/infrastructure/settings_store.py:DEFAULT_HARNESS_SETTINGS` —— 默认值与允许保存的键集合。

## 清理与其它模块的边界

### 入口

- `python_backend/modules/retention/maintenance.py:run_retention` —— 只处理 `paths` 里给出的键
- `python_backend/modules/artifacts/store.py:ArtifactStore.expire` —— 产物模块自带的过期删除

### 行为

- 本模块只删记录行：不删磁盘文件、不删对象存储对象、不动隔离工作目录。
- 只覆盖 execution、governance、artifacts 三个库；通知、评测、调度、机器人、记忆等库没有保留清理。
- 删除计数只作为函数返回值，不落库、不上报、不进事件流；产物有两条清理路径（后台循环、手动 cleanup），窗口来源相同、判定口径不同。

## 数据与存储

- `DODO_DATA_DIR/execution.db`：表 `execution_run`、`execution_event`。
- `DODO_DATA_DIR/harness-governance.db`：表 `harness_approval`。
- `DODO_DATA_DIR/artifacts.db`：表 `run_artifact`。
- 保留窗口存储：`DODO_DATA_DIR/harness-settings.db` 的 `harness_settings` 表。
- 相关配置项名称：`DODO_DATA_DIR`、`DODO_GENERATED_DIR`；Harness 设置项 `auditRetentionDays`、`artifactRetentionDays`。

## 接口清单

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/harness/settings` | 读取保留窗口等 Harness 设置 |
| `PUT` | `/harness/settings` | 修改保留窗口等 Harness 设置 |
| `POST` | `/harness/artifacts/cleanup` | 手动清理过期产物登记，可选删本地文件 |

本模块自身不提供 HTTP 路由，以上是它读写与依赖的关联接口。

## 边界与已知限制

- 只按 `created_at` 判定过期；审批的裁决时间 `decided_at` 不参与。
- 事件删除不看运行状态，长跑运行的旧事件会被清掉。
- 审批表时间戳默认是 SQLite `CURRENT_TIMESTAMP`（空格分隔的 `YYYY-MM-DD HH:MM:SS`），与截止时间的 `T`/`Z` 格式做字符串比较时，同一天的记录一律算「早于截止时间」：审批清理实际按整天生效，最多提前约 24 小时。
- 清理只回收登记行，不回收磁盘空间；产物文件与对象存储对象要靠手动 cleanup 或存储自身生命周期。
- 循环间隔固定 3600 秒，不可配置；启动后首个周期要等满一小时才执行。
- 循环内异常被静默吞掉，清理失败没有日志也没有告警。
- 前端设置表单只有「审计保留天数」，产物保留天数等设置项没有输入框。
- 通知、评测、调度、机器人、记忆等库没有保留窗口，数据会一直累积。
