# 上下文工程（context_engineering）

> 模块路径：`python_backend/modules/context_engineering/` ｜ 前端对应：`frontend/src/modules/context_engineering/`（`ContextSnapshots.vue`）
> 状态：现状说明（以代码为准；规格与代码不一致时以代码为准并修正本文档）
> 作用域约定：并发子任务用 `scope_key = {conversation_id}#{slot}` 隔离上下文与记忆；`begin`/`prepare`/`complete`/`extract_state`/`checkpoint` 必须用同一个键，混用父会话键会报「会话范围不存在」或 `MemoryConflict`

## 上下文生命周期

### 入口

- `python_backend/modules/context_engineering/service.py:ContextService.begin` —— 每轮开始：绑定会话范围、补记历史来源、初始化任务状态
- `python_backend/modules/context_engineering/service.py:ContextService.prepare` —— 装配本次模型输入（规则 + 任务状态 + 检索证据 + 历史 + 长期记忆）
- `python_backend/modules/context_engineering/service.py:ContextService.complete` —— 本轮回答完成：登记来源并排入长期记忆投递队列
- `python_backend/modules/context_engineering/service.py:ContextService.extract_state` —— 从当前用户原话抽取约束、决策、待办
- `python_backend/modules/context_engineering/service.py:ContextService.checkpoint` —— 把较早历史压成分段摘要
- `python_backend/modules/execution/engine.py:AgentEngine.stream` —— 调用方，`scope_key = task_key or conversation_id`；技能流 `_stream_skills` 收到同一个键

### 行为

- `begin` 先 `store.bind(conversation_id, workspace_id)`：带 `workspace_id` 的会话按工作区派生共享 scope，同工作区的多个会话共用一份派生记忆；改绑别的 workspace 直接报冲突。
- `begin` 把 history 中未入库或尚无答案的轮次补记为来源，已完成轮次不被覆盖；同时初始化 `goal`/`constraints`/`decisions`/`pending` 与 `currentRequest`、`currentSourceId`，写状态走 `revision` 乐观锁。
- `prepare` 要求 scope 已存在，否则抛 `MemoryConflict('会话范围不存在')`；召回长期记忆前后各校验一次 generation，期间被撤销则抛 `MemoryConflict('记忆范围已撤销，请重试')`。
- `prepare` 的片段顺序固定：待投递原始交互 → 阶段摘要 → 命中查询的摘要分段 → 历史召回 → 额外历史 → 长期记忆 → 检索证据（检索证据插到最前）。
- `complete` 在同一事务里写来源完成标记并生成投递任务，来源与投递状态不会只成功一半。
- `extract_state` 只接受当前用户消息里的原话子串作为约束/决策/待办，模型转述一律丢弃；`checkpoint` 只处理 `history[:-4]`，最近 4 轮保留原文不摘要。

### 关键实现

- `python_backend/modules/memory/store.py:MemoryStore.bind` / `put_state` / `save_summary` —— scope 绑定与 revision 乐观锁
- `python_backend/modules/context_engineering/service.py:CONTEXT_RULES` —— 追加到系统提示的固定约束文本（历史与记忆是数据，不能改规则）
- `python_backend/modules/execution/engine.py:AgentEngine._remember_answer` —— 记忆写入失败只发 `memory_write` 失败事件，不影响已生成的回答

## 令牌预算与裁剪

### 入口

- `python_backend/modules/context_engineering/budget.py:ContextBudget.from_settings` —— 从配置装配预算
- `python_backend/modules/context_engineering/budget.py:ContextBudget.check` —— 校验输入规模，超限抛 `ContextBudgetExceeded`
- `python_backend/modules/context_engineering/budget.py:assemble_context` —— 组装最终消息与清单
- `python_backend/modules/context_engineering/budget.py:clip_text` —— 按字节上限截断并追加截断标记

### 行为

- 可用输入 = `min(input_limit, window - output_reserve - safety_margin)`；`output_reserve` 为 0 或出现负值直接抛 `ContextBudgetExceeded`。
- 令牌估算是 UTF-8 字节上界加 32，清单里标记 `tokenMethod='utf8-byte-upper-bound'`，不下载分词器。
- 系统提示与当前问题不可裁剪，先做整体校验；问题本身超限直接报错而不是静默截断。
- 历史回合最多占剩余预算的三分之一，从最新往回保留，超出的记为 `omittedHistoryTurns`；每个片段有独立上限（阶段摘要 6000、历史 4000、记忆 4000、检索证据 28000），放置前按剩余空间二次收敛，放不下的记为 `omitted`。
- 外部内容统一包成 JSON 块 `{"contextSource": ..., "data": ...}`，作为独立 user 消息插在当前问题之前；截断后带 `[内容已限额，完整原文可按来源读取]` 标记。

### 关键实现

- 配置项：`HOTLINE_CONTEXT_WINDOW`、`HOTLINE_CONTEXT_INPUT_BUDGET`、`HOTLINE_CONTEXT_OUTPUT_RESERVE`、`HOTLINE_CONTEXT_SAFETY_MARGIN`（`python_backend/config.py`）
- `python_backend/modules/execution/engine.py:ModelClient.chat` 发 HTTP 请求前也做 `check`，超限不发出请求

