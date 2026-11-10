# Hotline 性能测量与并发压测方案（含系统优化清单）

状态：草案。本文回答两个问题——**这个系统还能优化什么**，以及**怎么系统性地测出每个环节的耗时、性能与并发**。

调研时间：2026-11-10。现状部分逐条按代码取证，给 `文件:行号`；业界部分给来源；方案部分给可执行命令、阈值口径与验收标准。

阅读约定：现状只写代码里确实存在的行为，不把规划当实现；测量方案分五层（L0 单元基准 → L1 组件基准 → L2 端到端 → L3 并发压测 → L4 生产观测），每层有明确产出物与门禁；所有数字先写口径再写阈值。

与 [第二阶段能力设计](./stage-two-capability-design.md) 的分工：那份讲「要补哪些能力」，本文讲「补之前先测出瓶颈在哪，以及补完之后怎么证明变快了」。

---

## 一、结论速览

**最该先做的三件事**（都是低改动、高收益，见第三节）：

1. **上传路径的事件循环阻塞** —— `python_backend/fastapi_app.py:218` 的 `async def file_upload` 在事件循环里同步做 embedding HTTP（`:253`，每块一次、最长 90s），一个上传就能拖住整个网关。
2. **摄取路径逐块 embedding** —— `python_backend/vector_store.py:159-179` 每块一次 HTTP；批量接口 `embed_batch`（`:101`）已经存在却没被摄取路径用。改调用方式是纯收益。
3. **SSE 每 80ms 在事件循环里查两次 SQLite** —— `python_backend/api/routers/execution.py:41-63`，每个打开的流约 12.5 次/秒 × 2 次查询。

**最短的测量路径**（不需要任何新框架，两天可跑出第一批数字）：

1. 在 §4.1 的口径表上定下 5 个 SLI（端到端延迟、检索延迟、TTFT、错误率、队列积压）。
2. 用已有的 `durationMs` 埋点（§2.8）把检索/路由/LLM 三段耗时导出来——**这一步已经有数据，只差导出**。
3. 用 k6 写一个 SSE 场景做阶梯加压（§4.5），拿到并发-延迟曲线。
4. 用 pytest-benchmark 给三个纯 Python 热点建基准（§4.3）：融合、余弦相似度、预算估算。

**一句话原则**（贯穿全文）：先测分位数，再谈优化；先定口径，再谈阈值。没有分位数的平均值不作为决策依据。

---

## 二、现状取证

### 2.1 进程与入口

| 进程 | 入口 | 说明 |
| --- | --- | --- |
| 网关 | 根目录 `main.py:15` → `python_backend/fastapi_app.py:128`（FastAPI + uvicorn） | `npm start` 走 `start-services.mjs:61` 的 `uvicorn main:app` |
| 执行 Worker | `python_backend/modules/execution/worker.py` | 独立进程，消费 SQLite 队列 |
| 遗留入口 | `python_backend/main.py:290`（标准库 `ThreadingHTTPServer`） | 仍在仓库里，端口与网关相同，**不要同时启动** |

真实网关是 FastAPI 应用（`python_backend/fastapi_app.py:128`），所有路由与压测目标都对着它。遗留入口只保留历史兼容。

### 2.2 同步阻塞：事件循环里的同步 I/O

全仓 `async def` 只有 6 处（`python_backend/fastapi_app.py:109`、`:218`、`:269`、`:339`、`:445` 与 `python_backend/api/routers/execution.py:41`），其中三处在事件循环里做同步出站调用，直接拖住整个网关：

- `python_backend/fastapi_app.py:218` `file_upload`：在事件循环里同步做对象存储上传、文件解析，最后调 `vector_store.add_chunks`（`:253`）——该函数每块一次 embedding HTTP（`python_backend/vector_store.py:133-142`），超时 90s（`python_backend/vector_store.py:114`）。N 块 = N 次串行阻塞。
- `python_backend/fastapi_app.py:269` `document_upload`：走 `documents.upload` → MinerU 转换，轮询里用 `time.sleep`（`python_backend/documents.py:116`），上传与结果包下载的 HTTP 超时都是 180s（`python_backend/documents.py:91`、`:143`）。
- `python_backend/api/routers/execution.py:41` `event_stream`：唯一的高频异步处理器，每 80ms（`:61`）同步调用 `service.get_run` 与 `service.get_events`，二者落到同步 SQLite（`python_backend/modules/execution/store.py:253`、`:299`）。
- 另外两处 `async def`（`python_backend/fastapi_app.py:339` `skill_upload`、`:445` `console_skills_action`）没有同步出站调用，但仍在事件循环里做同步工作：前者直接执行技能安装（`:344`），后者派发控制台动作。

其余大部分路由是同步 `def`，由 Starlette 线程池执行——这是对的（SQLite 与 urllib 都是阻塞调用），但意味着**每个同步路由都会占住一个线程池槽位**，并发上限来自线程池大小而非业务容量。

### 2.3 出站调用的放大

| 依赖 | 位置 | 超时 | 重试 | 连接复用 |
| --- | --- | --- | --- | --- |
| 模型（非流式） | `python_backend/agents.py:153` | 90s | 无 | 无（`urllib.urlopen` 每次新建 TCP/TLS） |
| 模型（流式） | `python_backend/agents.py:211` | 90s | 仅 `stream_options` 不被支持时重试一次（`python_backend/agents.py:198-207`，无退避） | 无 |
| Embedding | `python_backend/vector_store.py:114`、`:130` | 90s | 无 | 无 |
| 意图向量 | `python_backend/modules/intent/retrieval.py:48` | 30s | 无 | 无 |
| Tavily | `python_backend/agents.py:322` | 30s | 无 | 无 |
| 三元组抽取 | `python_backend/documents.py:585` | 45s | 无 | 无 |

放大点：

- **逐块 embedding**：`python_backend/vector_store.py:133-142` 与 `:159-179` 每块一次 HTTP；批量接口 `embed_batch`（`:101`）只在工作区文件级语义召回里用过（`python_backend/workers/execution_worker.py:357`）。
- **逐块串行 LLM 抽取三元组**：`python_backend/documents.py:689` 起对每个文档最多 40 个子块各调一次模型（`:585`），最坏 40×45s。
- **意图门闸每请求新建线程池**：`python_backend/modules/intent/classifier.py:203` 每次 classify 都 `ThreadPoolExecutor(max_workers=GATE_SAMPLES)`，用完即弃。
- **锁内做网络 I/O**：`python_backend/modules/intent/retrieval.py:82` 的锁在 `:108` 覆盖 `warmup`，warmup 里逐条调 embedding。

### 2.4 纯 Python 计算热点

仓库里没有 numpy/scipy/pandas，向量运算用标准库列表与 `array('f')`：

