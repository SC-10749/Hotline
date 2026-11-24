# 执行与运行编排（execution）

> 模块路径：`python_backend/modules/execution/`
> 前端对应：`frontend/src/modules/execution/`
> 状态：现状说明（以代码为准，冲突时以代码为准并修正本文档）

## 引擎分层（S-007 拆分后）

### 入口

- `python_backend/modules/execution/engine.py:AgentEngine` —— 编排层：构造、事件工厂、上下文装配、`stream()` 主流程。
- `python_backend/modules/execution/tasks.py:TaskManager` —— 任务锁：会话级互斥，Redis 模式下广播停止。
- `python_backend/modules/execution/model_client.py:ModelClient` —— 模型调用适配层：一次性与流式对话、token 用量统计。
- `python_backend/modules/execution/grounding.py:GroundingMixin` —— 证据落地：检索链路选择、文档/工作区召回、多跳证据扩展。
- `python_backend/modules/execution/gates.py:GateMixin` —— 意图门闸与需求级门闸。
- `python_backend/modules/execution/answer_flow.py:AnswerFlowMixin` —— 通用回答流程：提示组装、上下文装配、降级回答。
- `python_backend/modules/execution/skill_flow.py:SkillFlowMixin` —— 技能智能体执行流。
- `python_backend/modules/execution/constants.py` —— 门闸标记、需求交接标记与推荐项文案。

### 行为

- `AgentEngine` 由四个 mixin 组合而成，对外方法签名与 SSE 事件格式不变；`from python_backend.modules.execution.engine import AgentEngine, TaskManager, ModelClient` 等既有导入继续可用。
- `python_backend/agents.py` 仍是兼容入口，仍等价于 `modules.execution.engine`。
- mixin 只通过 `self` 访问已有协作者（模型、向量库、存储、文档），不直接依赖彼此。
- 打桩路径随代码位置变化：技能流用 `python_backend.modules.execution.skill_flow.run_agent` 与 `...skill_flow.build_chat_model`，不再从 `engine` 打桩。

## 执行队列与幂等入队

### 入口

- `python_backend/modules/execution/store.py:ExecutionStore.enqueue` —— 把一次运行请求写入 SQLite 队列。
- `python_backend/application/execution_service.py:ExecutionApplicationService.submit_or_resume` —— 带游标恢复的提交入口，`/agent/*/stream` 复用。

### 行为

- 活跃状态只有 `queued` 与 `running`，终态为 `completed` / `failed` / `cancelled`（`store.py:ACTIVE_STATUSES`、`TERMINAL_STATUSES`）。
- 同一 `(conversation_id, slot)` 下已有活跃运行，且 `agent`、`query`、`file_id`、`workspace_id`、`agent_id` 全同，则直接返回既有运行（幂等入队）；参数有差异抛 `ActiveExecutionError`，路由层转 HTTP 409。
- 查重与写入在同一个 `BEGIN IMMEDIATE` 事务内完成，并发窗口里不会出现两条活跃运行。
- 恢复路径 `find_run_by_event` 按 `conversation_id + agent + query + file_id + event_id` 反查既有运行；`event_id <= 0` 不做恢复。
- 没有存活 Worker 时 `submit_or_resume` / `create` / `create_parallel` / `retry_run` 抛 `WorkerUnavailableError`，路由层转 HTTP 503。
- 应用层用例只依赖 `ExecutionQueue` 协议，存储细节留在端口后面；`python_backend/infrastructure/queue/sqlite.py:SqliteExecutionQueue` 是 `ExecutionStore` 的薄适配，Worker 与网关共用同一个 SQLite 库。

## 活跃唯一索引与子任务 slot

### 入口

- `python_backend/modules/execution/store.py:ExecutionStore._initialize` —— 建库与建唯一索引。
- `python_backend/modules/execution/store.py:ExecutionStore.enqueue_parallel` —— 子任务按 slot 批量入队。

### 行为

