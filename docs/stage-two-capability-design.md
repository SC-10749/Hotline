# Hotline 第二阶段能力设计（检索、记忆与运营化）

状态：草案。本文承接 [上下文工程实现与验收](./context-engineering-design.md)，针对其中列出但尚未落地的十项能力，先给出业界做法与本仓库差距，再给出可执行方案。

调研时间：2026-11-09。一手来源为项目 README、官方文档与论文；博客类二手来源已在参考来源里标注。

阅读约定：每节分三段——「业界怎么做」只写可核实的机制，不写营销词；「本仓库现状」给文件位置；「建议方案」给接口、状态机或口径，能落到可执行测试的才写。

---

## 一、总览

| # | 领域 | 业界成熟度 | 本仓库现状 | 建议优先级 |
| --- | --- | --- | --- | --- |
| 1 | 融合后重排层 | 成熟（cross-encoder 已标准化） | 无重排，只有 RRF 融合 | P0 |
| 2 | 冲突与时效识别 | 有成熟参考（时序知识图谱） | 状态只有 active/completed/cancelled | P0 |
| 3 | 多用户与权限模型 | 成熟（检索期裁剪是共识） | 单用户，无 user/tenant 概念 | P1（上生产前必须） |
| 4 | 向量生产流水线与成本 | 成熟（摄取是独立流水线） | 在查询路径现算，无队列无预算 | P0 |
| 5 | 三套存储的一致性与并发 | 成熟（outbox + 幂等键） | 三处写入无顺序与补偿定义 | P0 |
| 6 | OpenViking 真实部署 | 有产品化参考 | 只有协议桩，无真实数据 | P1 |
| 7 | 评测门禁 | 成熟（两段式评测 + CI 门禁） | 两个标注集，语义那条依赖真实服务 | P0 |
| 8 | 前端呈现 | 成熟（引用可核查是标配） | 证据无出处展示，54 处演示回落 | P1 |
| 9 | 业务侧可观测性 | 成熟（trace + 成本 + 业务指标） | 只有运行与事件维度 | P1 |
| 10 | 跨工作区共享知识 | 成熟（分层存储 + 权限过滤） | 刻意未改共享表，只有工作区私有 | P2 |

「刻意未做」不等于「做错了」：第十项是因为共享表属于别人模块的边界，本轮先在工作区内自洽；第十项与第三项一起做才有意义。

---

## 二、融合后重排层

### 业界怎么做

- 北京智源（FlagEmbedding）把重排做成了独立模型族：`bge-reranker-base/large` 是 cross-encoder，官方说明是「比 embedding 模型更强，用来对 embedding 返回的 top-k 文档重新排序」。后续又出了轻量版、layerwise 版和基于 M3/LLM 的重排研究目录，说明「模型打分」是重排的上限形态但不是唯一起点。
- 同一个仓库的 `bge-m3` 把多路召回做成一件模型：dense retrieval + sparse retrieval + multi-vector（ColBERT 式），也就是「先多路召回再融合」本身可以交给一个模型做。
- 腾讯 WeKnora 在检索链路上同时用关键词检索、稠密向量检索与父子分块，并支持火山引擎 rerank；它的更新日志里有一条「passage cleaning for rerank」，即重排前先清洗片段，这是很多实现会漏掉的前置。
- 学术界对分块策略的对照实验给了量化结论：contextual retrieval（入库前用模型给每块补上下文）平均 nDCG@10 约 72.4，late chunking 约 61.0，但索引耗时约为 1890 ms/文档 对 15.81 ms/文档（约 120 倍）。这条数据说明「更聪明的入库」和「更贵的入库」是同一根杠杆的两端。

### 本仓库现状

- `python_backend/modules/retrieval/fusion.py` 的 `fuse_evidence` 做 RRF（1/(60+rank)）合并、词面命中数打破同分、归一化文本去重。
- 没有重排层。检索层是四层词面（精确 token / 中文 trigram / 中文 bigram / LIKE 兜底）加一条语义通道，合并后直接进上下文装配。

### 建议方案

分两级，默认只走第一级。

**第一级：确定性重排（无模型调用）**

对融合后的前 40 条候选打分，输出 8–12 组证据。打分信号全部是本地可算的：