## 私密路径与脱敏

### 入口

- `python_backend/modules/context_engineering/privacy.py:private_path` —— 判断路径是否属于私密文件
- `python_backend/modules/context_engineering/privacy.py:sanitize_text` / `sanitize_value` —— 文本与结构化值脱敏
- `python_backend/modules/execution/trace.py:trace_preview` —— 有界预览 + 凭据替换

### 行为

- `private_path` 在读取、索引、上传前生效，命中即整条排除；绝对路径和带冒号的路径（Windows 盘符）一律判为私密。
- 命中的目录或文件名：`..`、`private`、`secrets`、`.secrets`、`.ssh`、`.aws`、`.azure`、`.git`、`data`、`node_modules`、`__pycache__`、`.venv`、`venv`、`dist`、`build`；含 `env` 的文件名；含 `.local.`/`.private.` 的名字；`.local`/`.private`/`.pem`/`.key`/`.p12`/`.pfx` 后缀；`id_rsa*`、`id_ed25519*`。
- `sanitize_text` 依次处理：`<private|secret|env>` 块、`.env` 文件名、大写环境变量赋值、`trace_preview`、地址型键值（host/server/domain/address/url/dsn/endpoint/port）、密钥（sk-/ghp_/AKIA/JWT 形态）、域名、IPv6。
- `trace_preview` 只产出预览副本，不改变原值；把 URL、IPv4、Bearer 令牌、私钥块和 api_key/password/secret/dsn 类键值替换为 `[REDACTED]`。
- 原文保留在本地库，脱敏只作用于离开本地持久化边界的副本；投递长期记忆前由 `ContextService._memory_payload` 统一脱敏，工具结果原文入库、送给模型的副本另行截断。

## 上下文快照

### 入口

- `python_backend/modules/context_engineering/snapshots.py:context_snapshot` —— 生成调用前上下文预览
- `python_backend/modules/execution/engine.py:AgentEngine._context` —— 各阶段快照出口；`python_backend/modules/execution/langchain_agent.py:run_agent` —— 技能流阶段快照
- `GET /execution/runs/{run_id}/context` —— 读取该次运行记录的快照

### 行为

- 快照是事件类型 `context_snapshot`，`schemaVersion` 为 1，字段含 `capturedAt`（UTC）、`stage`、`modelName`、`modelConfigured`、`messageCount`、`budget`、`sources`。
- 最多预览 24 条消息，超出记 `omittedMessages`，单条内容上限 6000 字符；工具定义最多 8 个，超出记 `omittedTools`，`tool_calls`/`tool_call_id` 单独放在 `toolProtocol`。
- 只记录模型名与「是否已配置」，不记录 API Key 等凭据；预算字段只取 `estimatedTokens`、`inputBudget`、`outputReserve`。
- 阶段取值：`context-preparation`、`answer`、`retrieval-route`、`retrieval-sql`、`retrieval-plan`、`skill-model`。
- 快照随运行事件持久化，历史运行不会按当前配置补建快照。

## 来源与记忆写入

### 入口

- `python_backend/modules/context_engineering/service.py:ContextService.record_tool` —— 归档工具结果；同文件 `status` / `forget` / `forget_uri` —— 状态查询与撤销
- `python_backend/modules/memory/tools.py:build_context_tools` —— 只读工具 `search_memory`、`read_context_source`
- `GET /harness/context/{conversation_id}/sources/{source_id}` —— 分页读取原始来源

### 行为

- 来源 ID 形态：`message:` 行 ID、`tool:{turn_id}:{tool_call_id}`、`checkpoint:{through_id}`、`delivery:{job_id}`。
- 工具结果原文完整入库；送给模型的副本按上限截断，模型可用 `read_context_source` 回读全文。
- 读取本地来源按字符分页；远端 `viking://` 来源按行分页，每页最多 80 行。
- 工具只能读本会话或本工作区的来源，跨会话、跨工作区与已撤销的记忆路径都会被拒。
- `forget` 先轮换 scope generation、再删本地证据；同一 scope 的其它会话派生记忆一并失效，并从幸存事件重建。
- `forget_uri` 先登记屏蔽再排队远端删除；屏蔽清单在召回与工具读取两处都生效。

### 关键实现

- `python_backend/modules/memory/store.py:MemoryStore.source` / `pending_sources` / `iter_events` —— 来源读取、待投递内容、事件流式遍历
- `python_backend/modules/memory/openviking.py:memory_uri_belongs` / `memory_uri_blocked` —— 记忆路径归属与屏蔽判定

## 长期记忆投递（OpenViking）

### 入口

- `python_backend/modules/context_engineering/service.py:ContextService.start` / `close` —— 启停投递线程；同文件 `deliver_once` —— 处理一条投递任务
- `python_backend/modules/memory/openviking.py:OpenVikingClient` —— HTTP 客户端

### 行为