- `python_backend/modules/retrieval/workspace_index.py:377` 的余弦相似度是 `sum(a * b for a, b in zip(query, vector))`，且 `:363-381` 会把工作区**全部**文件向量读进内存后逐个算——工作区文件一多就是 O(文件数 × 维度) 的 Python 级运算。
- 归一化 `python_backend/modules/retrieval/workspace_index.py:67-71` 同样是纯 Python 循环。
- 词面分层：四层各跑一次 FTS5（`python_backend/modules/retrieval/workspace_index.py:425`、`:439`），短词兜底层对每个词单独发一条 SQL（`:454-475`）；分词 `_terms`（`:407-423`）也是纯 Python。
- **每次操作新建 SQLite 连接**：`python_backend/modules/retrieval/workspace_index.py:163-171` 的 `db()` 上下文管理器每条语句开一条连接。
- **预算估算重复遍历**：`python_backend/modules/context_engineering/budget.py:50-54` 的 `check` 每次都把整份 messages 重新 `json.dumps` 一遍再编码；`assemble_context`（`:57-98`）在 `:67`、`:73`、`:84`、`:89`、`:97` 反复调用它，sections 越多重复序列化越多（近似 O(n²)）。
- **融合阶段每候选一次正则**：`python_backend/modules/retrieval/fusion.py:12` 对每个候选 `re.sub` 归一化，`:16-19` 再全文 casefold 扫描一次排序键。

### 2.5 SQLite 写竞争与锁

- **全局 RLock + 每操作建连接**：`python_backend/storage.py:19` 一把全局 `threading.RLock`，`:135` 每条 SQL 都 `with self._lock, closing(self._connect_sqlite())`，而 `:46` 的 `sqlite3.connect(self.db_path, check_same_thread=False)` **没有 timeout、没有 busy_timeout、没有 WAL**——主会话库在并发写下靠进程内锁串行，跨进程没有保护。
- **WAL 覆盖不全**：已开 WAL 的有 `python_backend/modules/execution/store.py:68`、`python_backend/modules/memory/store.py:25`、`python_backend/modules/retrieval/workspace_index.py:132`、`python_backend/modules/artifacts/store.py:36` 等；**未开**的有 `python_backend/storage.py`、`python_backend/infrastructure/evaluation_store.py`、`governance_store.py`、`notification_store.py`、`registry_store.py`、`resource_store.py`、`settings_store.py`。
- **busy_timeout**：`python_backend/modules/memory/store.py:67`、`python_backend/modules/retrieval/workspace_index.py:164`、`python_backend/modules/execution/store.py:52` 与 `python_backend/infrastructure/*_store.py` 大多用 `connect(timeout=30)`（等效 30s 忙等待）；**没设的**是 `python_backend/storage.py:46`（走 Python 默认 5s）、`python_backend/skill_center.py:197` 与 `python_backend/modules/execution/tools.py:180`。
- **写锁用点**：`BEGIN IMMEDIATE` 出现在 `python_backend/modules/execution/store.py:139`、`:169`、`:195`、`:236`、`:374`、`:401`，`python_backend/modules/memory/store.py:141`、`:247`、`:312`，以及 registry/resource/evaluation/governance/skill_center/workspace_index 各自的写入点。
- **抢占不重试**：`python_backend/modules/execution/store.py:192-231` 的 `claim_next` 用 `BEGIN IMMEDIATE` + 单条条件 UPDATE，遇锁直接抛；`python_backend/modules/memory/store.py:244-258` 的 `claim` 同理。

### 2.6 无界增长

- `execution_event` 只增，靠保留任务清理（`python_backend/modules/retention/maintenance.py:22-42`，默认 30 天、每小时一次）。
- **`memory_event` 没有时间维度的保留策略**：`python_backend/modules/retention/maintenance.py:76-88` 只处理 execution/governance/artifacts，记忆只在显式 `forget` 时删（`python_backend/modules/memory/store.py:309-323`）——长期运行会无限增长。
- **产物文件不随保留期删除**：清理任务只删数据库行（`python_backend/modules/retention/maintenance.py:60-72`），磁盘文件要手工调带 `deleteFiles=true` 的清理接口才删。
- **Worker 内存字典不清理**：`python_backend/workers/execution_worker.py` 的 `_retry_attempts` / `_token_usage` 按 run、conversation 增长后从不清理。
- **线程不退出**：`python_backend/agents.py:61` 的 Redis 停止监听线程没有停止方法；`python_backend/documents.py:526` 的 `ThreadPoolExecutor` 有 `shutdown()` 但未找到调用方；`python_backend/modules/context_engineering/service.py:38-41` 的 `close()` 只 `join(timeout=2)`，而 in-flight 的 OpenViking 调用最长 10s（`:28`，`openviking_timeout` 的默认值）。

### 2.7 竞态与重复执行窗口

- **租约与重复执行**：`python_backend/modules/execution/store.py:44` 租约 45s，由 monitor 每 3s 续期（`python_backend/workers/execution_worker.py:122-134`、`python_backend/modules/execution/store.py:462-467`）。若 Worker 停顿超过租约，另一个 Worker 的 `claim_next`（`python_backend/modules/execution/store.py:196-207`）会把该 run 标记为 failed，而原 Worker 仍在跑——**同一请求可能被重复执行一次**（`python_backend/modules/execution/store.py:165-185` 的 `retry_run`）。
- **Worker 一次异常即退出**：`python_backend/workers/execution_worker.py:189` 的 `run_once` 没有单次异常兜底，`:320-332` 的 `run_forever` 循环体也没有 try/except——一次 "database is locked" 就会终止 Worker 循环。
- **取消延迟**：`request_cancel`（`python_backend/modules/execution/store.py:369-395`）只置标志位，生效依赖 3s 轮询（`python_backend/workers/execution_worker.py:128`），实际取消延迟还要叠加 Agent 检查点间隔。
- **revision 冲突未捕获**：`python_backend/modules/memory/store.py:102-109` 的 CAS 失败抛 `MemoryConflict`，调用方 `python_backend/modules/context_engineering/service.py:127` 未捕获，会冒泡成 Agent 错误事件。
- **后台线程竞态**：发布观察线程停止时会清空 observers（`python_backend/api/routers/release.py:41-52`），与正在跑的观察任务存在竞态；评测后台线程每个只 join 1s（`python_backend/api/routers/evaluation.py:31-42`）。
- **SSE 终态顺序**已显式处理（先读状态再吐事件，`python_backend/api/routers/execution.py:43-46`），这一点是对的。

### 2.8 现有埋点：可测量的分界点

这是本方案的基础——**大部分耗时数据已经有了，只差导出与口径**：

| 埋点 | 位置 | 载荷 |
| --- | --- | --- |
| 阶段耗时 | `python_backend/agents.py:287-295` `step()` | `durationMs`、`details` |
| 检索路由耗时 | `python_backend/agents.py:328-350` | `durationMs` + `route` |
| 检索命中耗时 | `python_backend/agents.py:511`、`:528` | `durationMs`、`hits`、`route` |
| Text2SQL 耗时 | `python_backend/agents.py:358-374` | `durationMs`、`rows` |
| 多跳停止原因 | `python_backend/agents.py:498` | `details.stopReason`（`hop_limit` / `cancelled` / `input_budget` / `coverage_sufficient`） |
| 模型用量 | `python_backend/agents.py:531-536` | `inputTokens` / `outputTokens` / `totalTokens` |
| 上下文快照 | `python_backend/agents.py:538-540` | `estimatedTokens` / `inputBudget` / `outputReserve` |
| 预算估算明细 | `python_backend/modules/context_engineering/budget.py:98`、`:100` | `sections[].estimatedTokens` / `omitted` / `truncated` |
| 运行级 token 累计 | `python_backend/workers/execution_worker.py:246-252` | `usage.runTotal`、`usage.budget` |
| 运行起止与事件时间戳 | `python_backend/modules/execution/store.py:434`、`:253-262` | 可算端到端与每段时延 |
| 检索基准 | `python_backend/modules/context_engineering/benchmark.py:88-104` | `retrievalP50Ms` / `retrievalP95Ms` / `indexSeconds` |