| 信号 | 计算方式 | 权重方向 |
| --- | --- | --- |
| 通道一致性 | 被几个通道命中（词面 / 语义 / 父块展开） | 越高越好 |
| 精确 token 命中 | 是否命中编号、错误码这类高区分度 token | 命中则强加权 |
| 词面覆盖 | query 词项在片段中的覆盖率（复用现有 trigram/bigram 命中） | 越高越好 |
| 来源层级 | 命中标识符的片段优于泛化描述 | 越高越好 |
| 新鲜度 | source marker 的更新时间 | 越新越好（权重最小） |

`fuse_evidence` 保留为第一阶段合并，重排作为可选第二阶段；重排异常、超时或候选不足时直接退回融合结果，不阻断回答。

**第二级：模型重排（有预算）**

只在两种情况下启用：候选里出现多个通道互相冲突，或用户明确要求「精确/最新」。约束写死：单次候选上限 12 条、调用超时 800 ms、失败即退回第一级、每轮最多一次。这样成本可预测，也避免把重排变成新的延迟来源。

**验收**

- 在现有两个标注集（`test_recall_quality.py` 13 条词面、`test_semantic_recall.py` 7 条语义）上，重排后 Recall@8 不低于重排前，nDCG@8 必须提升。
- 新增「同名不同主题」干扰用例，检验重排能否把主题一致的那条排到前面。

---

## 三、冲突与时效识别

### 业界怎么做

- Zep 团队的 Graphiti 把记忆做成**时序上下文图**：事实是带有效期窗口的边，双时态（事件时间与记录时间）跟踪，冲突时**自动失效旧边而不是删除**，历史保留；论文《Zep: A Temporal Knowledge Graph Architecture》(arXiv:2501.13956) 把「自动事实失效 + 保留完整时序历史」明确列为与 GraphRAG 的差异——GraphRAG 靠模型摘要判断矛盾，Graphiti 靠有效期窗口自动失效。
- 同一份 README 强调另外两件事：事实与关系都能追溯到产生它们的原始 episodes（出处可追），以及用 Pydantic 定义本体来避免实体类型坍缩成通用标签。
- Mem0 在 v3 把写入改成 ADD-only：一次抽取、只增不覆盖，冲突靠召回排序与实体链接解决，不在写入时消解。它的理由是「覆盖式写入要先判断新旧谁对，这本身又是一次不可靠的模型判断」。本仓库的 `memory_event` 只增不改加 status 字段，与这个方向一致。
- 腾讯 WeKnora 的跨会话长期记忆是「自动抽取 + 用户确认」，记忆类型为 profile / preference / fact / task / interest，并提供 `search_memory` 工具。
- 阿里云 AnalyticDB for MySQL 的 AI Agent MemStore 把记忆做成服务，统一接口是检索记忆 / 查看记忆 / 删除记忆 / 新增记忆，服务内置记忆分层管理、周期性反思、一致性维护与智能遗忘。

### 本仓库现状

- 任务状态在 `python_backend/modules/memory/store.py`，取值只有 active / completed / cancelled，用 revision 乐观锁。
- 长期记忆是追加语义，冲突只在召回排序时体现。
- 全仓 grep `conflict` 只命中治理与评测模块的「重复决策冲突」，与记忆事实冲突无关。

### 建议方案

**事实结构扩展**

任务事实增加 `validFrom` / `validTo` / `supersededBy` / `sourceId`（消息 ID，已有）。语义不变式：

- 冲突时不删除旧事实，只置 `validTo` 并指向新事实；历史完整保留。
- 召回时按 `validFrom` 倒序，同 key 只取当前有效值。
- 用户明确撤销走 `cancelled`（与「被更新覆盖」区分开，两者在 UI 与审计上含义不同）。

**判定分级**

| 情形 | 判定方式 | 处理 |
| --- | --- | --- |
| 同 key、同 scope、不同值，且值是标识符/数字/枚举 | 确定性判定 | 自动失效旧值，写新值 |
| 同 key、同 scope、语义相近但不同表述 | 模型判定 | 低置信度时两条并存，靠时间戳排序，模型看到时间戳自行取舍 |
| 值需要归一化（大小写、空白、别名、单位） | 归一化表 + 规则 | 归一后相同则不算冲突 |
| 跨作用域（不同 workspace 或不同任务） | 不判定 | 作用域不同即不是冲突 |

