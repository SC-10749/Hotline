# 审批与机器治理（governance）

> 模块路径：`python_backend/modules/governance/`（目录内只有测试，真实实现落在 `python_backend/infrastructure/governance_store.py`、`python_backend/infrastructure/notification_store.py`、`python_backend/modules/execution/tools.py`）
> 前端对应：无独立前端模块（`frontend/src/modules/governance/` 不存在）；界面在 `frontend/src/HarnessApp.vue` 的「运行治理 / 机器与运行时」「待审批」分区，接口封装在 `frontend/src/api.js`
> 状态：现状说明（以代码为准，冲突时以代码为准并修正本文档）

## 审批请求的创建与过期

### 入口

- `POST /harness/approvals` —— 由控制台或外部系统登记一条待审批请求。
- `python_backend/infrastructure/governance_store.py:GovernanceStore.create` —— 写入 `harness_approval` 行。
- `python_backend/modules/execution/tools.py:enforce_approval` —— 执行侧在工具调用前自动创建审批请求。

### 行为

- 请求字段：`runId`（必填）、`tool`（必填）、`risk`（默认 `high`）、`detail`（默认空串）、`timeoutSeconds`（可选，1~86400）。
- 生成 `request_id` 形如 `approval-{12位hex}`；状态初值 `pending`，`expires_at` 按 `timeout_seconds` 计算（存储层缺省 3600 秒，接口层缺省取设置项 `approvalTimeoutSeconds`）；`operator` 字段初始为空，实际裁决人由裁决动作写入。
- 过期是**惰性**的：`GET /harness/approvals`、`GET /harness/approvals/{request_id}`、审计导出每次先调 `GovernanceStore.expire_pending`，把 `expires_at` 已过的 `pending` 行置为 `expired` 并写 `decided_at`。
- 状态取值只有 `pending` / `approved` / `rejected` / `expired`。

### 关键实现

- `python_backend/infrastructure/governance_store.py:GovernanceStore._initialize` —— 建表并按需补 `expires_at`、`operator` 列（旧库用 `ALTER TABLE` 迁移）。

## 工具调用的审批等待与放行/拒绝

### 入口

- `python_backend/modules/execution/tools.py:prepare_tool_call` —— 工具执行前的统一入口：Agent 工具权限 → 参数校验 → 审批链。
- `python_backend/modules/execution/tools.py:enforce_approval` —— 阻塞等待人工裁决。

### 行为

- 触发条件：登记记录的 `approval_policy` 为 `always` 或 `required`；当 `approval_policy != 'always'` 时还要求 `risk == 'high'`。其余组合直接放行。
- 全局开关：环境变量 `HARNESS_APPROVAL_ENFORCE`（默认开启），取值 `0/false/no/off` 时整条审批链跳过；没有运行上下文（`run_id` 为空）时不阻塞、不建请求。
- 等待时长取 `harness_settings.defaultTimeoutSeconds`，读不到或非正数时回落到 `DEFAULT_APPROVAL_WAIT_SECONDS = 120` 秒；轮询间隔 `APPROVAL_POLL_SECONDS = 0.5` 秒。
- 裁决结果：`approved` 继续执行工具；`rejected` 抛 `ValueError`「工具审批被拒绝，未执行该工具」；`expired` 或超过等待上限抛 `ValueError`（提示等待超时秒数），工具均不执行。
- 审批明细只写参数**键名与类型**（`_summarize_arguments` 截断 20 个键），不写参数值。

### 关键实现

- `python_backend/modules/execution/tools.py:_approval_wait_seconds` —— 从设置库 `harness-settings.db` 的 `harness_settings` 行读 `defaultTimeoutSeconds`。
- `python_backend/modules/execution/tools.py:_expired` —— 按 `%Y-%m-%dT%H:%M:%SZ` 解析 `expires_at` 判断是否过期。
- `python_backend/modules/execution/worker.py` 通过 `set_current_run_id` 登记运行号（线程隔离），工具审批请求据此关联到具体运行。