**现成基准的边界**：`benchmark.py` 测的是合成语料下的 FTS5 关键词层，报告里 `providerCalls: 0`、`semanticQualityMeasured: False`、`openVikingMeasured: False`（`:96`）——它**不测** embedding、不测向量召回、不测 OpenViking、不测并发、不测端到端延迟。

**全仓没有任何压测工具**：k6 / locust / wrk / vegeta / jmeter / pytest-benchmark 均无命中；HTTP 层也没有请求计时中间件（`python_backend/fastapi_app.py:129-134` 只挂了 CORS）。

---

## 三、优化清单

按「影响面 ÷ 改动成本」排序。验收口径一律写可自动判定的条件，不写「更快了」。

| # | 问题 | 证据 | 建议 | 影响 | 成本 | 验收口径 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 上传在事件循环里做 embedding HTTP | `python_backend/fastapi_app.py:218`、`:253`；`python_backend/vector_store.py:133-142` | 改同步路由走线程池，或投递到 Worker | 极高 | 低 | 并发上传 10 个文件时，网关 `/health` p99 不升高超过 20ms |
| 2 | 摄取逐块 embedding | `python_backend/vector_store.py:138`、`:177`；批量接口 `:101` 已存在 | 摄取改走 `embed_batch`，批 16–32 | 极高 | 低 | 1000 块文档的 embedding 调用次数从 1000 降到 ≤32，墙钟时间下降 ≥80% |
| 3 | SSE 每 80ms 在事件循环查两次 SQLite | `python_backend/api/routers/execution.py:41-63` | 事件写入时唤醒（条件变量或内存队列），至少先移出事件循环 | 极高 | 中 | 50 条并发 SSE 时，网关 CPU 占用不随流数线性增长 |
| 4 | 主会话库全局锁 + 每操作建连接 + 无 WAL | `python_backend/storage.py:19`、`:46`、`:135` | 连接复用 + WAL + busy_timeout，锁降到语句级 | 高 | 中 | 200 并发写会话不再出现 "database is locked" |
| 5 | 文档向量化时最多 40 次串行 LLM | `python_backend/documents.py:689`、`:585` | 限流为 N 次或改异步补齐；事件总线 worker 仅 2 个（`:526`） | 高 | 低 | 单文档向量化墙钟 ≤5s 或明确降级为异步 |
| 6 | Worker 单次异常终止整个循环 | `python_backend/workers/execution_worker.py:189`、`:320-332` | 单次 claim 包 try/except + 退避 | 高 | 低 | 注入一次 SQLite 锁错误后 Worker 仍继续消费 |
| 7 | 45s 租约与 3s 心跳造成重复执行窗口 | `python_backend/modules/execution/store.py:44`、`:196-207`、`:462-467` | 续期独立于 monitor，租约拉长并加抖动 | 高 | 中 | 停顿 60s 的 Worker 不产生重复执行 |
| 8 | 每次技能请求新建 Catalog 并跑 DDL | `python_backend/fastapi_app.py:379`；`python_backend/skill_center.py:197` | 进程级单例 + 只读连接 | 中高 | 低 | 技能接口 p95 下降，且不再触发写锁 |
| 9 | 预算检查重复全量序列化 | `python_backend/modules/context_engineering/budget.py:50-54`、`:57-98` | 改成增量 token 累加，只算一次 | 中高 | 低 | 100 段装配的 CPU 时间下降 ≥60% |
| 10 | 记忆事件无保留策略 | `python_backend/modules/retention/maintenance.py:76-88`；`python_backend/modules/memory/store.py:309-323` | 保留任务加 memory 表清理窗口 | 中高 | 低 | 跑 30 天模拟数据后 memory_event 行数不超阈值 |
| 11 | 意图 warmup 持锁做网络 I/O | `python_backend/modules/intent/retrieval.py:82`、`:108` | 锁外批量 embedding，锁内只换引用 | 中 | 低 | 并发分类时 embedding 调用不串行 |
| 12 | 每次 classify 新建线程池 | `python_backend/modules/intent/classifier.py:203` | 复用模块级池 | 中 | 低 | 线程数不随请求数增长 |
| 13 | 历史逐条 source 查询（N+1） | `python_backend/modules/context_engineering/service.py:112`、`:245` | 批量取后内存比对 | 中 | 低 | 100 条历史的装配 SQL 次数从 100 降到 ≤3 |
| 14 | 每次查询都重扫工作区并可能重新 embed | `python_backend/modules/workspaces/context.py:58-59` | 加变更门限，只在文件变动后重建 | 中 | 中 | 同一工作区连续查询 10 次，只有第 1 次产生 embedding 调用 |
| 15 | 前端无虚拟滚动 + 5s 轮询 + 全量会话 | `frontend/src/HarnessApp.vue:1888`、`:1928`；`frontend/src/App.vue:1819`；`frontend/src/api.js:29-40` | 长列表分页或虚拟化，轮询改推送 | 中 | 中 | 1000 条运行列表的渲染帧率与滚动内存不随条数线性恶化 |

**明确不建议现在做**（收益依赖真实负载，盲改风险大于收益）：换向量库、把 SQLite 换成 Postgres、引入分布式队列、在没有基准数据时做向量库选型。前三项都要等 §4.8 的容量模型给出数字再决策。

---

## 四、测量方案

### 4.1 指标口径（先定口径，再谈阈值）

参考 Google SRE 的四个黄金信号（延迟、流量、错误、饱和度）与 SLI/SLO 结构，落到本平台的 SLI 定义：

| SLI | 定义 | 口径要点 | 建议目标（自用单机，不是对外 SLO） |
| --- | --- | --- | --- |
| 端到端延迟 | 从请求进入网关到最后一个 SSE 事件 | 分位；**成功与失败请求分开统计**（失败通常更快，会拉低整体） | p50 < 3s，p95 < 8s |
| 首字延迟 TTFT | 从请求进入到收到第一个非空 text 事件 | 与检索、意图判定、装配串行叠加 | p95 < 1.5s（不含模型排队） |
| 检索延迟 | 从 `_retrieve` 进入到拿到 hits | 词面与语义通道分别记 | 词面 p95 < 120ms；语义 p95 < 400ms |
| 装配耗时 | `assemble_context` 的墙钟 | 含被裁剪的段数 | p95 < 60ms |
| 模型延迟 | 单次模型调用墙钟 / TTFT / TPOT | 与上游绑定，须单列不混入端到端 | 记录基线，不设目标 |
| 错误率 | 5xx 加业务错误事件，除以总请求 | 区分「模型失败」「检索失败」「系统失败」 | < 1% |
| 饱和度 | Worker 队列深度、活跃 SSE 数、SQLite 写锁等待、进程 RSS | **不要以 CPU 100% 为红线** | 队列深度 < 50 |
| 投递积压 | `memory_delivery` 中 `stage` 非 done 的行数与最老年龄 | 记忆投递是异步链路，积压是最早的信号 | 最老 < 5 分钟 |

**分位数口径**：用 HdrHistogram 风格（计数直方图，3 位有效数字即量化误差 ≤0.1%）而不是均值；t-digest 用于看分布形状与下采样聚合。两者都只保证**分位估计误差**，不改变采样口径。