**边界**：冲突判定只在任务状态层做。长期记忆层保持追加语义（Mem0 方向），靠时间戳与实体链接在召回时排序，不在写入时互相覆盖。

**人工确认**：沿用 WeKnora 的「自动抽取 + 用户确认」模式——检测到高价值冲突时，在门闸澄清里带出「检测到与之前说法不一致，以最新为准吗」，用户确认后写入并把旧事实失效。

**验收**

- 改口用例：第 10 轮修改一条约束，第 30 轮不复活旧值（现有 `test_chain.py` 已有前半段，需要补后半段断言）。
- 显式撤销与被覆盖两种路径分别可查。
- 跨会话（不同 conversation、同一 workspace）仍能取到当前有效值。

---

## 四、多用户与权限模型

### 业界怎么做

- Azure AI Search 的文档级访问控制给出四种机制，其中最基础的是「安全过滤器」：应用把用户或组身份以字符串形式塞进查询过滤条件，不匹配的直接排除；更完整的形态是把查询令牌背后的安全主体与文档返回的权限元数据比对（POSIX 式的 ACL/RBAC 镜像），以及索引器侧打敏感度标签。共同点是**过滤发生在查询执行期，而不是检索之后的补救**。
- 火山引擎 VikingDB 的架构里，租户隔离与权限管理器放在控制平面，与数据平面的写入/读取分离；索引层同时提供 HNSW、IVF、DiskANN 与混合索引，存储层区分稠密向量、稀疏向量与多模态。

### 本仓库现状

- 单用户部署。作用域派生在 `python_backend/modules/memory/store.py`：`scope_id = sha256('workspace:' + workspace_id)`。
- 「权限」目前只有两处含义：Agent 工具白名单（`modules/execution/tools.py`）与技能工具的文件访问过滤。
- 全仓无 `user_id` / `tenant` 概念。

### 建议方案

**身份与作用域**

`identity = (user_id, workspace_id, role)`，`scope_id` 升级为对 user 与 workspace 共同派生。绑定时仍按「同一会话不可切换工作区」的既有约束。

**检索期过滤**

每个来源带 `access_tags`（用户 / 组 / 角色 / 公开），检索条件里带上调用者的 tags，过滤在检索期完成。两道防线：

1. 检索过滤（向量库 metadata + 本地索引 workspace/tags 条件）；
2. 装配前复核（上下文装配前再校验一次证据的 tags，防的是「召回对了但装配错了」）。

第 2 道不能省：过滤一旦只做在检索层，任何绕过检索直读原文的路径（`read_source`、原文分页工具）都会成为越权口子。

**落地顺序**

先在本地索引层做（workspace + tags 条件），不动共享向量库表结构；共享库那侧用 metadata 过滤，需要加字段时走向量库自己的迁移。

**审计**：命中与拒绝都写事件。WeKnora 有 per-KB activity audit，我们复用现有 `execution_run_events` 表即可。

**验收**：越权召回 0 次（这条设计文档 §7.2 已有）；补跨工作区、跨用户两组用例。

---

## 五、向量生产流水线与成本

### 业界怎么做

- 一份系统设计文章把 RAG 当流水线拆开：检索调用只是最后几毫秒，上游的摄取、切块、向量化、索引、重排每一段都决定答案是否站得住；核心权衡是吞吐对新鲜度、召回对延迟、存储成本对检索质量；并指出 embedding 生成才是摄取吞吐的瓶颈所在（二手来源）。
- LlamaIndex 的 IngestionPipeline 把「节点 + 转换组合」的哈希作为缓存键（IngestionCache），相同组合的重复运行直接复用结果，避免重复 embedding。这同时也是幂等摄取的标准做法（官方文档）。
- VikingDB 的架构里有独立的「向量化计算节点」与「索引构建节点」，即向量生产与索引发布是离线构建能力，不是查询路径上的动作。

### 本仓库现状

- `WorkspaceIndex.embed_directory` 在**查询路径**上被调用（`modules/workspaces/context.py` 的 `recall_workspace` 每次都会同步一次），每次最多处理 40 个文件。
- 没有预热、没有队列、没有成本上限、没有 embedding 缓存；文件向量以 (workspace, source) 为键存一份，同一份内容在不同工作区会重复计算。

### 建议方案

**三段式：探测 → 生产 → 发布**