- 唯一索引 `uq_execution_active_slot ON execution_run(conversation_id, slot) WHERE status IN ('queued','running')` 是部分索引，只约束活跃运行。
- 普通对话 `slot` 为空串，语义不变：同一会话同时只允许一条活跃运行；并发子任务各占一个 `slot`（`sub-0`、`sub-1`……），互不排斥。
- 索引依赖 `slot` 列，迁移顺序是「先补列、再建索引」；旧库通过 `_ensure_columns` 补齐 `agent_id`、`workspace_id`、`parent_run_id`、`slot`、`workspace_root` 等列，不丢历史行。
- `python_backend/modules/execution/parallel.py:task_key_for` 派生任务键：`{conversation_id}#{slot}`，普通对话仍返回 `conversation_id`。

## 并行子任务派发与 fan-in 流

### 入口

- `POST /execution/runs/parallel` —— 一次派发多个子任务；`GET /execution/parallel/stream` —— 多运行合并事件流。
- `python_backend/modules/execution/parallel.py:allocate_task_workspace` —— 分配子任务隔离目录。

### 行为

- 请求体为 `conversationId`、`parentRunId`、`tasks[]`；每个任务含 `query`（必填）、`agent`（默认 `chat`）、`agentId`、`workspaceId`；任务列表不能为空，一次最多 16 个，`workspaceId` 查不到工作区返回 404。
- 入队在单个事务内完成：任一 slot 冲突则整批回滚，不留半批运行；空 `query` 报「第 N 个子任务缺少内容」。
- 每个子任务按 `sub-{index}` 分配 slot，`parent_run_id` 记录父运行；`list_children(parent_run_id)` 按 slot 排序返回子任务。
- 合并流把多个运行的事件并到一条 SSE：事件 `id` 为 `{runId}:{eventId}`，数据体为 `{"runId","eventId","event"}`；所有运行进入终态后发 `event: done`。
- 隔离目录按 worktree → copy → outputs-only 三级降级，落在 `data/parallel/<父运行或会话>/<slot>/`；分配结果写入 `.task-workspace.json`，重复分配时复用既有目录。

### 关键实现

- `python_backend/workers/execution_worker.py:ExecutionWorker._prepare_workspace` —— 解析工作区源目录、分配隔离目录、把 `workspace_root` 写回运行记录，并发一条 `policy` 事件说明隔离模式。
- `python_backend/runtime/agent_runtime.py:AgentEngineRuntime.stream_run` —— 子任务用 `{conversation_id}#{slot}` 注册任务锁，且 `persist_history=False` 不写父会话历史；`frontend/src/modules/execution/ParallelPanel.vue` 是对应派发面板。

## 事件持久化与游标回放

### 入口

- `python_backend/modules/execution/store.py:ExecutionStore.append_event` / `events_after` —— 写入与游标读取。
- `GET /execution/runs/{run_id}/events`、`GET /execution/runs/{run_id}/stream` —— 拉取与实时回放；`python_backend/api/routers/observability.py:create_observability_router` 提供筛选、指标与导出。

### 行为

- 事件落库到 `execution_event`（`event_id` 自增、`event_json` 原文、`created_at`）；`events_after(run_id, event_id)` 只返回 `event_id >` 游标的记录。
- 级别由 `event_level` 推断：显式 `level` 优先，其次 `type == 'error'`、`tool_end` 且 `status == 'error'` 记为 `error`，其余为 `info`；筛选支持 `level`、`tool`、`hasError`、`since`、`until`、`type`。
- SSE 回放先读终态再取事件，避免终态切换瞬间漏掉最后一条事件；结束时发 `done`（envelope 模式）或 `[DONE]`；断线可用 `Last-Event-Id` 头带游标重连。
- 前端 `frontend/src/modules/execution/useRunEvents.js` 先 `GET .../events?after=` 补历史再接 EventSource，按 `event_id` 去重与排序，流结束后置 `complete`。
- 可观测导出走只读 SQLite 连接，支持 JSON/CSV 两种格式，时间参数必须是 ISO 格式。

## 取消、重试与运行终态

### 入口

- `POST /execution/runs/{run_id}/cancel`、`GET /agent/stop` —— 取消；`POST /execution/runs/{run_id}/retry` —— 重试。
- `python_backend/modules/execution/store.py:ExecutionStore.retry_run` —— 重试的存储实现。

### 行为

