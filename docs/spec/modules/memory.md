# 长期记忆（memory）

> 模块路径：`python_backend/modules/memory/`（`store.py`、`openviking.py`、`tools.py`） ｜ 前端对应：`frontend/src/modules/memory/`（只有 `.gitkeep` 占位，无独立前端模块）
> 状态：现状说明（以代码为准，冲突时以代码为准并修正本文档）

## 会话作用域绑定与作用域键

### 入口

- `python_backend/modules/memory/store.py:MemoryStore.bind` —— 会话绑定到记忆作用域
- `python_backend/modules/execution/engine.py:AgentEngine.stream` —— 计算 `scope_key` 并传给 context.begin/prepare/complete

### 行为

- `scope_id` 取 `sha256("workspace:"+workspace_id)` 或 `sha256("conversation:"+conversation_id)` 的前 32 位：有工作区时同工作区会话共享作用域，无工作区时每会话自成一个作用域；`bind` 用 `INSERT OR IGNORE` 建行，已绑定的会话算出不同 `scope_id` 时抛 `MemoryConflict("会话已绑定其他范围，请使用新的会话")`，标识长度上限 255。
- 远端命名空间 `peer_id` 固定为 `hotline-{scope_id}-{generation}`，`generation` 存在 `memory_scope` 表，遗忘时整体加一；引擎里 `scope_key = task_key or conversation_id`：普通对话用会话 ID，子任务用 `{conversation_id}#{slot}`，begin/prepare/complete/checkpoint/extract_state 必须同键，否则报「会话范围不存在」或撞上记忆乐观锁。
### 关键实现

- `store.py:MemoryStore.bind` / `conversation` —— 作用域派生与冲突判定；`engine.py:AgentEngine.stream` —— 子任务作用域隔离

## 乐观锁与任务状态写入

### 入口

- `store.py:MemoryStore.put_state` —— 带版本号的任务状态写入
- `python_backend/modules/context_engineering/service.py:ContextService.extract_state` —— 从用户原话抽取约束、决策与待办

### 行为

- `memory_conversation.revision` 是乐观锁：更新带 `WHERE conversation_id=? AND revision=?`，受影响行数为 0 时抛 `MemoryConflict("任务状态已更新，请重新读取后重试")`，成功则版本加一。
- 状态结构固定为 `goal`、`constraints`、`decisions`、`pending`、`currentRequest`、`currentSourceId`，条目为 `{key, quote, sourceId, status}`，`status` 只允许 `active`、`completed`、`cancelled`。
- `extract_state` 只接受用户原话里的精确引文（`quote` 必须是来源 `question` 的子串）：`key` 长度 1–80、`quote` ≤2000 字符、每类 ≤64 条、每轮 ≤16 条；结果非法或撞乐观锁时返回 `False` 而不抛异常；`PUT /harness/context/{conversation_id}/task` 引文校验不过返回 400，版本不匹配返回 409。
### 关键实现

- `store.py:MemoryStore.put_state` —— 条件更新实现的乐观锁；`service.py:ContextService.extract_state` —— 引文校验与冲突降级

## 事件记录、完成标记与重复投递幂等

### 入口

- `store.py:MemoryStore.record` —— 记录一问一答并按需生成投递任务
- `service.py:ContextService.complete` —— 一轮回答结束后的记忆落库入口（引擎侧由 `engine.py:AgentEngine._remember_answer` 调用）

### 行为

- `record` 在一个事务里写 `memory_event`、重建该条 FTS 索引，并在 `completed=True` 且带 `payload` 时插入 `memory_delivery` 投递任务；投递任务 `job_id` 由 `sha256("{scope_id}:{generation}:{conversation_id}:{source_id}")` 派生并 `INSERT OR IGNORE`，同一来源重复落库不会产生第二条投递（幂等）。
- 已完成的事件不会被未完成状态覆盖：旧行 `completed=1` 而新调用 `completed=False` 时直接返回；会话行不存在时抛 `MemoryConflict("会话范围不存在")`；`mark_completed` 把 `lastCompletedSourceId` 写进 `state_json` 并让版本加一；`source`、`events`、`iter_events`、`search_history` 都按 `conversation_id` 过滤，`iter_events` 按 `rowid` 每批 500 条。
### 关键实现