**关键纪律**：缓存命中与未命中必须分桶；不同请求类型（短问答 / 长文总结 / 带工具执行）成本差异巨大，必须分开统计——Google SRE 明确指出「Queries per Second 不是好的容量单位」。

### 4.2 五层测量

| 层 | 目标 | 工具 | 产出 | 门禁 |
| --- | --- | --- | --- | --- |
| L0 单元基准 | 单函数 CPU 与耗时 | pytest-benchmark、asv | 基准表加回归对比 | 相对基线劣化超过 15% 失败 |
| L1 组件基准 | 一个模块的端到端耗时（检索、装配、投递） | pytest-benchmark 加桩依赖 | 分段耗时与分位 | 同上 |
| L2 端到端 | 真实链路（含外部依赖） | httpx 脚本、k6 | 端到端与 TTFT 分位 | 场景级阈值 |
| L3 并发压测 | 并发-延迟曲线、崩塌点、正确性 | Locust、k6、并发不变量测试 | 曲线加崩塌点加不变量报告 | 达到目标并发且不变量成立 |
| L4 生产观测 | 真实流量的分位与饱和度 | 现有事件表加 OTel 语义 | 看板与告警 | 告警可触发可验证 |

**不要跳层**：L0/L1 不做就上 L3，测出来的数字无法归因（是模型慢还是我们的检索慢）。

### 4.3 L0/L1：组件级基准

三个已知热点优先建基准（都是纯 Python，改动前后可直接对比）：

| 基准对象 | 位置 | 关注指标 |
| --- | --- | --- |
| 证据融合 | `python_backend/modules/retrieval/fusion.py:6-23` | 候选 100 条时的耗时与排序稳定性 |
| 向量余弦 | `python_backend/modules/retrieval/workspace_index.py:363-381` | 100/1000/5000 文件时的耗时（纯 Python 增长曲线） |
| 预算估算 | `python_backend/modules/context_engineering/budget.py:50-54` | 10/100/1000 段装配的总耗时（暴露平方级重复） |

用法要点：

- **pytest-benchmark**：用 `benchmark` fixture 包裹被测函数；`--benchmark-json` 导出机器可读结果，`--benchmark-compare` 与基线文件对比并在劣化时返回非零退出码——这就是「把压测接进 CI」的最省事形态（Langfuse 的 `RegressionError` 是同一思路的完整版）。
- **asv**（Airspeed Velocity）：为**跨提交的微基准**设计，自动跟踪每个 commit 的历史并画趋势曲线；适合「这次改动到底让检索慢了没有」这种长期问题。
- **py-spy**：无侵入采样火焰图，`py-spy record --rate 100 --duration 30 --threads --subprocesses`，产出 SVG 火焰图；定位「时间花在哪个函数」比读代码快得多，**采样开销低，可以直接挂在压测过程中**。
- **Scalene**：能区分 CPU、GPU、内存三类开销并指出 Python 层面的低效（如未向量化的数值运算）；比 cProfile 更适合找「纯 Python 计算热点」这类问题。

**基准纪律**（这几条比工具本身更重要）：

1. **预热**：进程内先跑若干轮再计时，丢弃前几轮；否则测的是导入与页缓存。
2. **隔离数据**：每个基准用自己的临时目录与数据库，绝不复用上一次的状态（现有 `python_backend/modules/context_engineering/benchmark.py:23-24` 的「已有数据库就拒绝覆盖」是个好范例）。
3. **固定种子**：随机输入用固定种子，否则每次对比都在比不同的东西。
4. **记录机器与版本**：CPU 型号、Python 版本、数据规模、依赖版本写进报告，否则数字不可比。
5. **不要在压测机上跑压测客户端**（见 §4.11）。

### 4.4 L2：端到端与流式测量

**TTFT 与 TPOT 的定义**（沿用 vLLM 的官方口径，便于以后和推理服务对齐）：

- **TTFT** = 首个输出 token 到达时间；**TPOT / inter-token latency** = 相邻输出 token 的平均间隔；**e2e latency** = 整段响应时间；**queue time** = 排队等待时间。
- 本平台的对应：TTFT = 请求进入 → 第一个非空 text 事件；分段耗时用已有的 `durationMs` 埋点还原（§2.8）。

**吞吐量的三种口径不要混**：req/s（HTTP 层）、token/s（LLM 层，输出 token 除以总时长，LLM 场景真正该盯的）、事务/s（数据库层）。

**错误率的口径陷阱**：k6 的 `http_req_failed` 只统计传输层失败，**业务失败（HTTP 200 但 body 里带错误）不会被计入**，必须自己定义 Rate 指标；Locust 侧对应 `request_exception` 事件计数。

**脚本骨架**（放 `perf/` 目录，不进主环境）：

~~~python
# perf/latency_probe.py：测端到端与 TTFT，输出分位
import asyncio, time, httpx

async def one(client, url, params):
    t0 = time.perf_counter()
    ttft = None
    async with client.stream("GET", url, params=params, timeout=120) as resp:
        async for line in resp.aiter_lines():
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload not in ("", "[DONE]") and ttft is None:
                ttft = time.perf_counter() - t0
    total = time.perf_counter() - t0
    return {"ttft_ms": (ttft or total) * 1000, "total_ms": total * 1000}