## 单条裁决与重复裁决冲突

### 入口

- `POST /harness/approvals/{request_id}/decision` —— 对一条请求做人工裁决。
- `python_backend/infrastructure/governance_store.py:GovernanceStore.decide` —— 裁决的唯一实现。

### 行为

- 决定值只接受 `approved` / `rejected`，其它值抛 `ValueError`，路由层转 HTTP 400；请求不存在返回 HTTP 404。
- 只有 `pending` 能被裁决；已裁决或已过期的请求抛 `ApprovalStateError`：过期报「该审批请求已超时过期」，其它报「该审批请求已决定」，路由层转 HTTP 409。
- 裁决写入 `status`、`reason`（上限 500 字符）、`operator`（缺省 `harness-operator`）、`decided_at`；`UPDATE` 条件带 `status='pending'`，并发裁决只有一条能成功。
- 路由在裁决成功后触发通知记录（见「审批决定通知」）。

## 批量裁决的失败隔离

### 入口

- `POST /harness/approvals/decide-batch` —— 一次裁决多条请求。

### 行为

- 请求体：`requestIds`（列表，默认空）、`decision`、`reason`（上限 500 字符）、`operator`（可选）。
- 逐条裁决，单条失败不影响其它条目：状态冲突、非法决定值、请求不存在都进 `failed` 列表，元素为 `{requestId, reason}`。
- 成功条目进 `items`，每条裁决后同样触发通知记录。
- 响应恒为 HTTP 200，失败信息通过 `failed` 表达。

## 审计导出

### 入口

- `GET /harness/approvals/audit` —— 导出审批审计 CSV。

### 行为

- 先执行一次过期标记，再导出；可选 `status` 过滤。
- 列固定为 `request_id, run_id, tool, risk, status, reason, operator, created_at, decided_at`，不含 `detail`。
- 输出带 UTF-8 BOM（`\ufeff`），`content-type` 为 `text/csv; charset=utf-8`，`Content-Disposition` 为 `attachment; filename="harness-approvals.csv"`；前端通过 `frontend/src/api.js:harnessApprovalAuditUrl` 直接下载。

## 审批决定通知与 webhook 外发

### 入口

- `python_backend/api/routers/governance.py:notify_decision` —— 裁决后的通知分发。
- `GET /harness/approvals/notifications` —— 查询通知记录（可选 `requestId`、`limit` 1~500）。

### 行为

- 开关：设置项 `approvalNotifyEnabled` 为假时完全不产生通知；通知存储未接入时静默跳过。
- 先写一条 `channel='local'`、`status='recorded'` 的本地记录。
- 配置了 `notificationWebhookUrl` 时再 POST 一次 JSON，并补写一条 `channel='webhook'` 的记录：2xx 记 `delivered`，否则记 `failed` 并在 `detail` 写失败原因。
- webhook 失败**不阻断裁决**：HTTP 错误码记为 `HTTP {code}`，其它异常记异常类名，裁决结果照常返回 200。
- 通知载荷字段：`event`、`requestId`、`runId`、`tool`、`risk`、`decision`、`operator`、`reason`（截断 200 字符）、`decidedAt`。
- 通知只由 HTTP 裁决接口触发；直接调用 `GovernanceStore.decide` 不产生通知记录。

## 机器节点清单与心跳

### 入口

- `GET /harness/machines` —— 列出运行时节点。
- `python_backend/modules/execution/store.py:ExecutionStore.heartbeat_worker` —— Worker 周期心跳写库。
- `python_backend/modules/execution/store.py:ExecutionStore.list_workers` —— 节点清单读取。

### 行为

- 心跳写入 `last_seen`、`current_run_id`、`capacity`、`runtime_version`；心跳若节点原状态是 `draining` 则保持 `draining`，否则回到 `online`。
- 节点状态取值 `online` / `draining` / `offline`；`last_seen` 超过 `worker_stale_seconds`（默认 15 秒）即判为 `offline`。Worker 空闲时约每 5 秒心跳一次，执行中每次心跳同时续租运行（`heartbeat_run`）。
- 治理路由通过注入的 `workers()` 取数；未接入时返回空列表。