- `store.py:MemoryStore.record` —— 同事务写事件、FTS 与投递任务；`engine.py:AgentEngine._remember_answer` —— 落库失败发 `memory_write` 失败步骤，不影响已保存的回答

## 摘要、检查点与历史检索

### 入口

- `service.py:ContextService.checkpoint` —— 生成阶段摘要
- `store.py:MemoryStore.save_summary` / `search_checkpoints` / `search_history` / `source` —— 摘要写入、两路检索与来源读取

### 行为

- 只对 `history[:-4]` 之前的旧记录做摘要，最近 4 轮保留原文；`summary_through` 相同则跳过，摘要游标只前进。
- 摘要输入 16000 字节预算、每条摘录 ≤2000 字节、余量不足 512 字节即停；模型不可用时降级为「此前摘录 + 新增摘录」拼接，最终截断 6000 字符；带 `segment` 时同步写 `memory_checkpoint` 与 FTS5（trigram）索引，旧分段仍可按 `through_id` 读回。
- `search_checkpoints` 只在当前会话内检索（词条长度 ≥3、最多 12 个、按 `rank` 排序，默认 3 条）；`search_history` 只返回 `completed=1`，长度 ≥3 走 FTS，更短的词退化为 `LIKE` 模糊匹配；`source` 支持裸 `source_id`、`checkpoint:{through_id}`、`delivery:{job_id}` 三类标识。
### 关键实现

- `service.py:ContextService.checkpoint` —— 摘要游标、预算裁剪与降级路径；`store.py:MemoryStore.save_summary` —— 摘要与检查点分段同事务写入

## OpenViking 客户端与 peer 隔离

### 入口

- `python_backend/modules/memory/openviking.py:OpenVikingClient` —— OpenViking HTTP 适配器（`upload` / `commit` / `find_commit_task` / `task` / `search` / `recall` / `delete_memory`）
- `openviking.py:memory_uri_belongs` / `memory_uri_blocked` —— 路径归属与撤销判定

### 行为

- 连接配置只允许 http/https，必须有主机名，不得带账号密码、query、fragment；每次请求校验 `peer_id` 形如 `hotline-` 加 32 位十六进制加数字后缀，头带 `X-OpenViking-Actor-Peer`，配了密钥才带 `X-API-Key`；响应必须是 `status="ok"` 的对象，否则 `OpenVikingError("invalid_response")`，响应体上限 200 万字节，HTTP 错误转 `http_<状态码>`，重定向被拒绝。
- `upload` 先删同 session 再重建（未提交的上传可安全重试），创建 session 只开 peer 记忆并清掉自动提交策略，最后批量写入经 `sanitize_text` 脱敏的对话；`commit` 以 `keep_recent_count=0` 提交；`find_commit_task` 按提交任务类型加 `resource_id` 找已有任务，提交响应丢失时复用已有任务而不重复提交。
- `search` 固定 `mode=list`、`context_type=memory`、目标为当前 peer 的 `memories` 目录、上限 20 条、不直接取正文；`recall` 分层取数：L0 命中 → 每目录一次 L1 概览 → 前 2 条 `level=2` 读 L2（单页 ≤80 行），结果 `content` 为 `{abstract, overview, detail}` JSON；路径只接受 `viking://~/peers/{peer_id}/memories/...` 与 `viking://user/<段>/peers/{peer_id}/memories/...`，带 `..`、query、fragment 一律拒绝，`memory_uri_blocked` 忽略 `user` 别名，家目录别名绕不过撤销名单。
### 关键实现

- `openviking.py:OpenVikingClient.request` —— 统一请求、鉴权头与错误归一；`memory_uri_belongs` —— peer 路径白名单