| 段 | 触发 | 动作 |
| --- | --- | --- |
| 探测 | 查询路径（只读 stat） | 发现变更文件，登记待生产任务 |
| 生产 | 后台队列 | 批量调用 embedding（支持一次多输入） |
| 发布 | 生产完成 | 写入向量表并更新 marker |

查询路径只做探测，绝不等待 embedding。

**缓存键**

`sha256(模型名 + 维度 + 规范化文本)`。同一份文件内容在多个工作区只算一次，缓存放本地（与索引同库或单独一张表），键变化即失效——换 embedding 模型天然触发重算，不需要额外的版本协议。

**预算**

每工作区每日 embedding token 上限；超预算时只生产「本轮查询命中的候选文件」，其余排队；积压超阈值时降级为纯词面通道并在 manifest 里标注。

**版本与重建**

source marker 里带 embedding 模型名与维度。模型换了，marker 不匹配即自动重算，旧向量按 marker 分区保留，可灰度切换。

---

## 六、三套存储的一致性与并发

### 业界怎么做

- 分布式的常规做法：本地事务 + outbox 记录待投递事件，后台按幂等键重试；派生物失败只降级，不回滚事实源。
- LlamaIndex 的摄取管道把 docstore 与 vector store 双写，并用节点 ID 做幂等 upsert（官方文档）。
- WeKnora 的 Lite 模式用 SQLite + 内存队列，明确目标是「无外部依赖、可本地跑」，说明单机形态也需要一套明确的队列与状态语义，而不是靠进程内隐式行为。

### 本仓库现状

- 三处写入：本地 SQLite 索引（`workspace_index.py`）、pgvector（`vector_store.py`）、OpenViking（`modules/memory/openviking.py`）。
- 写入顺序、失败补偿、幂等键都没有定义。派发失败目前只是记日志，事实源与派生物可能长期不一致。
- 多 Worker 同时写同一工作区没有锁或租约。

### 建议方案

**单一事实源**

本地 SQLite 索引是事实源；pgvector 与 OpenViking 都是**可重建的派生物**。派生物写失败只标记为待重建，不影响事实源，也不回滚已写入的事实。这条不变式比「三写事务」简单得多，也更容易验证。

**outbox**

本地事务内同时写事实与一条待投递记录（表 `index_outbox`：id、scope、source_id、marker、目标存储、状态、重试次数、最后错误）。后台按目标逐个投递，投递成功标 done，失败按退避重试，永久失败留在表里可查可人工重放。

**幂等键**

`(scope_id, source_id, marker)`。同一键重复投递不产生重复行，也不产生重复记忆事件。

**并发**

每工作区一个写入租约（租约表 + 过期时间），同一工作区的写入串行，不同工作区并行。查询不占租约——查询只读 SQLite，SQLite 本身在 WAL 下支持多读单写。

**对账**

定时任务比对本地 marker 与派生物实际状态，列出漂移（本地有、向量库没有；向量库有、本地已删），生成修复任务。

---

## 七、OpenViking 真实部署

### 业界怎么做

- 阿里云 AnalyticDB for MySQL 的 AI Agent MemStore 把记忆做成独立服务：统一接口（检索 / 查看 / 新增 / 删除）、内置记忆分层管理、周期性反思、一致性维护与智能遗忘，并提供嵌入式 SDK 供本地开发。这说明记忆后端的产品化形态是「服务 + 统一接口 + 内置治理」，不是「一个 HTTP 客户端」。
- 字节 Eino（CloudWeGo）明确 Memory / Session / Store 属于业务层概念，框架只负责消息处理与工具编排，记忆存储由业务方决定。本仓库的边界与此一致：Hotline 负责用户与工作区隔离、脱敏、预算，OpenViking 负责抽取与存储。
- Zep / Graphiti 用图结构承载记忆，事实带有效期窗口、关系可追溯到原始 episodes。
- DeerFlow 2.0（字节开源 SuperAgent）把 memory、skills、sandbox 作为编排层的三大外部能力，记忆不是硬编码在流程里的。

### 本仓库现状

- `python_backend/modules/memory/openviking.py` 是完整的 HTTP 客户端，测试用本地协议桩。
- 本机没有部署服务，抽取质量、抽取延迟、并发行为都没有实测数据。这是设计文档 §9 列的最大未知项。

### 建议方案