- 取消有两种粒度：`request_cancel_run(run_id)` 停单个运行；`request_cancel(conversation_id)` 停该会话下全部活跃运行（覆盖并发子任务这一批）。
- 排队中的运行立即置 `cancelled` 并补一条 `error` 事件「任务已停止」；运行中的只置 `cancel_requested=1`，由 Worker 监测到后停止任务收尾。
- 重试只对终态运行开放：复制 `conversation_id`、`agent`、`query`、`file_id`、`agent_id`、`workspace_id`，并保留 `slot`、`parent_run_id`、`workspace_root`，避免子任务重试后退化成普通运行。
- 重试前检查同 `(conversation_id, slot)` 是否已有活跃运行，有则抛 `ActiveExecutionError`，路由层 409「只有已结束的运行可以重试」。
- 终态判定：`complete` 事件 → `completed`；`error` 事件 → 有取消标记时 `cancelled` 否则 `failed`；未收到终态事件 → `failed`（`execution ended without terminal event`）。
- `ExecutionStore.finish` 只在 `queued`/`running` 状态下改写终态，重复调用不覆盖已完成运行；`is_cancel_requested` 供 Worker 轮询。

## Worker 领取、租约与心跳

### 入口

- `python -m python_backend.modules.execution.worker` —— Worker 进程入口（`modules/execution/worker.py` 为兼容转发）。
- `python_backend/workers/execution_worker.py:ExecutionWorker.run_once` / `run_forever` —— 领取与主循环；`python_backend/modules/execution/store.py:ExecutionStore.claim_next` —— 领取一条运行。

### 行为

- Worker 领取最老的 `queued` 运行，置 `running` 并写入 `worker_id`、`started_at`、`lease_until`（租约默认 45 秒）；领取在 `BEGIN IMMEDIATE` 事务内完成，多个 Worker 并发领取各拿不同运行。
- 领取时顺带清理过期租约：`running` 且租约过期的运行置 `failed`，并写入 `error` 事件「Worker 意外中断，任务未完成。请重新提交。」
- 运行期监控线程每 3 秒续租（`heartbeat_run`）并上报 Worker 心跳（`heartbeat_worker`，含 `capacity`、`runtime_version`、`state`）；超过 `worker_stale_seconds`（默认 15 秒）无心跳的 Worker 读取时显示 `offline`。
- `has_live_worker()` 决定网关是否接受新运行，没有存活 Worker 时接口返回 503。
- 运行策略来自 Harness 设置（`harness-settings.db`），实际生效项：`defaultTimeoutSeconds`（默认 900）、`defaultRetryCount`（默认 1）、`defaultTokenBudget`（默认 0，0 表示不限）、`isolation`（默认 `container`）。
- 超时按 `defaultTimeoutSeconds` 判定：写一条 `error` 事件并置 `failed`（错误 `timeout`）；token 累计超过 `defaultTokenBudget` 置 `failed`（错误 `token budget exceeded`）；失败后按 `defaultRetryCount` 为该会话自动重试，取消的运行不重试，重试运行收到 `retry` 事件并带 `retryRunId`。
- `isolation` 非空时运行开始会写一条 `policy` 事件，记录本次实际生效的工具白名单、Skill 绑定与模型路由。

### 关键实现

- `python_backend/modules/execution/engine.py:TaskManager` —— 进程内事件表 + 可选 Redis 互斥（`agent:task:<key>`，带 TTL），远程停止走 `agent:stop` 订阅。
- `python_backend/workers/execution_worker.py:ExecutionWorker._monitor_run` —— 心跳、取消检查、超时判定三合一；`build_worker` 组装依赖并从 Harness 设置读取运行策略。

## 工具调用治理：白名单、参数校验与审批

### 入口

- `python_backend/modules/execution/tools.py:prepare_tool_call` —— 工具执行前的统一入口。
- `python_backend/modules/execution/tools.py:set_tool_policy` / `set_current_run_id` —— 运行期上下文登记；`build_read_skill_tool` 是内置只读工具 `read_skill`。

### 行为