## 节点错误日志与排空（drain）

### 入口

- `GET /harness/machines/{worker_id}/errors` —— 读取节点错误日志。
- `POST /harness/machines/{worker_id}/drain` —— 切换节点排空状态（body `{"draining": true|false}`）。
- `python_backend/modules/execution/store.py:ExecutionStore.list_worker_errors` / `set_worker_state` —— 实现入口。

### 行为

- 错误日志只返回该节点 `error` 非空的运行，按 `finished_at` 倒序，`limit` 取 1~200；每条附带该运行的错误事件（内容截断 500 字符，并带事件工具名）。
- 排空：`draining=true` 置状态为 `draining`，`draining=false` 置回 `online`；节点不存在返回 HTTP 404，未接入状态接口时返回 HTTP 503。
- 排空状态会随心跳保留（见上），但**领任务查询不按节点状态过滤**，因此排空只是状态标记与展示。

## 数据与存储

- `data/harness-governance.db`（SQLite，`GovernanceStore`）：表 `harness_approval`（审批主表）、`release_gate`、`release_record`、`release_observation`、`release_config`（后四张属发布治理模块，治理路由只用第一张）。
- `data/harness-notifications.db`（SQLite，`NotificationStore`）：表 `harness_notification`（通知记录），按 `(request_id, created_at)` 建索引；节点与运行数据在执行库的 `execution_worker` / `execution_run` / `execution_event` 表（`python_backend/modules/execution/store.py`）。
- 保留策略：`python_backend/modules/retention/maintenance.py:purge_approvals` 按设置项 `auditRetentionDays` 删除**非 pending** 且过期的审批行；`pending` 行永不清理。

## 接口清单

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/harness/machines` | 列出运行时节点及状态 |
| `GET` | `/harness/machines/{worker_id}/errors` | 节点错误日志 |
| `POST` | `/harness/machines/{worker_id}/drain` | 切换节点排空状态 |
| `GET` | `/harness/approvals` | 审批列表（可按 `status` 过滤） |
| `GET` | `/harness/approvals/audit` | 审批审计 CSV 导出 |
| `GET` | `/harness/approvals/notifications` | 通知记录查询 |
| `GET` | `/harness/approvals/{request_id}` | 单条审批详情 |
| `POST` | `/harness/approvals` | 创建审批请求 |
| `POST` | `/harness/approvals/{request_id}/decision` | 单条裁决 |
| `POST` | `/harness/approvals/decide-batch` | 批量裁决 |

## 边界与已知限制

- 工具登记接口只接受 `approval_policy` 取 `risk-based` 或 `always`，而 `enforce_approval` 判定的是 `always`/`required`：`risk-based` 的高风险工具实际不会触发审批。
- `python_backend/modules/execution/tools.py:enforce_approval` 里 `run_id or _current_run_id` 引用了模块内不存在的名字（应为 `current_run_id()`），缺 `run_id` 时会抛 `NameError` 而不是「跳过审批」。
- 审批有效期与执行侧等待上限用同一个超时值：接口创建走 `approvalTimeoutSeconds`（默认 3600），执行侧等待走 `defaultTimeoutSeconds`（默认 900，缺省回落 120），两个设置项互不相通。
- 过期标记只在读接口触发，没有后台定时过期任务；未读的过期请求在库里仍是 `pending`。
- 排空状态只落库与展示，领任务查询不按状态过滤，节点仍会领取新运行。
- webhook 只有一次投递，不重试、不排队；失败只留 `failed` 记录。
- 接口创建的 `detail` 是调用方传入的自由文本，不做脱敏；执行侧自动生成的 `detail` 只含键名与类型。
- 通知记录无分页游标，只有 `limit` 上限；审批列表无分页。