**部署形态**：独立服务 + 现有客户端不变。需要补的是部署、配置、就绪检查与运维手册，而不是改客户端。

**对账与降级**：派生态的语义已在第六节定义（outbox + 对账）。OpenViking 侧额外需要：

- 后端状态显式暴露：抽取延迟 P95、队列积压、失败码分布；不可用时在模型输入里给出实际状态（现有实现已有此路径）。
- 抽取质量验收口径：事实抽取准确率、同义去重率、误抽取率、事实到来源消息的可追溯率。

**代次与 Peer**：现有 generation 轮换保留（撤销即换代，不物理删除），加「当前代次的抽取水位」指标，便于回答「记忆落后了多少」。

**验收**：先在目标环境跑一份 50 条真实问答的抽取评测，再决定是否把抽取质量作为门禁。

---

## 八、评测门禁

### 业界怎么做

- RAGAS 与 ARES 是参考框架，DeepEval / TruLens / RAGChecker 负责生产集成。共识是**两段式评测**：检索段看 precision@k、recall@k、nDCG（排序质量）、MRR（首个相关结果的位置）；生成段看 faithfulness（是否忠于召回材料）、answer relevance（是否切题）、citation coverage（主张是否带出处）。两段失败方式不同，必须分开测。
- ARES 的思路是用少量人工标注样本校准自动判据，降低「用模型判模型」的不可信度。
- Langfuse / LangSmith / Phoenix 之类的可观测平台把一次请求记成树形 trace，评测挂在 trace 上。

### 本仓库现状

- `python_backend/modules/retrieval/test_recall_quality.py`：13 条词面问法 + 干扰材料，Recall@8 实测 1.0。
- `python_backend/modules/retrieval/test_semantic_recall.py`：7 条同义问法，需要真实 embedding 服务，默认跳过（`HOTLINE_SEMANTIC_EVAL=1` 打开）。
- 压缩保真度、任务恢复没有独立用例；容量分级脚本已存在（`modules/context_engineering/benchmark.py`）。

### 建议方案

**三层门禁**

| 层 | 依赖 | 内容 | 何时跑 |
| --- | --- | --- | --- |
| L0 离线 | 无网络、无真实服务 | 标注集、回归用例、越权用例、预算不变量 | 每次提交，必过 |
| L1 真实服务 | embedding + 模型 | 语义召回集、抽取质量、端到端答案质量 | 夜间或发版前 |
| L2 线上抽样 | 真实会话 | 失败样本采集与人工标注 | 持续 |

**指标口径**（每条都要求带来源与版本）：

- 检索：Recall@8、nDCG@8、MRR、分通道命中率（词面 / 语义）、越权召回次数（必须 0）。
- 生成：faithfulness、引用覆盖率、答案是否被原文支持。
- 系统：输入预算超限率、门闸澄清率、端到端时延 P95、每轮 embedding token 成本。

**数据集版本化**：标注集落 `python_backend/modules/retrieval/fixtures/`（JSON + 版本号 + 变更说明）。改动标注集必须 bump 版本，历史结果按版本可比。

**失败回流**：L2 采到的低分样本进人工队列，标注后进 L0 集，成为常驻回归。

**参考实现**：RAGAS / ARES 的两段式指标口径可以直接借鉴判定维度，但不在本仓库引入这些依赖——自研判定器 + 标注集足够，避免为一个指标体系引入一整套第三方栈。

---

## 九、前端呈现

### 业界怎么做

- 腾讯 WeKnora 的定位是「answers you can check」：RAG 答案带引用，配合父子弹块与可编辑、可留版本的分块，让用户能回到原文核对。
- Dify 与 Open WebUI 这类产品的共同做法是把引用做成可点击的卡片，点击展开原文片段。
- LangSmith 的 trace 视图把「检索到了什么、模型用了哪几条」摊开给用户看。

### 本仓库现状

- 后端证据已经带来源与分层（`workspace:` 前缀 + abstract / overview / detail），但聊天页没有展示出处，也没有「读原文」入口。
- 前端仍有 54 处 `demo` / 「演示」回落（分布在 4 个文件），连接失败与真实为空共用同一套演示数据。

### 建议方案

**证据卡片**（每条命中一张）：