- 运行上下文放在 `threading.local()` 里而非模块全局变量：并发子任务各跑在独立线程，审批请求与工具白名单互不覆盖。
- 白名单：`blocked=True` 时该 Agent 任何工具调用被拒（「该 Agent 已停用，本次运行不允许调用工具」）；有 `allowed` 列表时列表外工具被拒。
- 参数校验按登记表 `harness_tool.input_schema`：必须是 JSON 对象、必填参数齐全、字段类型匹配（string/number/integer/boolean/object/array），不通过抛 `ValueError`；没有登记信息时保持现状，交给 LangChain 自带 schema 校验。
- 审批：登记项 `approval_policy` 为 `always` 或 `required` 且 `risk` 为 `high` 时阻塞等待人工审批；等待时长取 Harness 设置 `defaultTimeoutSeconds`，取不到用 120 秒，每 0.5 秒轮询一次。
- 审批拒绝抛「工具审批被拒绝」，过期或超时报错，两种情况工具都未执行；环境变量 `HARNESS_APPROVAL_ENFORCE`（默认开启）可整体关闭审批阻塞。
- 参数摘要只保留键名与类型不写值；预览脱敏由 `python_backend/modules/execution/trace.py:trace_preview` 负责（屏蔽密钥字段、Bearer、私钥、URL 与 IP）。

### 关键实现

- `python_backend/modules/execution/tools.py:validate_tool_arguments` 做登记表 schema 校验，`enforce_approval` 把审批请求写入治理库并轮询结果。

## 机器人作为工具（Agent as Tool）

### 入口

- `python_backend/modules/execution/agent_tool.py:build_agent_tools` —— 把登记的机器人装配成工具；`agent_tools_from_dir` 从运行数据目录读取登记与机器人。
- `python_backend/modules/execution/engine.py:AgentEngine._agent_tools` / `_run_agent_tool` —— 引擎侧挂载与执行。

### 行为

- 登记来源为 `harness_tool` 的 `source='agent'`，`input_schema.agent.bot_id` 指向机器人，工具入参沿用同一份 `input_schema`。
- 只有登记状态可用（不在 `disabled`/`stopped`/`offline`/`error`）且机器人自身 `enabled` 为真时才装配成工具。
- 调用时注入机器人人设（角色指令 + 绑定技能）跑一次对话；入参 `query` 必填，`clarification` 回传上一轮澄清的回答。
- 工具同步执行，澄清不阻塞：需求说不清时返回 `{"status":"needs_clarification","clarification":...}` 由调用方转述用户，用户作答后带 `clarification` 再调一次。
- 正常返回 `{"status":"ok","summary":...}`，异常返回 `{"status":"error","error":...}`；摘要超过 4000 字符被截断并标注。
- 子会话不落库：机器人作为工具的对话不写父会话历史；调用复用 `prepare_tool_call`，白名单、参数校验与审批链同样生效。
- `agent_tool.py:bot_persona` 把机器人定义转会话人设，`collect_events` 消费事件生成器取澄清、失败与答案。

## 定时调度器

### 入口

- `python_backend/modules/execution/scheduler.py:register_runner` / `run_once` / `stop_schedule_loop` —— 调度线程。
- `python_backend/api/routers/schedules.py:create_schedule_runner` —— 到点任务的扫描回调；`POST /harness/schedules/{task_id}/run` 手动立即执行。

### 行为

- 调度是模块级后台守护线程，扫描间隔 60 秒（`INTERVAL_SECONDS`）；应用 `lifespan` 启动时注册扫描回调，退出时 `stop_schedule_loop()` 停线程并清空回调列表。
- 单个任务失败不影响其它任务：扫描回调逐个执行并记告警日志。
- 到点判定按 `interval_minutes` 与 `last_run_at` 比较；每条任务用独立会话号 `schedule-{task_id}-{时间戳}` 提交一次运行。
- 提交走 `ExecutionApplicationService.create`，没有存活 Worker 时如实返回失败原因；任务增删改查在 `/harness/schedules` 下，页面写入与调度线程读同一张表；`submit_task_run` 提交并回写 `last_run_at`。

## 数据与存储

- 执行库：`settings.execution_db_path` 指向的 SQLite 库（WAL 模式），三张表——`execution_run`（运行记录）、`execution_event`（事件日志）、`execution_worker`（Worker 心跳与状态）。
- 运行记录关键字段：`run_id`、`conversation_id`、`agent`、`query`、`file_id`、`status`、`cancel_requested`、`worker_id`、`agent_id`、`workspace_id`、`parent_run_id`、`slot`、`workspace_root`、`lease_until`。
- 事件日志：`execution_event(event_id 自增, run_id, event_json, created_at)`，按 `(run_id, event_id)` 建索引；隔离工作区在 `data/parallel/<父运行或会话>/<slot>/`，含 `workspace/`（worktree 或副本）与 `outputs/`，标记文件 `.task-workspace.json`。
- 产物登记在产物库（`artifacts.db`，由 `modules/artifacts` 管理），execution 只负责发 `artifact` 事件；审批请求写入治理库（`harness-governance.db`），工具登记在 `harness-registry.db`，机器人定义在 `harness-bots.db`；工具运行态（`run_id`、工具白名单）是线程内状态，不落库。