## 投递队列与后台轮询

### 入口

- `service.py:ContextService.deliver_once` —— 处理一个投递任务
- `store.py:MemoryStore.claim` / `delivery_update` / `queue_delete` —— 领取、推进与删除排队（后台线程由 `service.py:ContextService.start` / `close` 管控）

### 行为

- 后台线程 `openviking-memory` 循环处理任务，一轮无任务等 2 秒，未配置远端不启动；`claim` 在 `BEGIN IMMEDIATE` 事务里领取 `stage` 不在 `done`、`cancelled` 且已到期的最早任务并写租约与 `lease_token`，租约为 `max(120, 超时×8)` 秒，多 worker 并发只有一条拿到；阶段流转 `pending`（上传）→ `committing`（提交并取 `task_id`）→ `extracting`（轮询）→ `done`。
- 提交阶段先找已有提交任务再 `commit`，拿不到 `task_id` 抛 `commit_task_unknown`；提取阶段 `failed`、`cancelled` 抛 `extraction_failed`（退避 3600 秒并保留现场），`completed`、`succeeded` 置 `done`，其它状态保持 `extracting` 5 秒后再查；传输类错误按 `min(300, 2^(attempts+1))` 秒退避。
- `delivery_update` 校验 `lease_token`，租约失效抛 `MemoryConflict("记忆任务租约已失效")`；投递期间作用域被轮换（`generation` 不一致）时任务置 `cancelled`；删除类任务先确认相关提交任务已结束，再删远端 session 与记忆目录。
### 关键实现

- `service.py:ContextService.deliver_once` —— 阶段机、退避与取消判定；`store.py:MemoryStore.claim` —— 租约领取，多 worker 下不重复投递

## 遗忘、撤销与派生记忆重建

### 入口

- `service.py:ContextService.forget` / `forget_uri` —— 遗忘会话上下文、撤销单条远端记忆
- `store.py:MemoryStore.forget` / `block_uri` / `blocked_uris` —— 作用域轮换与撤销名单（对外接口 `DELETE /harness/context/{conversation_id}` 与 `DELETE /harness/context/{conversation_id}/memories`）

### 行为

- `forget` 先把作用域 `generation` 加一（共享命名空间轮换），再取消该作用域未完成的 `mem-` 投递、清空事件与 FTS、删检查点、清空投递载荷、最后删会话行；同工作区其它会话的 `peer_id` 随之改变，旧命名空间下的派生记忆不再可见，`forget` 之后遍历同作用域存活会话的已完成事件重新落库重建。
- `forget_uri` 先校验 URI 属于当前 peer，否则抛 `ValueError("记忆路径不属于当前范围")`；通过后写入 `memory_blocked_uri` 并排入远端删除任务，被撤销的 URI 在检索、召回与工具读取三处都不可见。
### 关键实现

- `store.py:MemoryStore.forget` —— 先轮换命名空间再删本地证据；`service.py:ContextService.forget` —— 派生记忆失效与重建

## 记忆只读工具

### 入口

- `python_backend/modules/memory/tools.py:build_context_tools` —— 装配 `search_memory` 与 `read_context_source`

### 行为

- `search_memory` 返回本地历史命中、远端命中（各 800 字预览）与 `workspaceEvidence`；`memory_status` 取 `unconfigured`、`ready`、`unavailable`；远端检索前后各复查一次会话与 `generation`，作用域被撤销返回 `{"error": "会话上下文已撤销"}`。
- `read_context_source` 分三类来源：`workspace:` 前缀走工作区读取器、`viking://` 前缀走远端记忆、其余按本地 `source_id` 读取；远端支持 `abstract`、`overview`、`detail` 三层，`detail` 按行分页且单页 ≤80 行，本地与工作区来源按字符分页。
- 撤销名单内的 URI、缺失来源、越权工作区来源都返回 `error` 而不抛异常。
### 关键实现