- 来源：文件路径或文档名 + 所属工作区。
- 层级：abstract / overview / detail，可切换。
- 命中原因：精确 token / 中文 trigram / 中文 bigram / LIKE 兜底 / 语义相似度（带分数）。
- 「读原文」：分页打开完整来源，沿用已有 `read_source` 能力。

命中原因要由后端给出（hits 里带 reason 与 score），前端只负责展示；否则「为什么这条被选中」无法解释。

**空状态区分**：连接失败与真实为空用不同文案与不同视觉，演示数据只在明确的「演示模式」下出现并带标识。

---

## 十、业务侧可观测性

### 业界怎么做

- Langfuse / LangSmith / Phoenix 的共同形态是树形 trace（一次请求内每一步的输入输出、耗时、成本），评测挂在 trace 上；Langfuse 还支持 OTLP 导出，WeKnora 用它做文档解析的阶段追踪。
- 成本与 token 用量是 trace 的一等公民，不是事后统计。

### 本仓库现状

- `python_backend/api/routers/observability.py` 提供 runs / events / metrics / export / trends，维度是运行与事件。
- 检索侧没有指标：不知道哪条通道在起作用、语义分数分布如何、embedding 花了多少、索引有多旧、门闸澄清率多少。

### 建议方案

**指标清单与采集点**（复用现有 `execution_run_events` 表，不引入新存储）：

| 指标 | 采集点 | 口径 |
| --- | --- | --- |
| 分通道命中率 | 召回处 | 词面命中数 / 语义命中数 / 两者皆无 |
| 语义分数分布 | 召回处 | top1 与 top3 分数，用于盯阈值漂移 |
| embedding 成本 | 向量生产 + 查询 | token 数与调用次数 |
| 索引新鲜度 | 探测处 | 最新 marker 与当前时间的差 |
| 门闸澄清率 | 意图门闸 | 澄清轮次占比 |
| 证据引用率 | 答案生成后 | 答案引用的证据数除以提供的证据数 |
| 预算超限率 | 装配处 | 超限返回错误的比例 |

这些数字进 step 事件（现有 `details` 机制）与 manifest，不新造一套上报通道。

---

## 十一、跨工作区共享知识

### 业界怎么做

- 火山引擎 VikingDB 把产品分成向量库、知识库、记忆库三种形态，各自面向不同的数据组织方式，而不是所有内容塞进一张表。
- AnalyticDB-V 走的是向量湖仓路线：一份数据，多种服务，权限与分区在湖仓层统一。
- GraphRAG 用社区摘要做全局归纳，其前提是底层有可分区的实体与关系结构。

### 本仓库现状

- 本轮刻意不改共享向量库表结构，工作区级检索靠本地索引 + 文档成员关系实现。共享库那一侧只被当作「工作区用过的文档」的语义存储。

### 建议方案

**三级作用域**

| 级别 | 范围 | 落地 |
| --- | --- | --- |
| 工作区私有 | 现状 | 本地索引 + `doc:` / `file:` 前缀 |
| 组织共享 | 同组织只读 | 独立 source 前缀（如 `shared:<org>:<id>`），检索时按作用域合并候选 |
| 公共知识 | 全局 | 同上，标签为公开 |

**边界与前置**

- 共享知识必须与第四节的权限模型一起做，否则「组织共享」会退化成无差别泄露。
- 共享库与工作区私有库物理分开（不同表或不同库），避免权限过滤互相干扰。
- 共享内容进入工作区上下文时，同样走「证据 + 来源 + 层级」这套结构，模型侧不区分来源级别，权限判定在检索期完成。

---

## 十二、分期建议

**P0（下一轮可直接开工，各项都能用现有标注集验收）**

1. 融合后重排层（确定性版，不引入模型调用）。
2. 冲突与时效识别（事实结构扩展 + 确定性冲突判定）。
3. 向量生产流水线（探测/生产/发布分离 + 缓存键 + 预算）。
4. outbox 与幂等（单一事实源 + 派生物可重建）。
5. 评测门禁三层化 + 标注集版本化。

**P1（上生产前必须）**

6. 权限模型（身份、检索期过滤、装配前复核、审计）。
7. OpenViking 真实部署与抽取质量评测。
8. 前端证据卡片与空状态区分。
9. 业务指标采集。

**P2（规模化之后）**

10. 跨工作区共享知识与共享库分离。