## 接口清单

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/harness/overview` | 总览：今日运行、模型用量、待审批数 |
| `POST` | `/execution/runs` | 创建一次运行，返回运行记录 |
| `POST` | `/execution/runs/parallel` | 一次派发多个子任务（每任务一个 slot） |
| `GET` | `/execution/parallel/stream` | 多运行合并事件流（fan-in） |
| `GET` | `/execution/runs` | 运行列表，支持 `status`/`search`/分页 |
| `GET` | `/execution/runs/{run_id}` | 运行详情 |
| `GET` | `/execution/runs/{run_id}/events` | 游标拉取事件（`after`） |
| `GET` | `/execution/runs/{run_id}/stream` | SSE 事件回放（支持 `Last-Event-Id`） |
| `GET` | `/execution/runs/{run_id}/context` | 该运行的上下文快照事件 |
| `POST` | `/execution/runs/{run_id}/cancel` | 取消单个运行 |
| `POST` | `/execution/runs/{run_id}/retry` | 重试已结束的运行 |
| `GET` | `/agent/stop` | 按会话取消全部活跃运行 |
| `GET` | `/agent/chat/stream`、`/agent/file/stream`、`/agent/pptx/stream`、`/agent/deep/stream`、`/agent/skills/stream` | 各助手的事件流入口 |
| `GET` | `/harness/observability/runs`、`/harness/observability/runs/{run_id}` | 可观测运行列表与详情 |
| `GET` | `/harness/observability/runs/{run_id}/events` | 事件筛选（级别、工具、时间、类型） |
| `GET` | `/harness/observability/metrics`、`/harness/observability/trends` | 运行状态、错误与工具调用统计；运行与事件的时间分桶趋势 |
| `GET` | `/harness/observability/runs/{run_id}/export`、`/harness/observability/exports` | 单次与跨运行 Trace 导出（JSON/CSV） |
| `GET`/`POST`/`PUT`/`DELETE` | `/harness/schedules`、`/harness/schedules/{task_id}` | 定时任务增删改查 |
| `POST` | `/harness/schedules/{task_id}/run` | 立即执行一次定时任务 |

## 边界与已知限制

- 单主机存储：队列、事件与 Worker 心跳在同一个 SQLite 库里，靠 WAL 与 `BEGIN IMMEDIATE` 串行化，不做多机分布式调度；Worker 是必需的，只起网关没有 Worker 时 `/agent/*/stream` 与新建运行接口返回 503，`/health/ready` 显示 `executionWorker: unavailable`。
- 租约是兜底不是保证：Worker 崩溃后要等租约过期（默认 45 秒）才判定失败，期间不会自动重跑；一次并行派发最多 16 个子任务，超出返回 400，合并流始终一条连接，靠 `runIds` 参数传全部运行号。
- 隔离目录三级降级：worktree 失败退回复制，复制失败退化为只保留产物目录，降级信息写在 `policy` 事件里，产出目录与工作目录可能不是同一份内容。
- 审批阻塞依赖治理库与人工响应，等待时长受 Harness 设置 `defaultTimeoutSeconds` 影响；事件日志本模块只负责写入，保留窗口由 `modules/retention` 的清理循环负责。
- `engine.stream` 注册任务锁用 `task_key`（`modules/execution/engine.py`），但 `finally` 里用 `conversation_id` 释放，Worker 侧释放用 `task_key`；子任务场景下两处不完全一致，改任务锁语义时需一并核对。
- 交接口令由后端认定：`engine.stream` 开头用 `_is_tdd_handoff` 判定「按 TDD 把这些需求写成测试」时把本轮 agent 置为 `skills`，并用 SSE `agent` 事件告知前端，前端漏切模式也照走技能流。