- `tools.py:build_context_tools` —— 工具装配与撤销复查；`service.py:ContextService.prepare` —— 上下文装配时同样按撤销名单过滤远端命中

## 数据与存储

- 本地 SQLite：`data/context-memory.db`（WAL 模式），由 `ContextService` 按 `settings.data_dir` 装配；表：`memory_scope`、`memory_conversation`（状态 JSON、版本、摘要游标）、`memory_event` 与 FTS5 trigram `memory_event_fts`、`memory_delivery`（队列、租约、重试）、`memory_blocked_uri`、`memory_checkpoint` 与 `memory_checkpoint_fts`；远端只存脱敏后的摘要型记忆，原始问答证据只留在本地 SQLite；配置项：`HOTLINE_OPENVIKING_URL`、`HOTLINE_OPENVIKING_API_KEY`、`HOTLINE_OPENVIKING_TIMEOUT`（对应 `config.py` 的 `openviking_url`、`openviking_api_key`、`openviking_timeout`）。

## 接口清单

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/harness/context/{conversation_id}` | 会话记忆状态、作用域与投递队列 |
| `PUT` | `/harness/context/{conversation_id}/task` | 带版本号更新任务状态 |
| `GET` | `/harness/context/{conversation_id}/history?q=`、`/sources/{source_id}` | 检索本会话已完成的问答历史、按来源 ID 分页读取原始记录 |
| `DELETE` | `/harness/context/{conversation_id}/memories` | 撤销单条远端记忆并排队删除 |
| `DELETE` | `/harness/context/{conversation_id}` | 遗忘会话上下文并轮换命名空间 |
| `POST` | `/api/v1/sessions`、`/api/v1/sessions/{session_id}/messages/batch`（OpenViking 远端） | 创建记忆会话并设置记忆策略、批量写入脱敏后的对话 |
| `POST` | `/api/v1/sessions/{session_id}/commit` | 触发远端记忆抽取 |
| `GET` | `/api/v1/tasks/{task_id}`、`/api/v1/tasks?task_type=session_commit` | 轮询抽取任务、查找已有提交任务 |
| `POST` | `/api/v1/search/search` | 在当前 peer 的记忆目录内检索 |
| `GET` | `/api/v1/content/{level}`、`/api/v1/content/read` | 分层读取概览与详情 |
| `DELETE` | `/api/v1/sessions/{session_id}`、`/api/v1/fs` | 删除远端会话与记忆目录 |
| — | `python_backend/modules/memory/store.py:MemoryStore` | 本地记忆存储与投递队列 |
| — | `python_backend/modules/memory/tools.py:build_context_tools` | 装配记忆只读工具 |

## 边界与已知限制

- 本模块没有独立路由前缀，对外接口都挂在 `/harness/context/*` 下；前端对应目录只有 `.gitkeep` 占位文件，没有记忆界面。
- 未配置 OpenViking 时本地记忆、摘要与历史检索照常工作，远端状态为 `unconfigured`；远端故障只降级为 `unavailable`，不影响本地回答路径。
- 记忆只在同一工作区（同一 `scope_id`）内共享，不同工作区互相不可见；事件表按会话隔离，但同工作区会话共享远端命名空间，对其中一个会话遗忘会连带轮换该工作区的远端命名空间。
- 远端投递最终一致：回答返回时记忆可能仍在排队（`pending`、`committing`、`extracting`）；抽取失败保留现场并按 3600 秒退避；落库失败发 `memory_write` 失败步骤，已保存的回答不受影响，下一轮重试该来源的落库。
- 子任务用 `{conversation_id}#{slot}` 作作用域键，不写父会话的 `ai_session` 历史，也不复用父会话的记忆作用域。
- 撤销名单按去掉 `user` 别名后的路径比对，别名不能绕过，同一路径的不同别名会被一并拦下；任务状态里的引文必须与用户原话逐字一致，否则该条约束、决策或待办被丢弃。