**明确不做**：不引入 RAGAS / Langfuse 等第三方栈来替代自研判定器与埋点；不引入分词器依赖，中文分层继续靠 FTS5 trigram + bigram；不在本阶段改共享向量库表结构。

---

## 十三、验证命令

文档改动只需核对路径与命令一致性。涉及代码改动时执行仓库约定的验证命令。

    .\.venv\Scripts\python.exe -m unittest python_backend.modules.context_engineering.test_chain python_backend.modules.context_engineering.test_snapshots -v
    .\.venv\Scripts\python.exe -m unittest python_backend.modules.retrieval.test_workspace_index python_backend.modules.retrieval.test_recall_quality -v
    .\.venv\Scripts\python.exe -m compileall python_backend
    .\.venv\Scripts\python.exe skill-center/test_center.py
    .\.venv\Scripts\python.exe skill-center/test_agent_tools.py
    npm --prefix frontend run build

需要真实 embedding 服务的语义评测默认跳过，显式打开：

    $env:HOTLINE_SEMANTIC_EVAL=1
    .\.venv\Scripts\python.exe -m unittest python_backend.modules.retrieval.test_semantic_recall -v

---

## 十四、参考来源

一手（项目 README、官方文档、论文）：

- FlagEmbedding（北京智源），含 bge-reranker 系列与 bge-m3 多路召回模型：https://github.com/FlagOpen/FlagEmbedding
- WeKnora（腾讯微信 AI 团队），混合检索、父子分块、引用、跨会话长期记忆与用户确认、审计、Langfuse 追踪：https://github.com/Tencent/WeKnora
- Graphiti / Zep，时序上下文图、事实自动失效与时序历史、episodes 溯源、混合检索：https://github.com/getzep/graphiti ；论文：https://arxiv.org/abs/2501.13956
- Eino（字节 CloudWeGo）记忆边界说明（Memory / Session / Store 属业务层）：https://cloudwego.io/docs/eino
- LlamaIndex 摄取管道与 IngestionCache（节点 + 转换哈希缓存）：https://docs.llamaindex.ai/en/stable/module_guides/loading/ingestion_pipeline/
- Azure AI Search 文档级访问控制（安全过滤器、ACL/RBAC 镜像、敏感度标签）：https://learn.microsoft.com/azure/search/search-document-level-access-overview

二手（用于取数与结论方向，非权威定义）：

- RAG 评测两段式指标综述（RAGAS / ARES / RAGChecker，precision@k、recall@k、nDCG、MRR、faithfulness、citation coverage）：https://laoujin.github.io/Atlas/research/2026-06-09-session-blueprint-rag-embeddings-from-demos-in-5-minutes-to-a-production-grade-pipeline-2026/rag-evaluation
- 大规模 RAG 流水线的吞吐与新鲜度权衡、embedding 为摄取瓶颈：https://aicassindra.com/blogs/agents/sysdesign_rag_pipeline_at_scale.html
- contextual retrieval 与 late chunking 的 nDCG 对照与索引成本：https://particula.tech/blog/contextual-retrieval-vs-late-chunking
- 向量库租户隔离与元数据过滤的工程讨论：https://anjalichaursiya.com/?p=231
- Mem0 去重与更新策略的实测比较：https://blog.csdn.net/kanhaoning/article/details/165128345
- LLM 可观测平台对比（Langfuse / LangSmith / Phoenix）：https://scored.tools/blog/langsmith-vs-langfuse-vs-arize-phoenix-llm-observability

公开产品与架构资料（用于大厂做法）：

- 火山引擎 VikingDB 架构分析（存算分离、索引与存储分层、租户隔离、权限管理器）：https://www.zybuluo.com/changedi/note/2645044
- 阿里云 AnalyticDB for MySQL AI Agent MemStore 长期记忆方案（记忆分类、Memory Service 接口、内置一致性维护与遗忘）：http://www.senben.cc/?zh/analyticdb/analyticdb-for-mysql/long-term-memory-overview
- 腾讯 WeKnora 项目说明与版本演进（含记忆与检索能力）：https://baike.baidu.com/item/%E7%BB%B4%E5%A8%9C%E6%8B%89/69381232
- 字节 DeerFlow SuperAgent 架构解读（子 Agent、沙箱、记忆与技能的编排）：https://www.termdock.com/en/blog/deer-flow-bytedance-superagent