- 只在配置了 `openviking_url` 时才建客户端；未配置时 `memoryStatus='unconfigured'`，本地来源与状态路径照常工作。
- 一轮完成即入队一条投递任务，`job_id` 由 scope、generation、conversation、source 哈希得出，重复完成不会重复入队。
- 阶段流转 `pending` → `committing` → `extracting` → `done`；任务用租约抢占，多 worker 并发时只有一个拿到。
- 传输失败按 `2^min(attempts+1, 8)` 秒退避，上限 300 秒；抽取失败记 `extraction_failed`、延迟 3600 秒并保留可见错误码。
- commit 响应丢失时先查已有任务再决定是否重试，不产生重复记忆。
- 记忆按 peer 隔离，`peer = hotline-{scope_id}-{generation}`；同工作区会话共享，其他工作区召回不到；远端不可用时只把 `memoryStatus` 置为 `unavailable`，回答链路不受影响。

### 关键实现

- `python_backend/modules/memory/store.py:MemoryStore.claim` / `delivery_update` / `queue_delete` —— 租约抢占、状态推进、删除排队
- 投递线程名为 `openviking-memory`，无任务时按 2 秒间隔轮询；远端删除走同一队列

## 容量与召回基准

### 入口

- `python_backend/modules/context_engineering/benchmark.py:run_benchmark` —— 跑一次本地基准；同文件 `main` —— 命令行入口，参数 `--tokens`、`--queries`、`--output`

### 行为

- 生成合成语料，用 `cl100k_base` 计数，写入 `WorkspaceIndex`（sqlite-fts5），结果落 `report.json`。
- 输出 `recallAt8`、`retrievalP50Ms`/`retrievalP95Ms`、`sourceRecoveryRate`、`workspaceIsolationPassed`。
- 通过条件：实际 token 数达标、`recallAt8 ≥ 0.95`、`sourceRecoveryRate = 1`、工作区隔离检查通过；不通过时进程返回非零。
- 不调用任何模型（`providerCalls=0`），不评估语义质量（`semanticQualityMeasured=false`），不评估 OpenViking（`openVikingMeasured=false`）；目标目录已有数据库时直接报错，避免覆盖旧报告。

## 数据与存储

- 本地库：`{data_dir}/context-memory.db`（SQLite，WAL 模式），由 `MemoryStore` 建表。
- 表：`memory_scope`（scope_id + generation）、`memory_conversation`（状态 JSON、revision、摘要、摘要游标）、`memory_event`（原始来源）、`memory_event_fts`（trigram 全文索引）、`memory_delivery`（投递队列与租约）、`memory_blocked_uri`（屏蔽的记忆路径）、`memory_checkpoint` 与 `memory_checkpoint_fts`（分段摘要及索引）。
- `scope_id = sha256('workspace:'+workspace_id 或 'conversation:'+conversation_id)` 取前 32 位；`peer_id = hotline-{scope_id}-{generation}`。
- 会话状态字段：`goal`、`constraints`、`decisions`、`pending`、`currentRequest`、`currentSourceId`、`lastCompletedSourceId`；约束项含 `key`、`quote`、`sourceId`、`status`（active/completed/cancelled）。
- 原始来源留在本地；出本地边界的副本（模型输入、长期记忆、快照）一律脱敏；基准报告写入调用方指定的输出目录。

## 接口清单

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/harness/context/{conversation_id}` | 会话上下文状态、记忆后端与投递列表 |
| `PUT` | `/harness/context/{conversation_id}/task` | 手工更新任务状态；带 `revision` 乐观锁，引用必须出自本会话原话 |
| `GET` | `/harness/context/{conversation_id}/history` | 按关键词检索本会话历史来源 |
| `GET` | `/harness/context/{conversation_id}/sources/{source_id}` | 分页读取原始来源（字符分页） |
| `DELETE` | `/harness/context/{conversation_id}/memories` | 撤销单条长期记忆 URI 并排队远端删除 |
| `DELETE` | `/harness/context/{conversation_id}` | 撤销整个会话上下文，轮换命名空间并删除会话 |
| `GET` | `/execution/runs/{run_id}/context` | 读取该次运行记录的上下文快照 |
| `GET` | `/execution/runs/{run_id}/events` | 读取运行事件流（含 `context_snapshot`） |

## 边界与已知限制

- 令牌估算是 UTF-8 字节上界，不是真实分词结果，中文场景偏保守。
- 约束、决策、待办只认用户原话引用；模型转述、建议和材料中的指令不会被采纳。
- 长期记忆依赖外部 OpenViking 服务；未配置或不可用时只有本地来源与任务状态可用，抽取失败任务延迟 3600 秒重试且错误码在状态接口可见。
- 快照只反映调用前的输入，历史运行不补建；快照本身也做脱敏，展示可能与实际发送内容有差异；基准只测本地检索容量与召回，不测语义质量与 OpenViking 表现。
- 作用域键必须全链路一致，`begin`/`prepare`/`complete`/`extract_state`/`checkpoint` 混用父会话键会撞记忆乐观锁或报「会话范围不存在」。