async def main(n=50, url="http://127.0.0.1:8888/agent/chat/stream"):
    results = []
    async with httpx.AsyncClient() as client:
        for i in range(n):
            results.append(await one(client, url, {
                "conversationId": "perf-" + str(i), "query": "压测固定问句"}))
    for key in ("ttft_ms", "total_ms"):
        values = sorted(r[key] for r in results)
        print(key, "p50=%.1f p95=%.1f max=%.1f" % (
            values[len(values)//2], values[int(len(values)*0.95)], values[-1]))
~~~

用法：`python perf/latency_probe.py`（隔离 venv，外部依赖先用桩服务）。

**要点**：① 问句固定、只用少量不同会话，避免命中不同缓存状态；② 外部模型不可用时先测「桩模型」版本，得到的是**我们自己的**耗时基线；③ 覆盖率插桩会显著改变耗时，基准环境用 `--no-cov`。

### 4.5 L3：并发与负载模型

**负载模型的选择**（这是压测最容易做错的地方）：

| 模型 | 含义 | 谁实现 | 风险 |
| --- | --- | --- | --- |
| 恒定并发（闭环） | 固定 N 个用户，各自循环；上一轮慢了这轮就晚发 | Locust 默认、k6 `constant-vus` | **协调遗漏**：服务变慢时压测端自动降速，掩盖排队延迟 |
| 恒定到达率（开环） | 按固定速率发请求，不管上一轮是否回来 | k6 `constant-arrival-rate`、vegeta、wrk2 | 压测端本身可能成为瓶颈 |
| 阶梯加压 | 并发或速率按阶段递增，找拐点与饱和点 | Locust `LoadTestShape`、k6 `ramping-vus` | 每阶段要等系统回到稳态，否则阶段间互相污染 |
| 浸泡 | 固定中等并发跑数小时 | 任一工具 | 时间成本高，但找内存与连接泄漏唯一可靠 |
| 破坏性 | 远超容量 | 任一工具 | 只在隔离环境做 |

**协调遗漏（coordinated omission）是压测里最贵的坑**：压测工具跟随服务端节奏而「忘记」记录本应发出的请求，使高延迟被系统性低估。wrk2 的卖点就是「恒定吞吐 + 精确到 9 位数的延迟」，vegeta 的 README 也明确写着「Avoids nasty Coordinated Omission」。**能开环就别闭环**。

**k6 场景骨架**（测 SSE 端到端，阈值即门禁）：

~~~javascript
// perf/scenarios/chat_stream.js
import http from 'k6/http';
import { Trend, Rate } from 'k6/metrics';
import { check } from 'k6';

const ttft = new Trend('ttft_ms', true);
const fail = new Rate('failures');

export const options = {
  scenarios: {
    ramp: {
      executor: 'ramping-vus',          // 阶梯加压；换成 constant-arrival-rate 即开环
      startVUs: 0,
      stages: [
        { duration: '30s', target: 5 },
        { duration: '1m',  target: 20 },
        { duration: '1m',  target: 50 },
        { duration: '30s', target: 0 },
      ],
    },
  },
  thresholds: {                          // 阈值即门禁，不是给人看的图
    'http_req_duration': ['p(95)<8000'],
    'failures': ['rate<0.01'],
  },
};

export default function () {
  const res = http.get(
    'http://127.0.0.1:8888/agent/chat/stream?conversationId=perf-' + __VU + '&query=压测固定问句',
    { timeout: '120s' });
  const ok = check(res, { 'status 200': (r) => r.status === 200 });
  fail.add(!ok);
  ttft.add(res.timings.waiting);
}
~~~

**Locust 骨架**（SSE 分段计时更方便；`FastHttpSession` 提供 `iter_lines` 可逐行消费）：

~~~python
# perf/locustfile.py
from locust import HttpUser, task, between, LoadTestShape

class ChatUser(HttpUser):
    wait_time = between(1, 3)          # 模拟思考时间
    @task
    def chat(self):
        with self.client.get(
            "/agent/chat/stream",
            params={"conversationId": "perf-" + str(self.environment.runner.user_index),
                    "query": "压测固定问句"},
            stream=True, catch_response=True, name="/agent/chat/stream") as r:
                for line in r.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    if line[5:].strip() not in ("", "[DONE]"):
                        r.failure("empty stream")   # 首个有效事件即视为首字到达
                        break
                r.success()

class Stages(LoadTestShape):
    def tick(self):
        run_time = self.get_run_time()
        if run_time < 30:  return (5, 5)
        if run_time < 90:  return (20, 10)
        if run_time < 150: return (50, 25)
        return None                     # 返回 None 结束压测
~~~

运行：`locust -f perf/locustfile.py --headless -u 50 -r 10 --run-time 3m --csv=perf/report`。

**要测的并发场景清单**（按本平台实际路径排）：

1. 并发 SSE 打开数（每条流 12.5 次/秒的 DB 轮询会放大）
2. 并发文件上传（含 embedding 阻塞）
3. 并发文档摄取（逐块 embedding 加 40 次 LLM 抽取）
4. 并发 Worker 消费（队列抢占、租约续期、事件追加）
5. 并发记忆投递（幂等键、退避、代次轮换）
6. 并发工作区召回（索引扫描与可能的重新 embed）

**压测端自身的坑**：Locust 官方提示 CPU 占用超过 90% 时应改用 `FastHttpUser`、改分布式，或检查脚本里是否有阻塞事件循环的库；`wait_time` 设太大会直接压低吞吐，容易被误判成「服务变慢」。

### 4.6 并发正确性：不变量测试

性能测试只回答「快不快」，**并发正确性要单独测**：压测过程中系统可能很快地产生错误结果。

用 Jepsen 的思路——施加并发与故障，然后检查**不变量**而不是看返回值：

| 不变量 | 场景 | 判定 |
| --- | --- | --- |
| 一次提交只产生一次执行 | 同一 conversation 并发提交 10 次 | 只有一条 run 进入 running，其余 409 |
| 租约过期不产生重复副作用 | 暂停 Worker 超过租约 | 原 run 终态唯一；重试 run 最多一条且事件可区分 |
| 记忆投递幂等 | 同一 job 并发投递 | `memory_event` 不重复；`memory_delivery` 只有一条 |
| 事件不丢不乱序 | 并发追加加 SSE 消费 | event_id 连续递增；SSE 收到的序号连续 |
| 取消与完成互斥 | 取消与自然完成同时发生 | run 只有一个终态；事件流只出现一个 terminal |
| SQLite 不出现写锁错误 | N 个写线程并发写 | 无 "database is locked" |

写法用标准库 `threading.Barrier` 做同步起跑，断言用现有 unittest 风格（仓库里 `python_backend/modules/context_engineering/test_chain.py:280-301` 已有 8 线程并发重试去重的用例可以照抄模式）。

**属性测试是更廉价的抓手**：Hypothesis 可以直接断言「分页不重不漏」「top-k 不超过候选集」「同一会话的事件序号单调」这类不变量。注意两个必设项：`deadline=None`（默认 200ms 会在慢 CI 上随机失败，是并发测试 flake 的经典来源）与 `derandomize=True`（让 CI 可复现）。

**故障注入**：toxiproxy 可在不改业务代码的前提下切断或延迟下游（模型、OpenViking、pgvector），用于验证降级路径；Chaos Mesh / Chaos Blade 用于更完整的混沌实验，但在本平台规模下**先做「杀 Worker」「断网络」「锁库」三个场景就够**。
### 4.7 L4：生产观测（线上才知道的事）

基准回答「改动是否变快」，观测回答「线上现在什么状况」。两者不能互相替代：基准在受控环境里给出因果，观测在真实环境里给出事实。**先有基准再改代码，改完用基准证明，用观测兜底。**

**复用现成埋点，不新造一套。** 仓库已有一条完整的事件与指标通道：可观测性路由提供运行指标汇总（`python_backend/api/routers/observability.py:107-121`）、单次运行的完整 trace 导出（`python_backend/api/routers/observability.py:125-135`）与按时间分桶的趋势（`python_backend/api/routers/observability.py:183-215`）；发布侧有灰度观察循环（`python_backend/api/routers/release.py:54-67`）与发布指标接口（`python_backend/api/routers/release.py:301-302`、`:444-445`），评估侧有后台评估与汇总指标（`python_backend/api/routers/evaluation.py:261-268`、`:290-301`）。L4 的第一原则是**在已有维度上补齐，而不是另起炉灶**。

已有可用的埋点点位：

| 埋点 | 位置 | 提供的维度 |
| --- | --- | --- |
| 单轮阶段耗时 | `python_backend/agents.py:287-295` | durationMs（总时长，但未分段） |
| 流式事件出口 | `python_backend/agents.py:729-730` | step / tool_start / tool_end / context_snapshot 原样下发 |
| 检索路由耗时 | `python_backend/agents.py:328-350` | durationMs + route |
| 检索命中耗时 | `python_backend/agents.py:511`、`:528` | durationMs + hits + route |
| Text2SQL 耗时 | `python_backend/agents.py:366-373` | durationMs + rows |
| LLM 生成耗时 | `python_backend/agents.py:643-659` | durationMs + outputChars |
| 终止原因 | `python_backend/agents.py:498` | stopReason（多跳检索的停止原因） |
| token 用量 | `python_backend/agents.py:531-536` | usage（输入/输出 token） |
| 预算消耗 | `python_backend/modules/context_engineering/budget.py:50-54`、`:99-103` | 预算水位 |

**已知的埋点缺口**（第一轮必须补）：`tool_start` / `tool_end` 事件（`python_backend/agents.py:729-730`）**不带耗时字段**——工具调用的耗时现在没法从事件流直接读出；而 `durationMs` 是整段耗时，没有 TTFT/TPOT 分段，也没有「请求进入网关」的入口时刻。

**RED 与 USE。** RED 看服务面（Rate、Errors、Duration），USE 看资源面（Utilization、Saturation、Errors）。对 Agent 系统，Duration 必须拆成 **TTFT / TPOT / 总时长**三段（见 §4.4），Rate 必须拆成「请求数」和「活跃流式会话数」两个维度——SSE 长连接下用 QPS 衡量吞吐完全失真：一路会话挂着 30 秒，QPS 可能只有 0.03，但它占着一条执行上下文。

四个黄金信号落到本系统：

| 信号 | 本系统的具体指标 |
| --- | --- |
| 延迟 | TTFT p50/p95/p99、总时长 p99、embedding 耗时 p95、pgvector 查询耗时 p95 |
| 流量 | 活跃 SSE 会话数、摄取任务数、Worker 消费速率、模型调用 QPM |
| 错误 | 意图门闸拒绝率、模型调用失败率、embedding 失败率、SSE 中断率、Worker 异常退出次数 |
| 饱和度 | 事件循环延迟、SQLite 写锁等待时长、队列长度、连接创建耗时 |

**指标口径纪律。** 每个指标必须写清四件事：单位、统计窗口、聚合方式（sum / count / max / histogram）、**标签基数上限**。最后一条最容易被忽略：把 conversation_id、run_id 这类高基数字段直接做成时序标签，几千次请求就能把时序库打爆。正确做法是用 exemplar 或 trace_id 做关联跳转，让指标保持低基数。

**分布式追踪与 GenAI 语义约定。** Agent 调用的 span 层次建议固定为：

```
agent.turn                      root
├── intent.classify
├── retrieval.search
│   ├── embedding.embed
│   └── pgvector.query
├── llm.chat                    gen_ai.*
└── execution.run
```

OpenTelemetry 的 GenAI 语义约定为 LLM span 规定了统一属性名（`gen_ai.system`、`gen_ai.request.model`、`gen_ai.usage.input_tokens`、`gen_ai.usage.output_tokens` 等）。跨厂商（OpenAI / Anthropic / 阿里云百炼）统一用这一套名字，将来换 Grafana 或接 Langfuse 都不用重写埋点。

**Tail sampling。** 全量采样成本不可接受，而 SSE 长流让 span 数量呈乘法增长。采样策略按两条规则走：慢的必采（总时长超阈值）、错的必采（出现 error 或 stopReason 为错误）。关键参数是 **decision_wait**（默认 30s）：它必须大于最长 trace 的完成时间，否则 trace 会被中途截断。本仓库的 SSE 长流可能超过 30s，所以有两条路——把长流拆成「会话 span + 分片 span」（推荐，采样友好），或者把 decision_wait 调大（简单但采样器内存压力上升）。

**告警用燃尽率，不用瞬时阈值。** 短时毛刺用瞬时阈值必然误报。燃尽率告警（多窗口多燃尽率）同时看长短两个窗口，判断错误率相对 SLO 预算的燃烧速度：

| 等级 | 长窗口 | 短窗口 | 燃烧预算 | 响应 |
| --- | --- | --- | --- | --- |
| 快速燃烧 | 1h | 5m | 2%（14.4× 速率） | 立即通知值班 |
| 慢速燃烧 | 6h | 30m | 5%（6× 速率） | 4 小时内处理 |

**SLO 只对用户感知的链路定。** 不要给每个内部接口都定 SLO，容易定出一堆没人看的告警。可用的三条：

1. **可用性**：非 5xx 响应比例 ≥ 99.9%（按月滚动）
2. **延迟**：首字延迟 p95 ≤ 目标值（由所选模型的典型延迟决定）
3. **正确性**：意图判定准确率 ≥ 目标值，用 `python_backend/modules/context_engineering/benchmark.py:88-105` 的评测集做回归基线

### 4.8 容量规划：并发上限怎么算

**Little's Law。** 系统中的平均并发数 = 到达率 × 平均停留时间：

```
L = λ × W
```

代入本系统的典型值做一次完整推算：

| 参数 | 取值 | 来源 |
| --- | --- | --- |
| 平均到达率 λ | 20 请求/秒（峰值） | 压测阶梯的拐点 |
| 平均停留时间 W | 8 秒（单轮对话总时长） | §4.4 的 TTFT + 生成耗时 |
| **理论并发数 L** | **160** | 20 × 8 |
| **崩塌点（75%）** | **120** | Netflix concurrency-limits 的建议 |

**为什么是 75% 而不是 100%。** 上限 100% 意味着资源刚好被用尽，此时任何抖动都会直接转化为排队，而排队又会拉长 W，W 变长又会抬高 L——正反馈直到崩塌。Netflix 的原始表述是「RPS 上限设在崩塌点的 75%」，落到并发模型即：把 limit 当作「资源可用度 100%」，在 75% 处开始拒绝，让系统在到达物理极限前就进入可控的降级状态。

**单机 SQLite 是容量天花板，不是调参能绕过的。** 所有状态落在同一个 SQLite 文件上（`python_backend/storage.py:19` 的全局 RLock 保护全局连接），写入吞吐是单机的。加上 `python_backend/storage.py:46` 每次操作新建连接的额外开销，本机的并发目标应定在 **100~200 条活跃流以内**。要再往上，只有两条路：换 Postgres（消除单文件写锁与 RLock 串行化），或把摄取/记忆投递这类写操作拆到独立进程。**在没有压测数字之前不要动架构**——先测出 SQLite 的实际写吞吐上限，再决定换不换。

容量表要按层维护，每层一个数字（本文档给出的是待实测的占位目标）：

| 层级 | 并发上限（待实测） | 硬约束来源 |
| --- | --- | --- |
| HTTP 请求处理 | TBD | 事件循环内同步 IO（§三 优化项 1） |
| 活跃 SSE 流 | TBD（目标 ≤ 200） | SQLite 写 + 每流 12.5 次/秒轮询 |
| 文档摄取任务 | TBD | embedding 速率 + 40 次 LLM 抽取串行 |
| Worker 执行任务 | TBD | 租约 45s 与单次异常终止 |
| 记忆投递 | TBD | 幂等键 + 代次轮换 |

### 4.9 过载保护：三层防线

过载时系统必须**有控制地退化**，而不是无控制地崩溃。分三层。

**第一层：自适应并发上限。** 并发上限不是写死的数字，而是按实测延迟动态调整。Netflix 的 concurrency-limits 用的是 **Vegas** 算法（把并发上限类比成 TCP 拥塞窗口）：

- 每个采样窗口结束时，若估计的排队长度**小于 alpha**（官方给的典型值是 2~3），上限 **+1**
- 若估计的排队长度**大于 beta**（官方给的典型值是 4~6 个请求），上限 **-1**

注意 alpha 与 beta 是**排队长度的阈值**，不是梯度倍数；beta 明显大于 alpha 意味着「触发收紧的条件比触发放宽更宽松」——这是有意的：宁可少接一点请求也别让队列失控。

**第二层：熔断。** Envoy 的默认熔断参数可以直接作为起点——**consecutive_5xx=5、interval=10s、base_ejection_time=30s、max_ejection_percent=10%**。映射到本系统的下游：**模型调用、embedding、OpenViking、pgvector 各自独立熔断**，四个舱壁互不拖累。一个下游挂掉时，只该让依赖它的请求失败，而不是让整个进程被拖死。注意 max_ejection_percent=10% 的含义是「最多驱逐 10% 的实例」——这是防止熔断本身造成雪崩的保护。

**第三层：负载丢弃与舱壁。**

负载丢弃的优先级原则：**保护已经在跑的流，放弃刚进来的新流。**

- 新请求排队超过阈值 → 直接返回 503，带 `Retry-After`
- 丢弃时必须**明确告知用户**「当前负载高，请稍后再试」，不要静默挂起
- 舱壁隔离四个资源池：SSE 流、文档摄取、Worker 执行、记忆投递。**互不借用线程与连接**——摄取任务不能占满 HTTP 线程池，记忆投递不能抢 Worker 的队列槽位

**重试预算。** 无脑重试在过载时会加剧拥塞，规则如下：

1. 只有幂等操作可重试；非幂等操作重试等于制造重复副作用（参见 §4.6 的不变量）
2. 总重试数不超过总请求数的 10%（重试预算）
3. 指数退避**必须带抖动**——没有抖动的同步退避会形成周期性尖峰
4. 只对 429 / 503 / 连接错误重试；4xx 业务错误直接失败
5. 熔断打开时**不重试**，直接失败

### 4.10 工具选型对照表

star 数为 2026-11-10 的 GitHub API 快照（会变，只用于横向比较量级，不用于精确引用）。

| 工具 | star | 层级 | 用途 | 何时用 | 已核实的关键默认值 |
| --- | --- | --- | --- | --- | --- |
| [k6](https://github.com/grafana/k6) | ~32k | L3 | 场景化负载生成 + 阈值门禁 | 开环到达率压测、CI 门禁 | `ramping-vus` / `constant-arrival-rate`（开环）、`thresholds` 断言 |
| [Locust](https://github.com/locustio/locust) | ~28k | L3 | 自定义 Python 用户、闭环压测 | SSE 分段延迟、需要复杂用户行为时 | `FastHttpSession.iter_lines`、`LoadTestShape`、`constant_pacing` 等等待模式 |
| [py-spy](https://github.com/benfred/py-spy) | ~16k | 任意 | 无侵入采样 profiler | 定位 CPU 热点，不改代码 | `--rate`、`--gil`、`--native`、`--subprocesses`、`--format` |
| [Scalene](https://github.com/plasma-umass/scalene) | ~13.5k | 任意 | CPU/GPU/内存 + 墙钟三分 | 区分「真慢」还是「等 IO」 | 需额外安装 |
| [Hypothesis](https://github.com/HypothesisWorks/hypothesis) | ~9.1k | L1/L3 | 属性测试，随机化不变量 | 分页/top-k/序号单调性 | 必设 `deadline=None`、`derandomize=True` |
| [toxiproxy](https://github.com/Shopify/toxiproxy) | ~12.5k | L3 | 代理层故障注入 | 断网/延迟/断开下游 | 不改业务代码 |
| [pytest-benchmark](https://github.com/ionelmc/pytest-benchmark) | ~1.5k | L0/L1 | 单元/组件基准 + 回归门禁 | CI 里比对基线 | `--benchmark-compare-fail=min:5%`、`--benchmark-disable-gc`、`--benchmark-min-time 0.000005`、`--benchmark-max-time 1.0`、`--benchmark-min-rounds 5`、`--benchmark-save`、`--benchmark-between` |
| [asv](https://github.com/airspeed-velocity/asv) | ~1.0k | L0 | 跨提交性能趋势 | 需要「这个提交比上个慢了吗」 | 维护多个分支基准 |
| [pyperf](https://github.com/psf/pyperf) | ~1.0k | L0 | 严谨微基准（控制环境） | 需要可信的算法级数字 | 比 pytest-benchmark 更严格 |

**选型结论**：CI 门禁用 **pytest-benchmark**（门禁语义最直接）；并发压测用 **k6** 优先（阈值即门禁、无需写 Python），SSE 场景用 **Locust**（需要分段计时与流式读取）；热点定位用 **py-spy**（零侵入，怀疑 CPU 瓶颈时先上它），怀疑「等 IO」而不是「算得慢」时换 **Scalene**；跨提交趋势用 **asv**；严谨算法级数字用 **pyperf**。

**不引入的东西**：本阶段不引入向量数据库替换、不引入分布式队列、不引入 APM 商业 SDK。理由在 §4.8——单机 SQLite 的容量上限还没测出来，在没有数字之前换架构是赌博。

### 4.11 测量纪律

测量方法本身就是被测对象的一部分，纪律不守住，数字没有意义。

1. **先定口径，再测。** 指标定义、单位、窗口、聚合方式写在跑之前。
2. **不跳层。** L0 单元 → L1 组件 → L2 端到端 → L3 并发 → L4 生产。跳层就无法归因：端到端变慢，你没法知道是算法、IO、还是排队。
3. **隔离外部依赖。** 基准里 embedding 与 LLM 必须打桩或固定回放，否则测的是网络不是代码。
4. **环境固定。** 同一台机器、同一份数据集、固定的 warmup 轮数、记录 CPU/内存/Python 版本/依赖版本。
5. **多轮取分位数。** 至少 5 轮，看 p50/p95，不看单次结果。
6. **GC 要测两次。** Python 用 `--benchmark-disable-gc` 测纯算法耗时，再跑一次带 GC 的真实耗时，两个数都要记录。
7. **噪声阈值。** 差异小于 3~5% 一律视为噪声，不写进结论。
8. **一次只改一个变量。** 同时改三处然后说「快了 30%」，无法归因，等于没测。
9. **基准失败不许重跑蒙混。** CI 门禁的失败必须解释或回退，不能靠「再跑一次就绿了」。
10. **测量本身要版本化。** 基准脚本进仓库，基线文件进仓库，改动一起 review。

### 4.12 报告格式与回归门禁

每次测量产出一份固定格式的报告，避免结果只存在于某个人脑子里：

```
# 性能报告 YYYY-MM-DD / <变更名>
- 机器：<CPU> / <内存> / Python <版本> / commit <sha>
- 层级：L0 | L1 | L2 | L3
- 被测对象：<文件:函数>

## 结论
<一句话：这个改动让 X 从 A 变成 B，分位数为 ...，是否达标>

## 数据
| 场景 | 指标 | 基线 | 本次 | 变化 | 是否达标 |
| --- | --- | --- | --- | --- | --- |
| ... | p95 延迟 | ... | ... | ... | 是/否 |

## 方法
- 轮次/时长/warmup：
- 打桩方式：
- GC 开关：

## 噪声与风险
- 本次结果的已知不确定因素：

## 未覆盖
- 本次没有测到的部分（明确写出来，不让读者误以为全面覆盖）
```

**CI 门禁**分三级，强度递增：

| 门禁 | 工具 | 判据 | 阻断级别 |
| --- | --- | --- | --- |
| 单元基准回归 | pytest-benchmark | `--benchmark-compare-fail=min:5%` | 警告 → 阻断（稳定后） |
| 端到端延迟 | k6 thresholds | p95 ≤ 目标值，错误率 ≤ 目标值 | 阻断 |
| 并发正确性 | unittest + Hypothesis | 不变量全部成立 | 阻断（永远阻断，不设警告期） |

**并发正确性门禁永远阻断**——性能可以退让，正确性不能。它跑得快（秒级），成本低，没有理由不设。

## 五、落地顺序

三轮，每轮都有可验证的产出，不做大爆炸式改造。

### 第一轮：装测量能力（不动业务代码，约 1~2 天）

**目标**：先能测，再谈改。这一轮不碰任何生产逻辑。

- L1：给检索融合（`python_backend/modules/retrieval/fusion.py:6-23`）、上下文预算（`python_backend/modules/context_engineering/budget.py:57-98`）、向量点积（`python_backend/modules/retrieval/workspace_index.py:377`）加 pytest-benchmark 用例
- L2：落地 `perf/latency_probe.py`，能对指定会话跑一次端到端并输出 TTFT/TPOT/总时长分段
- L3：落地 `perf/k6/baseline.js` 冒烟场景 + `perf/locustfile.py` 的 SSE 场景
- 补齐 §4.7 的埋点缺口：durationMs 拆成 TTFT/TPOT 两段（`python_backend/agents.py:287-295` 附近）

**验收**：能对当前 HEAD 跑出一份基线报告，且报告中「未覆盖」一节如实列出还没测的场景。

### 第二轮：修已知热点（按收益排序，约 3~5 天）

**目标**：只修第一轮测出来的问题，收益排序按「耗时占比 × 修复成本」。

1. **embedding 批量 + 移出事件循环**：`python_backend/vector_store.py:133-142` 与 `:159-179` 目前逐块调用 embedding（批量接口 `:101` 已存在但摄取路径没用），而调用发生在 `python_backend/fastapi_app.py:218` 与 `:253` 的事件循环里——既拖慢单请求，又阻塞并发
2. **SSE 轮询降频或改事件推送**：`python_backend/api/routers/execution.py:41-63` 每 80ms 查两次 SQLite，20 条并发流就是每秒 500 次查询
3. **存储层开 WAL + 复用连接**：`python_backend/storage.py:19`、`:46`、`:135`
4. **文档抽取并发化**：`python_backend/documents.py:689` 的最多 40 次串行 LLM 抽取

**验收**：第二轮结束时，§三 优化清单里标 P0 的条目要么做完，要么有实测数据说明「为什么可以不做」。

### 第三轮：把门禁固化 + 上生产观测（持续）

- CI 接入门禁（§4.12）
- L4 观测补齐：GenAI 语义约定的 span 属性、燃尽率告警、SLO
- 建立容量表实测数字（§4.8）
- 过载保护落地：自适应并发上限、熔断、舱壁

## 附录 A：perf/ 目录骨架

新增目录（仅骨架，不含实现细节以外的业务逻辑）：

```
perf/
├── latency_probe.py          # L2 端到端分段计时客户端
├── locustfile.py             # L3 SSE 并发压测
├── k6/
│   └── baseline.js           # L3 场景与阈值
├── benchmarks/               # L0/L1 pytest-benchmark 用例
│   ├── test_fusion.py
│   ├── test_budget.py
│   └── test_workspace_index.py
└── invariants/               # L3 并发正确性不变量
    ├── test_execution_idempotency.py
    ├── test_memory_delivery.py
    └── test_event_ordering.py
```

约定：

- **不新建 README**——按仓库规则，说明写在根 README 或本文件里
- 每个脚本文件头写清：用途、依赖、如何运行、产出什么
- 脚本必须能在没有 Worker 的情况下跑通单元部分（SSE 场景除外）
- 不变量测试复用仓库现有的 unittest 风格；可参考 `python_backend/modules/context_engineering/test_chain.py:280-301` 的 8 线程并发去重用例

**不变量测试骨架**（`perf/invariants/test_execution_idempotency.py`，与 §4.6 的表格对应）：

```
import threading
import unittest


class ExecutionIdempotencyTest(unittest.TestCase):
    """同一 conversation 并发提交，只能有一次执行真正进入 running。"""

    def test_concurrent_submit_produces_single_run(self):
        barrier = threading.Barrier(10)
        results = []
        lock = threading.Lock()

        def submit():
            barrier.wait()            # 同步起跑，制造真正的竞争
            outcome = self._submit()
            with lock:
                results.append(outcome)

        threads = [threading.Thread(target=submit) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        running = [r for r in results if r["status"] == "running"]
        rejected = [r for r in results if r["status"] == "rejected"]
        self.assertEqual(len(running), 1, f"期望只有 1 条 running，实际 {len(running)}")
        self.assertEqual(len(running) + len(rejected), len(results))
```

## 附录 B：参考来源

访问日期均为 2026-11-10。star 数为当日快照。

### 开源工具

- k6 — https://github.com/grafana/k6
- Locust — https://github.com/locustio/locust
- pytest-benchmark — https://github.com/ionelmc/pytest-benchmark
- py-spy — https://github.com/benfred/py-spy
- Scalene — https://github.com/plasma-umass/scalene
- Hypothesis — https://github.com/HypothesisWorks/hypothesis
- toxiproxy — https://github.com/Shopify/toxiproxy
- asv — https://github.com/airspeed-velocity/asv
- pyperf — https://github.com/psf/pyperf
- Netflix concurrency-limits — https://github.com/Netflix/concurrency-limits

### 大厂与官方实践

- Google SRE Book: Monitoring Distributed Systems — https://sre.google/sre-book/monitoring-distributed-systems/
- Google SRE Book: Handling Overload — https://sre.google/sre-book/handling-overload/
- Google SRE Workbook: Implementing SLOs — https://sre.google/workbook/implementing-slos/
- OpenTelemetry GenAI 语义约定 — https://opentelemetry.io/docs/specs/semconv/gen-ai/
- OpenTelemetry Collector 配置（含 tail sampling 处理器）— https://opentelemetry.io/docs/collector/configuration/
- Envoy 熔断默认值 — https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/upstream/circuit_breaking
- 阿里云 PTS 全链路压测 — https://help.aliyun.com/zh/pts/
- vLLM 指标口径 — https://docs.vllm.ai/en/latest/usage/metrics/
- Anthropic 速率限制 — https://docs.anthropic.com/en/api/rate-limits

### 本文引用的仓库位置（均已逐条核对行号）

`python_backend/fastapi_app.py:128`、`:218`、`:253`、`:269`、`:379`
`python_backend/vector_store.py:101`、`:114`、`:133-142`、`:159-179`
`python_backend/api/routers/execution.py:41-63`
`python_backend/api/routers/observability.py:107-121`、`:125-135`、`:183-215`
`python_backend/api/routers/release.py:41-52`
`python_backend/api/routers/evaluation.py:31-42`
`python_backend/storage.py:19`、`:46`、`:135`
`python_backend/documents.py:689-692`
`python_backend/agents.py:287-295`、`:328-350`、`:358-374`、`:498`、`:531-536`
`python_backend/modules/retrieval/fusion.py:6-23`
`python_backend/modules/retrieval/workspace_index.py:377`
`python_backend/modules/context_engineering/budget.py:57-98`、`:98`、`:100`
`python_backend/modules/context_engineering/benchmark.py:88-105`
`python_backend/modules/intent/classifier.py:203`
`python_backend/modules/workspaces/context.py:58-59`
`python_backend/modules/execution/store.py:44`
`python_backend/workers/execution_worker.py:189`、`:320-332`
`python_backend/modules/context_engineering/test_chain.py:280-301`
