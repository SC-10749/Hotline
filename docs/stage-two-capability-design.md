> 方案草案：文中的差距、文件行号和运行拓扑是编写时的基线，不作为当前功能清单。当前实现与 Java/Python 迁移进度见 [主 README](../README.md)。

# Hotline 第二阶段能力设计（检索、记忆与运营化）

状态：草案 v2。本文承接 [上下文工程实现与验收](./context-engineering-design.md)，针对十项尚未落地的能力，给出业界做法、本仓库实证差距与可执行方案。

调研时间：2026-11-09 首版，2026-11-10 全量复核。复核方式：开源项目与大厂官方文档检索 + 本仓库逐条代码取证。开源 star 数为检索时快照（2026-11-10）。

阅读约定：每节三段——「业界怎么做」只写可核实的机制并给出来源；「本仓库现状」给 `文件:行号`；「建议方案」给接口、状态机或阈值，能落到可执行测试的才写。

**本版相对 2026-11-09 版的四处修正**（上一版有两处表述与代码不符）：

1. OpenViking 不是「协议桩」。`python_backend/modules/memory/openviking.py` 是完整 HTTP 客户端，真实端点、投递队列、租约恢复都在；缺的是部署编排与真实数据。
2. 演示回落不是 54 处。实测 22 处：`frontend/src/HarnessApp.vue` 17 处、`frontend/src/harness.css` 5 处。
3. 评测门禁的现状不是「两个标注集」。`eval/` 已是两段式（Ragas 打分 + 提示词静态检查 + 指纹对比），缺的是 CI 与应用内发布门禁的接线。
4. 向量流水线的缺口不是「查询路径现算 embedding」——问题向量现算是必然。真正的缺口是**摄取期逐块单条调用、无队列、无成本预算、文档向量全量重建**。

---

## 一、总览

| # | 领域 | 业界成熟度 | 本仓库现状（2026-11-10 代码取证） | 优先级 |
| --- | --- | --- | --- | --- |
| 1 | 融合后重排层 | 成熟（cross-encoder 已标准化） | 只有 RRF 融合，无重排、无 MMR、无语义级去重 | P0 |
| 2 | 冲突与时效识别 | 成熟（双时态事实 + 显式作废） | 事实只增不覆盖，有时间戳与撤销代次；无有效期、无冲突判定 | P0 |
| 3 | 多用户与权限模型 | 成熟（检索期裁剪是共识） | 单用户，无 user/tenant/role；产物归属靠客户端自证请求头 | P1（上生产前必须） |
| 4 | 向量生产流水线与成本 | 成熟（摄取是独立流水线） | 摄取逐块单条 embedding 调用，无队列无预算，文档向量全量重建 | P0 |
| 5 | 多套存储的一致性与并发 | 成熟（outbox + 幂等键） | 记忆投递已是局部 outbox；跨库无事务，无补偿表与死信 | P0 |
| 6 | OpenViking 真实部署 | 有产品化参考 | 已是完整客户端 + 投递队列；缺部署编排、探活、真实抽取数据 | P1 |
| 7 | 评测门禁 | 成熟（两段式评测 + CI 门禁） | 已有两段式与静态检查；无 CI，应用内 release gate 与 eval/ 产物未连通 | P0 |
| 8 | 前端呈现 | 成熟（引用可核查是标配） | 知识库片段无出处展示，联网引用才有出处；演示回落 22 处 | P1 |
| 9 | 业务侧可观测性 | 成熟（trace + 成本 + 业务指标） | 有事件表与 metrics/trends/export；无 trace/span 层级、无金额成本、无分位延迟 | P1 |
| 10 | 跨工作区共享知识 | 成熟（分层存储 + 权限过滤） | 工作区严格隔离，向量表无 workspace 列，无共享层 | P2 |

「刻意未做」不等于「做错了」：第十项是因为共享表属于其他模块的边界；第十项与第三项一起做才有意义。

---

## 二、融合后重排层

### 业界怎么做

三段式流水线是共识：**多路召回（dense / sparse-BM25 / SPLADE）→ 融合（RRF 或相对分数融合）→ 精排（cross-encoder）→ top-N**。融合阶段用「排名」而非「分数」做无标度组合，精排阶段才引入业务语义与交叉编码。

开源侧：

- **pgvector**（23,625 star，滚动发布，无 release 标签）：不做融合引擎，只提供原料——官方直接指向 `pgvector-python/examples/hybrid_search/rrf.py` 与 `cross_encoder.py` 两个示例作为标准实现；另有「子向量索引粗召回 20 条 + 全向量距离精排取 5 条」模式。HNSW 默认值：`m=16`、`ef_construction=64`、`hnsw.ef_search=40`。
- **Qdrant**（35,479 star，v1.20.0）：`prefetch` 让一次查询先跑若干子查询，融合支持 RRF 与 DBSF，dense / SPLADE++ 稀疏向量 / payload BM25 可任意组合。
- **Weaviate**（16,944 star，v1.40.4）：单个 `alpha` 标量（1 纯向量 / 0 纯关键词）；v1.24 起默认融合由 RRF 改为 Relative Score Fusion；`explainScore` 输出每个文档对总分的贡献拆解。
- **Milvus**（46,614 star，v3.0.5）：多向量字段 + 多路 `AnnSearchRequest` 合并重排。
- **Dify**（160,699 star，1.19.0）：把「融合」放在知识库层、「重排」放在节点层——知识库设置决定初始结果池，节点设置再重排或收窄；`Top K` 与 `score_threshold` **只在开启 rerank 后生效**，关掉时这两个旋钮是死的。
- **FlagEmbedding / BGE**（12,304 star，v1.4.2）：`bge-m3` 一模型同时做 dense / sparse / multi-vector（ColBERT）；`bge-reranker-*` 是 cross-encoder 精排器。

大厂侧：

- **Azure AI Search**：语义重排**只在初始结果的 top 50 上做二次排序**；排序前用 summarization model 把每篇文档压到 ≤2000 token；单索引最多 100 个语义配置，可在不重建索引的前提下增改。
- **Amazon Bedrock Knowledge Bases**：托管知识库检索一律走混合检索（纯向量不可用）；重排由 `retrievalConfiguration.managedSearchConfiguration.rerankingModelType` 控制（`MANAGED` / `CUSTOM` / `NONE`），CUSTOM 官方示例 `numberOfRerankedResults: 5`。托管重排仅对使用托管 embedding 的知识库可用。
- **Vertex AI RAG Engine**：`RANKER_MODEL_NAME`（如 `semantic-ranker-default@latest`）与 `SIMILARITY_TOP_K` 分离配置。
- **阿里云百炼**：两段式——向量 TopK 50 + 关键词 TopK 50 → 全部进 `qwen3-rerank` → 最终召回 5 条。**重排按送入排序的切片总量计费**，不是按最终返回数计费。
- **扣子（Coze）**：最大召回数量默认 5，最小匹配度默认 0.5，可选「结果重排」。

可直接抄的默认值：

| 参数 | 取值 | 出处 |
| --- | --- | --- |
| 送入重排的候选上限 | 50 | Azure 语义重排上限 |
| 重排模型看到的单文档上限 | 2000 token | Azure |
| 最终进入上下文的片段数 | 5 | Bedrock / 百炼 / 扣子 |
| 初步召回规模 | 50 + 50 | 百炼 |
| 相似度下限 | 0.5 | Dify（仅 rerank 阶段）/ 扣子 / 百炼 |
| RRF 的 k | 60 | 现行实现已用此值，与 Azure 文档公式一致 |

坑：

- pgvector 官方明确：近似索引**先扫索引再过滤**，若过滤命中 10% 行、`ef_search=40`，平均只有 4 行能通过过滤，不开 iterative scan 会少召回。
- Azure 官方明确：重排只在 top 50 内生效，**召回层给不回的文档，后面再强也救不回来**。
- 百炼明确：挂 N 个知识库则检索 token 消耗 ×N。

### 本仓库现状

- `python_backend/modules/retrieval/fusion.py:6-23`：`fuse_evidence` 做 RRF（`1/(60+rank)`，k=60 硬编码在 `:13`）、词面命中数打破同分、归一化文本去重后截断。
- 调用点两处：`python_backend/agents.py:502-506`（文档证据 + 工作区证据合并）、`python_backend/agents.py:508-528`（hybrid 路由下语义/关键词/图谱三路融合，融合发生在 `:523`）。
- 路由共四条：`semantic` / `keyword` / `graph` / `text2sql`，外加默认 hybrid（`agents.py:514-527`）。
- **全仓无重排**：检索 `rerank|cross_encoder|bge-reranker|semantic_rank` 零命中；无 MMR、无近重复（语义级）去重，只有完全相同字符串去重。
- 分层摘要是抽取式、不调模型：`python_backend/modules/retrieval/layers.py:11-21`。

### 建议方案

分两级，默认只走第一级。

**第一级：确定性重排（无模型调用）**

对融合后的前 40 条候选打分，输出 8–12 组证据。信号全部本地可算：

| 信号 | 计算方式 | 权重方向 |
| --- | --- | --- |
| 通道一致性 | 被几个通道命中（词面 / 语义 / 父块展开） | 越高越好 |
| 精确 token 命中 | 是否命中编号、错误码这类高区分度 token | 命中则强加权 |
| 词面覆盖 | query 词项在片段中的覆盖率（复用现有 trigram/bigram 命中） | 越高越好 |
| 来源层级 | 命中标识符的片段优于泛化描述 | 越高越好 |
| 新鲜度 | source marker 的更新时间 | 越新越好（权重最小） |

`fuse_evidence` 保留为第一阶段合并，重排作为可选第二阶段；重排异常、超时或候选不足时直接退回融合结果，不阻断回答。

**第二级：模型重排（有预算）**

只在两种情况下启用：候选里出现多个通道互相冲突，或用户明确要求「精确/最新」。约束写死：单次候选上限 12 条（远低于 Azure 的 50 上限，因为本仓片段更长）、调用超时 800 ms、失败即退回第一级、每轮最多一次。

参数直接对齐成熟项目：候选池 50（Azure 上限），最终进上下文 5 条（Bedrock/百炼/扣子一致），相似度下限 0.5（Dify/扣子/百炼），单文档送入重排 ≤2000 token（Azure）。

**验收**

- 在现有两个标注集（`python_backend/modules/retrieval/test_recall_quality.py` 4 条词面、`test_semantic_recall.py` 3 条语义）上，重排后 Recall@8 不低于重排前，nDCG@8 必须提升。
- 新增「同名不同主题」干扰用例，检验重排能否把主题一致的那条排到前面。

---

## 三、冲突与时效识别

### 业界怎么做

成熟方案不再把记忆当「一串可覆盖的字符串」，而是给每条事实加**双时态**：事实何时在现实成立（`valid_at` / `invalid_at`）与系统何时记录或作废（`created_at` / `expired_at`）分开存。冲突裁决不是「谁后写谁赢」，而是**作废旧事实 + 生成新事实**，并保留历史以支持「某时刻的真相」查询。

开源侧：

- **Zep / Graphiti**（32,670 star，v0.31.2）：事实是图上的 edge，四个时间戳 `created_at` / `valid_at` / `invalid_at` / `expired_at`；冲突时**作废旧边而不是删除**。官方样例极典型：用户先说喜欢 Adidas，后来说鞋坏了并转投 Puma，系统作废「likes Adidas」这条边，新建「Adidas shoes broke」与「likes Puma」两条事实。有效时间由承载该事实的 episode 内容 + `reference_time` 推断（只有日期无时间的按 UTC 午夜处理）。
- **Mem0**（68,662 star，v2.2.1）：写入侧 **ADD-only**——`add` 只增不覆盖，更新必须显式 `update(memory_id, text)`。治理交给后台 **Dream** 的三个动作：`Synthesis`（蒸馏高阶模式记忆，付费档 opt-in）、`Supersede`（淘汰过时事实，始终开启）、`Merge`（合并重复，始终开启）。
- **LangMem**（1,754 star）：记忆先分语义 / 情景 / 程序性三类再选载体；用 collection 时系统必须处理「删除/作废或更新/整合」已有记忆。
- **Letta**（25,389 star，0.16.8）：**MemFS** 把长期记忆放进属于该 agent 的 git 仓库，每次记忆编辑都提交，天然获得版本历史、冲突解决，以及「已保存记忆 vs 未提交改动」的清晰边界。

大厂侧：

- **AgentCore Memory**：事件保留期**写入即固定**，更新只影响此后创建的事件，历史事件保留原过期时间且**过期不可恢复**；长期记录 TTL 最小 31 天，默认不过期。内置策略三步：Extraction → Consolidation（决定写新记录还是更新已有记录）→ Reflection。
- **Google grounding check**：可判定文本在参考集中的接地程度并生成支持性引用；release notes 明说该 API 还能（实验特性）生成「相互矛盾的引用」，标出哪些事实与文本冲突及冲突强度。

坑：

- Mem0 社区 issue #4896 直接质疑 v2 文档与实现不符：*ADD-only 架构未实现语义相似记忆的冲突消解*。结论是「靠 add 自动解决冲突」的预期在 v2 不成立，**冲突治理必须显式设计**。
- Zep 官方自陈：`valid_at` / `invalid_at` **不表示**源内容或派生事实为真，只表示系统推断的时间范围，不要当可信度信号。
- Mem0 的 `version="v2"` 参数在新版 SDK 已被移除且「传了会被忽略」，升级时旧代码静默降级——典型的「参数被忽略」型故障。

### 本仓库现状

- 事实与历史在 `python_backend/modules/memory/store.py`：
  - `memory_event`（`:34-41`）主键 `(conversation_id, source_id)`，字段 `created_at` + `completed`，写入即 UPSERT 覆盖（`:151-154`）——**同一事实不会多版本并存**，无 `supersedes` / `as_of` / `effective_until`。
  - 撤销代次 `memory_scope.generation`（`:27-29`）：`forget()` 自增 generation、取消未完成投递、删本地证据（`:309-334`）。这是「整体遗忘」，不是「事实级作废」。
  - 乐观并发 `revision` CAS（`:102`、`:111`），冲突抛 `MemoryConflict`（`:14-16`）。
  - 检索历史只取 `completed=1`（`:232`）。
- 任务事实状态（active/completed/cancelled）在 `python_backend/agents.py` 的任务状态抽取层，不在记忆层。
- 文档版本 `ai_document_version` 有 `UNIQUE(doc_id, version)`（`python_backend/storage.py:87-90`），但那是**产物版本**，不参与检索裁决。
- 全仓 `conflict` 只命中治理的「重复决策冲突」与记忆的 `MemoryConflict`，没有事实级冲突实现。

### 建议方案

**事实结构扩展**（保留追加语义 + 增加显式作废）

| 字段 | 含义 | 对应 |
| --- | --- | --- |
| `valid_from` | 事实开始成立的时间 | Zep `valid_at` |
| `valid_to` | 事实不再成立的时间，空 = 当前有效 | Zep `invalid_at` |
| `superseded_by` | 被哪条事实取代 | 本仓自定义 |
| `observed_at` | 系统记录时间 | Zep `created_at` |

不变式：

- 冲突时不删除旧事实，只置 `valid_to` 并指向新事实，历史完整保留。
- 召回时按 `valid_from` 倒序，同 key 只取当前有效值。
- 用户明确撤销走 `cancelled` / generation 轮换，与「被更新覆盖」区分开（两者在 UI 与审计上含义不同）。
- 长期记忆层保持追加语义（Mem0 方向），但**必须显式接治理动作**，否则噪声自我稀释（Mem0 issue #4896）。本仓已有 generation 轮换，可作为 Supersede 的粗粒度版本，但缺事实级粒度。

**判定分级**

| 情形 | 判定方式 | 处理 |
| --- | --- | --- |
| 同 key、同 scope、不同值，且值是标识符/数字/枚举 | 确定性判定 | 自动失效旧值，写新值 |
| 同 key、同 scope、语义相近但不同表述 | 模型判定 | 低置信度时两条并存，靠时间戳排序，模型看到时间戳自行取舍 |
| 值需要归一化（大小写、空白、别名、单位） | 归一化表 + 规则 | 归一后相同则不算冲突 |
| 跨作用域（不同 workspace 或不同任务） | 不判定 | 作用域不同即不是冲突 |

**边界**：冲突判定只在任务状态层做。长期记忆层不在写入时互相覆盖。

**人工确认**：沿用「自动抽取 + 用户确认」模式——检测到高价值冲突时，在门闸澄清里带出「检测到与之前说法不一致，以最新为准吗」，用户确认后写入并把旧事实失效。

**验收**

- 改口用例：第 10 轮修改一条约束，第 30 轮不复活旧值（现有 `test_chain.py` 已有前半段，需要补后半段断言）。
- 显式撤销与被覆盖两种路径分别可查。
- 跨会话（不同 conversation、同一 workspace）仍能取到当前有效值。

---

## 四、多用户与权限模型

### 业界怎么做

主流是「**检索期裁剪 + 存储期分片**」双层：数据物理上按租户分区（collection / 表分区），查询时再叠加权限谓词（payload filter / metadata filter / policy engine）。成熟项目都不会把「先全量召回再让 LLM 自己判断能不能说」当作权限方案。

开源侧：

- **Mem0**：四类作用域 ID —— `user_id`（个人）、`agent_id`（智能体）、`app_id`（应用面）、`run_id`（单次运行）。`app_id` 与 `run_id` 会写进该次调用产生的**每一条**记忆。
- **Weaviate**：多租户是 **collection 级**能力，默认关闭，需在 collection 定义里设 `multiTenancyConfig`；默认向不存在的 tenant 写入会报错，可开 `autoTenantCreation`；v1.26 起租户状态由 `HOT/COLD` 改名 `ACTIVE/INACTIVE`。
- **pgvector**：没有原生多租户，官方给「按 `customer_id` 做 LIST 分区」或「每租户独立表」两条路。
- **Dify**：workspace 是组织单元，所有资源归属单一 workspace 且相互隔离，成员按 role 决定可见范围；跨工作区共享必须显式走「外部知识库 API」这条带契约的通道，不能直连。
- **Casbin**（20,489 star，v3.11.0）：授权抽成独立决策层，PERM 元模型写在 CONF 里，换授权机制只改配置，典型 matcher `m = r.sub == p.sub && r.obj == p.obj && r.act == p.act`。**OPA**（12,452 star，v1.22.2）用 Rego 做全栈策略执行。
- **Letta**：权限是**工具调用审批模式**而非数据级过滤，四档 `unrestricted` / `standard` / `acceptEdits` / `strict`，CLI 默认落在 `unrestricted`。

大厂侧：

- **Azure AI Search** 文档级访问控制四条路径：安全过滤器（应用把用户/组标识拼进 filter）、POSIX 式 ACL/RBAC scope、内置身份访问、应用侧自行 trim。查询时服务端读请求头 `x-ms-query-source-authorization` 的身份，**内部自动构造安全过滤器**并与用户 filter 合并——应用不需要自己写 filter。ACL 元数据字段 `userIds` / `groupIds`（存 Entra GUID，需 filterable），SharePoint 站点组用 `spg:` 前缀。
- **MCP 授权**（规范 2025-11-25）：server 作为 OAuth 2.1 resource server，MUST 实现 RFC 9728 Protected Resource Metadata，401 时通过 `WWW-Authenticate: resource_metadata="…"` 提示，scope 在 challenge 中声明以贯彻最小权限。
- **AgentCore Memory**：隔离靠 `actorId / sessionId / namespace` 三元组；namespace 必须是**首尾带斜杠的层级路径**（`/actors/alice/` 而非 `/actors/alice`）以避免多租户前缀碰撞；粒度四档 session / actor / strategy / 全局。
- **A2A**：`TASK_STATE_AUTH_REQUIRED` 是中断态，客户端补凭据后带同一 `taskId` + `contextId` 继续。

坑：

- Qdrant payload 索引即使 `wait:true` 建完、返回 HTTP 200，过滤查询仍可能严重漏结果（issue #9373：25 条只回 2 条）。在多租户过滤场景下会被放大为「某租户看不到数据」，且与权限配置错误极难区分。
- Azure 官方承认 ACL 变更生效有延迟窗口：索引器 ACL 变更后需带 `options: ["permissions"]` 显式 resync 回填历史条目。
- Letta CLI 默认 `unrestricted`——默认即放行，企业部署必须显式改档。

### 本仓库现状

- **全仓所有 `CREATE TABLE` 里没有任何 user / tenant / role / ACL 表**（检索 `tenant` / `role` / `permission` 只命中消息角色与工具白名单）。
- 唯一的归属概念是产物：`run_artifact.owner`（`python_backend/modules/artifacts/store.py:38-56`），下载与预览按请求头校验，头名默认 `X-Harness-Owner`（`python_backend/api/routers/artifacts.py:19`、`:44-72`），头名可配（`python_backend/infrastructure/settings_store.py:22`）。
- **该请求头是客户端自证，可伪造**；历史行 `owner=''` 直接放行（`artifacts.py:65-67`）。
- **无鉴权中间件**：`python_backend/fastapi_app.py:129-130` 只挂 CORS；全仓无鉴权类 `Depends(` 依赖。
- 检索隔离只到 `workspace_id` 一层：索引主键 `(workspace_id, source_id)`（`python_backend/modules/retrieval/workspace_index.py:135-148`），FTS 查询 `WHERE workspace_id = ?`（`:428`、`:443`）。
- 记忆作用域按 workspace 派生：`scope_id = sha256('workspace:' + workspace_id)`（`memory/store.py:75-86`）。
- 模型凭证明文落本机 `data/harness-credentials.db`（见 `docs/harness-implementation-plan.md` 的「仍然存在的限制」）。

### 建议方案

**身份与作用域**

`identity = (user_id, workspace_id, role)`，`scope_id` 升级为对 user 与 workspace 共同派生。绑定时仍按「同一会话不可切换工作区」的既有约束。

**检索期过滤**

每个来源带 `access_tags`（用户 / 组 / 角色 / 公开），检索条件里带上调用者的 tags，过滤在检索期完成。两道防线：

1. **检索过滤**：向量库 metadata + 本地索引 `workspace_id` / tags 条件；
2. **装配前复核**：上下文装配前再校验一次证据的 tags，防的是「召回对了但装配错了」。

第 2 道不能省：过滤一旦只做在检索层，任何绕过检索直读原文的路径（`read_source`、原文分页工具）都会成为越权口子。

**授权层选型**：不引入 Casbin/OPA 这类新依赖起步（本仓 388 个后端用例、15 个 Python 依赖，都还没有策略引擎）。先用「主体 + 资源 + 动作」的最小三元组在应用层实现，等出现第二个以上消费方再抽成 Casbin 模型——这条与 Casbin 自己的思路一致：策略从 CONF 走、不散进业务代码。

**落地顺序**

先在本地索引层做（`workspace_id` + tags 条件），不动共享向量库表结构；共享库那侧用 metadata 过滤，需要加字段时走向量库自己的迁移。

**审计**：命中与拒绝都写事件，复用现有 `execution_event` 表即可。

**验收**：越权召回 0 次（这条设计文档已有）；补跨工作区、跨用户两组用例。

---

## 五、向量生产流水线与成本

### 业界怎么做

摄取是**独立于查询路径的服务**，有明确的阶段契约：解析 → 切块 → 富化 → 索引 → 异步增量同步。任务系统按 at-least-once 语义设计，任务函数必须幂等。成本控制点主要在两处：解析/OCR 的算力与 embedding 的 token/调用数。

开源侧：

- **RAGFlow**（93,799 star）：进程级拆分——镜像入口先跑数据库迁移，再启动 **Admin / Syncer / Ingestor / API** 等服务，`./bin/ragflow_server --ingestor` 单独起摄取服务。Agent 侧把摄取做成可编排画布：**Parser → Chunker → {Transformer | Compiler} → Indexer**；官方注明**一块画布只支持一个 chunking 组件**；「视觉增强（生成图片描述）」与「OCR（识别文字）」是**两个独立开关**，要求至少开一个。
- **Dify**：把「索引方式」显式产品化为二选一——High Quality（向量 + 全文 + 混合）与 Economical（每块约 **10 个关键词**建倒排，**不消耗 embedding token**）。官方明确**索引方式不可逆**，High Quality 建完不能改 Economical。
- **Unstructured**（15,701 star）：`partition_pdf` / `partition_text` 统一入口，OCR 后端按需安装。
- **Docling**（70,315 star，v2.149.0）：统一 **DoclingDocument** 表示层，覆盖版面/阅读顺序/表格结构/代码/公式/图片分类。
- **Celery**（29,145 star）的幂等契约：任务应尽量幂等；`acks_late` 只在任务幂等时开启，否则用 `task_reject_on_worker_lost`；worker 崩溃时消息会被**重新投递给另一个 worker**。
- **Prefect**（24,138 star）/ **Airflow**（47,421 star）/ **Temporal**（24,284 star）分别是任务编排、静态工作流、durable execution 三档。

大厂侧：

- **Bedrock KB 切片策略**（可直接当接口形状抄）：默认切片 ≈**300 token** 且遵循句子边界；固定大小 = `maxTokens` + 重叠**百分比**；分层切片 = 父块/子块/重叠 token 数（两级，命中子块、返回父块）；语义切片 = `maxTokens` + `bufferSize` + `breakpointPercentileThreshold`。
- **百炼三段式成本模型**：规格费（运行时长/RCU）+ **检索阶段**模型费（向量化 + 排序 + 路由）+ **问答阶段**模型费（生成 + 预文件解析），每段独立计价；优化手段按收益排序是「关闭排序 → 调小初步召回 TopK → 其他」。
- **缓存计费**：Anthropic 5 分钟 cache write 1.25×、1 小时 2×、命中 0.1×；OpenAI cached input 0.1×；Gemini 隐式缓存在 2.5 及以后模型上折扣 90%。

坑：

- Celery 官方 FAQ：worker 无法检测你的任务是否幂等，`acks_late` 配错会导致任务被执行多次。
- Dify 索引方式不可逆，意味着「先上便宜索引后补向量」不可行，切换需重建知识库。
- 语义切片会**额外调用基础模型**，费用与数据量相关。
- Airflow 官方自述其设计前提是「工作流结构基本静态」，把 Agent 的动态编排硬塞进 DAG 会很别扭——本仓的动态编排不要往这个形状上靠。

### 本仓库现状

- 文档摄取有状态机：PENDING → CONVERTED → VECTORIZING → VECTORIZED（`python_backend/documents.py:651-708`）；失败回退 CONVERTED 并写 `errorMsg`（`:693-696`）；有进程内 sweeper（`:597-614`）与外部补偿入口（`:767-773`）。
- **摄取不批量**：`index_document` 逐块调 `_embed`，每块一次 HTTP 请求（`python_backend/vector_store.py:159-178`）。批量接口 `embed_batch` 存在（`:101`）但只用于工作区文件级语义召回（`python_backend/workers/execution_worker.py:357`）。
- **文档向量全量重建**：先 `delete_document` 再整体写入（`documents.py:685-686`），无增量差分。
- 工作区侧有增量：以 `mtime_ns:size` 作 marker 跳过未变文件（`python_backend/modules/retrieval/workspace_index.py:290-292`、`:318-320`），每次最多处理 40 个变更文件（`_DEFAULT_EMBED_BUDGET`，常量 `:48`，入口 `:303`），语义分数下限 0.35（`_MIN_VECTOR_SCORE`，`:49`）。
- **无摄取队列**：`vectorize()` 由 API 同步调用 + 定时 sweeper 兜底，没有任务表与消费端。
- **无成本口径**：全仓无 token 成本或金额统计；`modules/context_engineering/budget.py` 只管模型输入的 UTF-8 字节上界估算（`:15-18`）。
- 查询期的问题向量现算是必然（`vector_store.py:147`、`:191`），不算缺口。

### 建议方案

**三段式：探测 → 生产 → 发布**

| 段 | 触发 | 动作 |
| --- | --- | --- |
| 探测 | 查询路径（只读 stat） | 发现变更文件，登记待生产任务 |
| 生产 | 后台队列 | 批量调用 embedding（一次多输入） |
| 发布 | 生产完成 | 写入向量表并更新 marker |

查询路径只做探测，绝不等待 embedding。

**批量优先**：现有 `embed_batch` 直接复用，摄取侧从「每块一次 HTTP」改成「每批 10–32 块一次」。这条是本节投入产出比最高的一项——不改架构，只改调用方式。

**缓存键**

`sha256(模型名 + 维度 + 规范化文本)`。同一份文件内容在多个工作区只算一次，缓存放本地（与索引同库或单独一张表），键变化即失效——换 embedding 模型天然触发重算，不需要额外版本协议。

**预算**

每工作区每日 embedding token 上限；超预算时只生产「本轮查询命中的候选文件」，其余排队；积压超阈值时降级为纯词面通道并在 manifest 里标注。成本三段式归因（向量 / 排序 / 生成）先各记 token 数，不急着换算金额——单价表会变，token 数不会。

**版本与重建**

source marker 里带 embedding 模型名与维度。模型换了，marker 不匹配即自动重算，旧向量按 marker 分区保留，可灰度切换。

**验收**

- 同一份文档重复摄取，embedding 调用次数不增加（缓存命中）。
- 换 embedding 模型后 marker 不匹配触发重算，且旧向量分区可回滚。
- 超预算时 manifest 标注降级状态，答案仍能产出。

---

## 六、多套存储的一致性与并发

### 业界怎么做

通用做法没有免费的跨库一致性：选**一个 source of truth**，其余为**可重建的派生视图**；写入路径用幂等键 + 可重放语义（at-least-once 队列 + 幂等任务）；版本切换用「双写 + 别名切换」，旧索引保留可回滚窗口；可见性靠「索引代数 + 指针」而不是分布式事务。

开源侧：

- **pgvector**：一致性直接继承 PostgreSQL 的 MVCC，代价是近似索引与过滤的交互问题。
- **Qdrant**：快照即一致性手段——collection 级快照是 tar 归档，`create_snapshot` 是同步操作。
- **RAGFlow**：把「同步」与「摄取」拆成独立服务（**Syncer** 与 **Ingestor** 分家），派生视图刷新与解析入库互不阻塞。
- **Celery / Temporal / Prefect**：at-least-once + 幂等 + 持久化的三档组合。

大厂侧：

- **Azure AI Search** 向量索引参数（官方示例值，可直接抄成配置模板）：`hnswParameters {m: 4, efConstruction: 400, efSearch: 500, metric: "cosine"}`；另有 int8 的 `scalar-quantization` 与 `binary-quantization` 压缩 profile。
- **Azure 限流**：索引读 50 queries/sec（每索引聚合），索引写 5 requests/sec per index；语义重排用**队列**管理并发请求，队列满则拒绝并要求重试。
- **Memorystore for Valkey** 向量参数：`EF_RUNTIME` 默认 10（上限 4096）、`M` 默认 16、`EF_CONSTRUCTION` 默认 200。
- **LangGraph** durable execution：checkpointer（线程内状态快照）与 store（跨线程应用数据）分离；`thread_id` 在 PostgresSaver 里必须 <255 字符；**checkpoint 会无限增长**，要定期 prune，否则直接推高延迟与存储成本。
- **语义缓存的工程结论**（Redis 官方）：阈值太松会答错、太紧命中率崩；有效做法是**软相似度 + 硬元数据边界（tenant、locale、模型版本、安全标记）并存**；模型厂商的 prompt caching 只省前缀，**仍然完整跑一遍模型**，既不解决延迟也不跨用户复用整段响应。

坑：

- 多存储最终一致在实践中失败的方式是**用户先看到新答案、后看到旧证据**（引用与文档版本错配）——RAGFlow 为此专门做了「只返回被引用文档」的修复。
- **检索入口必须校验知识库归属**：Dify 的相关 PR 标题就是 `fix(api): check kb ownership in /dify/retrieval`。
- pgvector 加近似索引后**查询结果本身会变**，做「索引前后对比」或灰度时会得出错误结论。

### 本仓库现状

各存储落点：

| 存储 | 内容 | 位置 |
| --- | --- | --- |
| SQLite（业务） | `ai_file_info` / `ai_session` / `ai_document` / `ai_document_version` | `python_backend/storage.py:54-120` |
| SQLite（执行/事件） | `execution_run` / `execution_event` / `execution_worker` | `python_backend/modules/execution/store.py:70-104` |
| SQLite（产物） | `run_artifact` | `python_backend/modules/artifacts/store.py:38-49` |
| SQLite（记忆/投递） | `memory_scope` / `memory_event` / `memory_delivery` / `memory_checkpoint` | `python_backend/modules/memory/store.py:27-63` |
| SQLite（治理/发布） | `harness_approval` / `release_gate` / `release_record` | `python_backend/infrastructure/governance_store.py:55-106` |
| SQLite（评测） | `evaluation_dataset` / `evaluation_run` / `evaluation_result` | `python_backend/infrastructure/evaluation_store.py:40-86` |
| MySQL（可选后端） | 与 SQLite 同 schema | `python_backend/storage.py:22-36` |
| Postgres + pgvector | 向量表 / 父块表 / `dodo_knowledge_relation` | `python_backend/vector_store.py:62-77` |
| 对象存储 | MinIO 或本地目录 | `python_backend/object_store.py:11-34` |

已有机制：

- **幂等键**：记忆投递 `job_id = 'mem-' + sha256(scope:generation:conversation:source)`（`memory/store.py:137-180`）；产物 `UNIQUE(run_id, storage_backend, storage_key)` + `ON CONFLICT DO NOTHING` + 冲突后字段比对拒绝覆盖（`artifacts/store.py:49`、`:82-90`）。
- **唯一的 outbox**：完成事件与投递任务在**同一事务**提交（`memory/store.py:139` 的注释与 `:160-180`）。
- **事务边界**：执行队列与记忆库用 `BEGIN IMMEDIATE`；向量库 `autocommit=True`，**无跨库事务**（`vector_store.py:45`）。
- **租约并发控制**：执行侧 `lease_until` + `worker_id` + `claim_next` + 租约过期置 failed + 心跳；记忆投递侧 `lease_until` / `lease_token` + `claim()` + `delivery_update()` 校验租约。
- **写入顺序有代码可查**：PPT 产物 = 生成文件 → 上传对象存储 → 登记 SQLite → 删本地（`python_backend/workers/execution_worker.py:167-180`）；文档 = 转 Markdown → 对象存储 → 记录与版本 → 向量（`documents.py:631-647`、`:686`）。

缺口：

- 无跨存储事务；**向量写入与文档状态更新非原子**，失败即回退 CONVERTED，靠 sweeper 重试。
- 除记忆投递外**无 outbox 模式**；无补偿表、无死信。
- 幂等键无全局规范（记忆用 sha256 串、产物用三列唯一约束、执行用唯一索引）。
- 向量表按 `file_id` 过滤，**连 `workspace_id` 列都没有**（`vector_store.py:63-77`），跨工作区隔离靠「谁来查谁负责」，不是靠表结构。

### 建议方案

**单一事实源**

本地 SQLite 索引是事实源；pgvector 与 OpenViking 都是**可重建的派生物**。派生物写失败只标记为待重建，不影响事实源，也不回滚已写入的事实。这条不变式比「三写事务」简单得多，也更容易验证。

**outbox**

本地事务内同时写事实与一条待投递记录（表 `index_outbox`：id、scope、source_id、marker、目标存储、状态、重试次数、最后错误）。后台按目标逐个投递，投递成功标 done，失败按退避重试（退避公式沿用记忆投递现有的 `min(300, 2 ** min(attempts+1, 8))`），永久失败留在表里可查可人工重放。

**幂等键**

`(scope_id, source_id, marker)`。同一键重复投递不产生重复行，也不产生重复记忆事件。

**并发**

每工作区一个写入租约（租约表 + 过期时间），同一工作区的写入串行，不同工作区并行。查询不占租约——查询只读 SQLite，WAL 下支持多读单写。

**对账**

定时任务比对本地 marker 与派生物实际状态，列出漂移（本地有、向量库没有；向量库有、本地已删），生成修复任务。这一条直接对应 Azure 的「ACL 变更需 resync」教训：漂移必须能被发现，而不是等用户发现引用对不上。

---

## 七、OpenViking 真实部署

### 业界怎么做

开源侧：

- **Mem0**（68,662 star）：流水线是「抽取事实 → 去重 → 嵌入 → 实体链接 → 写入 SQL + 向量库」。
- **Letta**（25,389 star）：把 Agent 变成**持久身份**——stateful agent 拥有自己的记忆、模型配置、工具与消息历史；「要独立身份与记忆用不同 agent，要并行线程共享身份与记忆用不同 conversation」。**MemFS** 把长期记忆放进属于该 agent 的 git 仓库，每次编辑都提交，因此天然获得版本历史与冲突解决。
- **Zep / Graphiti**：以「上下文图」为核心，事实 = 带时间戳的边，检索时把 Context Block（含每个事实的有效期区间）整段喂给模型。
- **Cognee**（33,155 star，v1.6.7）：定位「把文档、代码、应用数据变成持久 AI 记忆」，自托管为主。

大厂侧：

- **AgentCore Memory** 的接口形状最完整可抄：Memory（容器）→ MemoryStrategy（策略）→ Namespace（层级路径）→ MemoryRecord（唯一 ID + 所属 namespace）→ Session（`sessionId`）→ Actor（`actorId`）→ Event（短期记忆基本单元）。`RetrieveMemoryRecords` 支持 `namespace`（精确）与 `namespacePath`（前缀），`searchCriteria` 含 `searchQuery`（≤10000 字符）与 `topK`（**默认 10，最大 100**）；返回的 relevance score 是 embedding 余弦相似度，**官方明说「不代表百分比匹配」**；分页每页最多 100 条，用 `nextToken` 翻页。
- 策略三档：built-in（全自动，存储成本最高）、built-in overrides（改 prompt，成本较低）、self-managed（完全自控，成本最低但要自建设施）；同一 memory 可混用。内置四种：semantic / user preference / summary / episodic。
- **阿里云百炼**：长期记忆与记忆库并行，记忆库自动从对话与可复用轨迹抽取事实记忆、用户画像、技能记忆；**记忆体数据存储不收费**，但内容会并入 Prompt，占用 Token 增加。
- **OpenViking（厂商自述）**：把记忆/资源/技能统一成 `viking://` 文件系统，三种 scope —— `resources`（公共知识）、`user`（私有）、`agent`（跨 agent 共享）；三层加载 L0 摘要 / L1 概览 / L2 原文，检索**递归下钻**。

坑：

- 托管记忆服务把**记忆投毒**责任推给应用方——官方明确 memory poisoning / prompt injection 属客户责任，建议在写入前用 guardrails 做输入清洗。本仓已有 `sanitize_text` 出站脱敏（`python_backend/modules/context_engineering/privacy.py`），但入库前的语义投毒防护仍是空白。
- 写入即固定的 TTL 语义会让「事后延长保留期」变成不可行操作——策略变更必须提前设计。
- Mem0 ADD-only 意味着长期运行会积累噪声，必须显式接 Dream/Merge/Expire，否则召回精度被自我稀释。

### 本仓库现状

**已经是完整 HTTP 客户端，不是协议桩**：

- 真实端点：`/api/v1/sessions`、`/messages/batch`、`/commit`、`/api/v1/tasks`、`/api/v1/search/search`、`/api/v1/content/{abstract|overview|read}`、`/api/v1/fs`（`python_backend/modules/memory/openviking.py:46`（client）、`:58`（request）、`:85`（upload）、`:104`（commit）、`:111`（task）、`:117`（find_commit_task）、`:126`（search）、`:148`（read_level）、`:160`（recall）、`:183`（delete_memory）、`:189`（read）、`:198`（delete_session））。
- 凭据与命名空间留在服务端：`X-OpenViking-Actor-Peer` 头 + `X-API-Key`（`:62-64`）；`peer_id` 格式强校验 `hotline-<sha256[:32]>-<gen>`；URI 归属校验 `memory_uri_belongs`（`:19-30`）。
- **投递队列**：`memory_delivery` 表带 `stage` / `attempts` / `available_at` / `lease_until` / `lease_token` / `task_id` / `error_code`（`python_backend/modules/memory/store.py:43-52`）；`claim()`（`:244`）、`delivery_update()`（`:260`）。
- **重试与退避**：`min(300, 2 ** min(attempts+1, 8))`，`extraction_failed` 单独延迟 3600s（`python_backend/modules/context_engineering/service.py:103-105`）。
- **提交响应丢失处理**：用 `find_commit_task` 按 Session ID 找回已有抽取任务（`service.py:86` 配合 `openviking.py:117`）。
- **租约恢复**：`claim` 条件 `lease_until <= now` 自然过期（`memory/store.py:244-250`）+ 进程内 dispatch 线程（`service.py:32-50`）。
- 集成测试用**回环 HTTP 服务**按官方信封实现（`python_backend/modules/context_engineering/test_chain.py:44-75`）。

缺口：

- **仓库内无部署编排**：全仓无 docker-compose / Dockerfile，OpenViking 服务由外部部署。
- **无健康检查 / 探活 / 熔断**：`OpenVikingClient` 没有 ping 方法，连接失败只能在真实请求时才暴露。
- **无真实环境的抽取质量数据**：事实准确率、同义去重率、误抽取率、事实到来源消息的可追溯率都没有实测记录。

### 建议方案

**部署形态**：独立服务 + 现有客户端不变。需要补的是部署、配置、就绪检查与运维手册，而不是改客户端。

**对账与降级**：派生态语义沿用第六节（outbox + 对账）。OpenViking 侧额外需要：

- 后端状态显式暴露：抽取延迟 P95、队列积压、失败码分布；不可用时在模型输入里给出实际状态（现有实现已有此路径）。
- 抽取质量验收口径：事实抽取准确率、同义去重率、误抽取率、事实到来源消息的可追溯率。
- 加一个 `GET /health/openviking` 探活端点，供 `/health/ready` 汇总（当前只汇总执行 Worker）。

**代次与 Peer**：现有 generation 轮换保留（撤销即换代，不物理删除），加「当前代次的抽取水位」指标，回答「记忆落后了多少」。

**验收**：先在目标环境跑一份 50 条真实问答的抽取评测，再决定是否把抽取质量作为门禁。

---

## 八、评测门禁

### 业界怎么做

两段式评测是共识：**离线**（固定数据集 + 指标 + 阈值，作为 CI 门禁）与**在线**（生产 trace 上跑 evaluator / LLM-as-a-judge，抽样回归）。门禁形态是「跑评测脚本 → 超阈值抛错 → CI 失败」，而不是人工看报告。

开源侧：

- **Ragas**（16,261 star，v0.4.3）：指标可组合。`Faithfulness = (回答中被检索上下文支撑的断言数) / (回答中的断言总数)`；`Context Precision@K = Σ_k (Precision@k × v_k) / K`，其中 `Precision@k` = 排名 k 处相关块数 / 该位总块数，`v_k ∈ {0,1}`。
- **DeepEval**（19,375 star）：定位「LLM 应用的 pytest」，指标带可读解释，已覆盖 agent trajectory 的逐步决策评估。
- **promptfoo**（26,975 star，0.125.1）：CLI / 库 / GitHub Action 三形态，断言类型丰富。
- **Langfuse**（37,175 star，v4.77.0）：把「实验」做成 CI 门禁产品功能——跑数据集实验、加 evaluator、**分数越阈值即抛 `RegressionError`**、用 `langfuse/experiment-action` 写 workflow；另有基线对比与 judge 人工一致性校准。
- **Phoenix**（12,208 star）：确定性 evaluator（精确匹配 / 正则 / 自定义）与 LLM-as-a-judge 两类，可直接对生产 trace、实验、数据集跑评测。
- **Opik**（23,277 star，2.2.143）：数据集 + 实验 + 生产监控 + Diagnostics 自动扫描 trace 找复现问题。

大厂侧：

- **Microsoft 365 Copilot Agent Evaluations CLI** 给出了可直接抄的默认阈值表：LLM 指标 1–5 量表、**默认阈值 3**（Relevance / Coherence 默认启用；Groundedness / Similarity 默认关闭）；`RetrievalResult` 比例 **1.0**；`PartialMatch` **0.5**；`Citations` **≥1 但默认不启用**。
- **AgentCore Evaluations**：把 LangGraph / Strands 的 trace 统一后打分，内置 13 个评估器；**每账号每区域默认最多 1000 个 evaluation configuration**；**每账号每分钟最多 100 万输入 + 100 万输出 token**；online evaluation 结果自动落 CloudWatch 专用 log group。
- **Bedrock Evals**：模型评估 + 人工评估（5 点 Likert、成对选择、排序、Thumb up/down，JSON 结构化落 S3）+ RAG 评估；官方 hands-on 特别提到「**引用了段落却没真正使用**」这类指标。

坑：

- LLM-as-a-judge 若不与人工标注做一致性校准，阈值门禁只是在固化偏差。
- **有评测分数 ≠ 可当门禁**：Opik 的 Diagnostics 是「事后扫描」，而门禁必须前置。
- promptfoo 文档提示：provider 侧返回的 chat 数组若无可用 user message 会回退到原始 prompt 兜底——这是「评测输入与线上输入不一致」的隐蔽来源。
- AWS 官方博客的一句可作结论：**五次发布连着来、中间没有观察窗口，等于五次无控变更**——门禁的意义在于给每次发布一个观察窗口，而不是加更多指标。

### 本仓库现状

- **阶段 1 采集**：`eval/collect.py` 跑真实 RAG，组装与线上同一套对象、复用主链路的路由与分路召回（`:63-84`，其中召回复用见 `:73-77`），`--mock` 可干跑（`:148` 的参数与 `:122-135` 的 `mock_case`），产出 `samples.jsonl` + `meta.json`。
- **阶段 2 打分**：`eval/score.py` 跑 Ragas，指标 `faithfulness` / `context_precision` / `answer_relevancy`（`:67-88`），按提示词变体分组统计（`:134-142`）、基线对比（`:166`、`:229-233`），产出 `report.md` + `scores.json`。
- **提示词变体与指纹**：`eval/prompts.py` 变体表 + 契约声明 + `sha256[:12]` 指纹，用于区分「提示词变了」与「模型/检索变了」（`:5-8`、指纹 `:26-28`、变体入口 `:53-58`）。
- **静态检查**：`eval/prompt_checks.py` 检查引用标记、拒答话术、系统提示泄露、占位符泄露、长度上限（`:44-110`），`--min-pass` 默认 0.8，失败退出码 1（`:149`、`:181`）。**这一步完全本地、零成本**。
- 评测依赖隔离在 `eval/.venv`：`ragas==0.4.3`、`langchain-community==0.3.31`（`eval/requirements-eval.txt`）。
- **应用内门禁**已存在：`gate_result()` 校验 `e2ePassRate` / `ragFaithfulness` / `highRiskErrors`，阈值来自 `release_config`（`python_backend/api/routers/release.py:159`、`:169-184`），发布动作前阻断（`:350-354`），门槛落 `release_gate` 表。

缺口：

- **无 CI**：`.github` 目录不存在，仓库没有任何流水线配置；评测目前是手工命令。
- **两套评测数据未连通**：`eval/` 产出 `scores.json` / `report.md`，应用内 `release_gate` 用的是另一套 `evaluation_run` 数据（`python_backend/infrastructure/evaluation_store.py:65`）。**评测分数进不了发布门禁**，这是本节最该先补的一处。
- 依赖真实外部服务的指标：`faithfulness` / `context_precision` 需要判分模型 + API Key，缺配置直接退出码 2；`answer_relevancy` 额外需要 `EVAL_EMBEDDING_MODEL`。
- **前端没有测试入口**：`frontend/package.json` 只有 dev / dev:hot / build / preview，没有 test 脚本，也没有 vitest/jest 依赖；仓库里那两个 `node:test` 用例（`frontend/src/modules/execution/progress.test.js`、`frontend/src/modules/workspaces/paths.test.js`）当前无法通过 npm 脚本运行。根 `package.json` 的 `test` 脚本只跑 `skill-center/test_center.py`，不跑后端 388 个用例。

### 建议方案

**三层门禁**

| 层 | 依赖 | 内容 | 何时跑 |
| --- | --- | --- | --- |
| L0 离线 | 无网络、无真实服务 | 标注集、回归用例、越权用例、预算不变量、提示词静态检查 | 每次提交，必过 |
| L1 真实服务 | embedding + 模型 | 语义召回集、抽取质量、端到端答案质量 | 夜间或发版前 |
| L2 线上抽样 | 真实会话 | 失败样本采集与人工标注 | 持续 |

**把评测接进发布门禁**（本节 P0 的核心动作）：让 `POST /release/gate` 直接读最近一次 `eval/runs/<ts>/scores.json`，而不是另建一套数据。门禁判定沿用 Microsoft 的默认阈值口径：LLM 指标 1–5、阈值 3，检索类指标比例 1.0，部分匹配 0.5，引用数 ≥1 但默认不启用（避免一上线就因 Groundedness 抖动阻塞）。

**指标口径**（每条都要求带来源与版本）：

- 检索：Recall@8、nDCG@8、MRR、分通道命中率（词面 / 语义）、越权召回次数（必须 0）。
- 生成：faithfulness、引用覆盖率、答案是否被原文支持。
- 系统：输入预算超限率、门闸澄清率、端到端时延 P95、每轮 embedding token 成本。

**数据集版本化**：标注集落 `python_backend/modules/retrieval/fixtures/`（JSON + 版本号 + 变更说明）。改动标注集必须 bump 版本，历史结果按版本可比。

**失败回流**：L2 采到的低分样本进人工队列，标注后进 L0 集，成为常驻回归。

**前端测试入口**：补一个 `"test": "node --test src/modules/**/*.test.js"` 脚本即可（Node 内置 test runner，无新依赖），把已有的两个用例纳入提交前检查。

**参考实现**：RAGAS / Langfuse 的两段式口径与门禁骨架可以直接借鉴，但**不在本仓库引入这些依赖**——自研判定器 + 标注集足够，避免为一个指标体系引入一整套第三方栈。eval 目录已经在用 Ragas，那是隔离环境里的选型，不进主环境。

---

## 九、前端呈现

### 业界怎么做

引用必须是**可回跳的、机器可校验的标识**，而不是模型自由生成的文本。可核查链路通常有三环：① 答案里的引用标记指向具体 chunk/文档；② 标记是规范化 token；③ 引用有来源集合白名单（模型提到的、但未在上下文中出现的文档必须被剔除）。

开源侧：

- **RAGFlow**（93,799 star）实现最完整、也最值得抄：定义规范化引用标记 `[ID:<chunk id>]`，`citationMarkerMaxLength = 128`；引用来源注入「流式后置 prompt」时用 `citationGroundingSourceTokenBudget = 30000` 截断——源码注释写明理由：多轮检索的 Agent 运行会累积几十个块，不封顶则第二次 LLM 调用会溢出上下文窗口。函数族：`ExtractCitedChunkIDs`、`InsertCitationMarkers`、`ExpandCommaCitations`、`CitedIDsFromMarkers`、`ResolveCitations(answer, registry, publishable)`。
- **Dify**：引用靠「知识库/节点两层检索设置 + 文档元数据」提供可回跳信息；外部知识源场景下引用条目带 `score`。
- **Weaviate**：`explainScore` 把每个文档对总分的贡献拆开，是「分数可解释」的现成范式。

大厂侧：

- **Bedrock KB**：引用给原始块文本 + 源文件链接 + 关联元数据；控制台可展开来源块原文。
- **Foundry IQ**：查询时执行 agentic retrieval（规划查询、选择数据源、并行检索、聚合），返回**带引用且强制执行用户权限**的回答。
- **AG-UI**：事件分类与属性模型明确；`metadata` 是开放键值对象，各事件合并进消息时按键覆盖、后者胜出——因此可以在**最后一个事件上一次性附带 token 用量、trace id、finish reason**；生命周期必须以 `RunStarted` 开始、以 `RunFinished` / `RunError` 结束。

坑：

- **引用「看起来对但指向错 chunk」是高频缺陷**：RAGFlow 专门修过「按 marker key 解析引用 chunk」（PR #21012）与「只返回被引用文档」（PR #19899）。必须按 marker 解析，不能按显示顺序。
- Bedrock 明写 **Guardrails 只作用于输入与 LLM 生成输出，不作用于运行时从知识库检索到的参考信息**——这个缺口必须由应用自己补。

### 本仓库现状

- **出处展示只覆盖联网搜索**：`references-block` 折叠区 + 外链（`frontend/src/App.vue:1861-1864`），归一化在 `:697`，事件入口 `data.type === 'reference'`（`:887-892`）；后端 `refs` 全部来自 Tavily `_search`（`python_backend/agents.py:595-603`）。
- **知识库召回片段没有出处展示**：后端把召回内容当纯文本拼进 prompt，**无编号、无来源字段**（`agents.py:616`）；前端 `progress.js:45-47` 的 `entry.sources` 只取 `event.details.documents`，而该字段只在 `web_search` 步骤产生（`agents.py:602`）。→ 无法做可核查引用。
- 阶段时间线本身是完整的：`appendProgressEvent` 把 `step/tool_start/tool_end` 归并为 timeline 条目并补结束时间（`frontend/src/modules/execution/progress.js:25-53` 处理 step、`:54-83` 处理 tool），阶段文案表在 `:1-15`。
- 运行事件 SSE 增量拉取支持游标续传与断线重连（`frontend/src/modules/execution/useRunEvents.js:19-56`）。
- **演示回落实测 22 处**（`HarnessApp.vue` 17 处、`harness.css` 5 处），已有「demo-」前缀提示与页脚连接状态区分。

### 建议方案

**引用契约**（后端产出、前端只渲染）：

`Citation { id, sourceType, title, uri, locator(page/offset), snippet, score, permissionScope }`

**证据卡片**（每条命中一张）：

- 来源：文件路径或文档名 + 所属工作区。
- 层级：abstract / overview / detail，可切换。
- 命中原因：精确 token / 中文 trigram / 中文 bigram / LIKE 兜底 / 语义相似度（带分数）。
- 「读原文」：分页打开完整来源，沿用已有 `read_source` 能力。

命中原因必须由后端给出（hits 里带 reason 与 score），否则「为什么这条被选中」无法解释。

**引用标记**：答案里插入 `[ID:n]` 形态的标记，`n` 指向证据注册表里的稳定 ID（现有 `workspace:file:相对路径` / `workspace:doc:文档ID` 形态已足够作稳定 ID）；前端按 marker 解析，不按显示顺序；模型提到但不在白名单里的引用一律剔除。marker 长度上限抄 RAGFlow 的 128，来源注入预算抄它的 30000 token 口径并接进现有上下文预算。

**空状态区分**：连接失败与真实为空用不同文案与不同视觉，演示数据只在明确的「演示模式」下出现并带标识。

**验收**：知识库问答的每条断言都能点回原文；模型引用不存在的来源时前端不显示该引用。

---

## 十、业务侧可观测性

### 业界怎么做

两层：① **trace 层**用 OpenTelemetry 语义约定统一 span/metric 命名，让跨厂商可比；② **网关层**做路由、配额、故障转移与用量归属（成本按租户/项目归集）。

开源侧：

- **OpenTelemetry GenAI 语义约定**已拆到独立仓库 `open-telemetry/semantic-conventions-genai`。span 命名规则：**span name SHOULD be `@{gen_ai.operation.name}`**；`gen_ai.operation.name`、`gen_ai.provider.name`、`gen_ai.response.id` 为 Required；Agent 侧另有 `create_agent {gen_ai.agent.name}`、`invoke_agent` 命名与 `gen_ai.agent.id` / `gen_ai.agent.description`。指标名：`gen_ai.client.operation.duration`、`gen_ai.server.request.duration`、`gen_ai.server.time_per_output_token`、`gen_ai.server.time_to_first_token`；异常事件名 `gen_ai.client.fetch_response.exception`、`gen_ai.invoke_agent.exception`。
- **OpenLLMetry**（7,528 star）：给 LLM provider 与向量库提供 OTel instrumentation。
- **LiteLLM**（62,940 star）：生产级网关形态——virtual keys、spend tracking、guardrails、负载均衡；支持按 project/user 的多租户成本核算。
- **Envoy AI Gateway 已更名 Agent Router**（2,368 star，v1.2.1）：CRD 与 API group 不变（`AIGatewayRoute`、`AIServiceBackend`、`BackendSecurityPolicy`、`aigateway.envoyproxy.io`），CLI 仍为 `aigw`，仓库迁至 `theagentrouter/agent-router`；定位是「统一管凭据、路由、配额、故障转移与用量归属」。

大厂侧：

- **CloudWatch 生成式 AI 可观测性**：面向含 agent 的 GenAI 工作负载的质量/性能/健康度。
- **AgentCore 观测**：`Bedrock-AgentCore` 命名空间下的数据面 `Invocations` / `Latency` / `Errors`，摄入侧 `NumberOfMemoryRecords`；异步摄入日志落客户账号 log group。
- **百炼三段式成本模型**（见第五节）：规格费 + 检索阶段模型费 + 问答阶段模型费，每段独立计价，优化顺序是「关闭排序 → 调小初步召回 TopK → 其他」。

坑：

- OTel GenAI 属性在检索时仍标记为 **Development**，语义可能变动，落地需容忍版本漂移。
- 语义约定仓库被拆分后，旧仓路径全部变成「Moved」跳转页，依赖旧路径的脚本会取到空内容。
- 项目更名带来的运维坑：Envoy AI Gateway → Agent Router 后旧仓库链接重定向，但 CRD / CLI / 镜像路径都不变，文档与告警规则要同步更新。

### 本仓库现状

- `python_backend/modules/execution/trace.py` **不是 tracer，是脱敏预览器**：`trace_preview()` 做 password/secret/token/URL/IP 脱敏 + 长度截断（`:18-45`）。
- 事件是「单表 + JSON」：`execution_event(event_id, run_id, event_json, created_at)`（`python_backend/modules/execution/store.py:91-98`）。
- 指标接口齐全：`/harness/observability/metrics` → runs / byStatus / errors / toolCalls / recentRuns（`python_backend/api/routers/observability.py:107-121`）；趋势按 hour/day 分桶（`:183-215`）；跨运行导出 JSON/CSV（`:137-178`）；单 run trace JSON 导出（`:125-135`）。
- **成本只有 token**：`_record_usage` 从上游响应取 `prompt_tokens` / `completion_tokens`（`python_backend/agents.py:128-136`），转成 `usage` 事件（`:531-537`）。
- 事件类型集合：`step` / `tool_start` / `tool_end` / `text` / `usage` / `context_snapshot` / `error` / `clarify` / `thinking` / `recommend` / `complete` / `artifact`（`agents.py:536`、`:539`、`:588`、`:650`、`:733`、`:747-748`、`:768`，`modules/execution/langchain_agent.py:161`、`:184-189`，`workers/execution_worker.py:182`）。

缺口：

- **无 trace/span 结构**：事件里没有 `trace_id` / `span_id` / `parent_id`，跨 run 无法串联（`execution_run` 只有 `run_id` / `conversation_id`）。
- **无金额成本**：没有单价、模型归集、per-user / per-workspace 成本。
- 无延迟分位（P95/P99）、无业务口径的成功率（一次问答算不算成功没有定义）。
- 无 OpenTelemetry / Langfuse 依赖（`requirements.txt` 与 `pyproject.toml` 均无）。

### 建议方案

**不引第三方栈，先在现有事件表上补结构**：`execution_event` 加 `trace_id` / `span_id` / `parent_id` 三列，事件名规范化，步骤耗时写入既有 `durationMs`。这样 trace 树在本地就能拼出来，不引 OTel SDK，也不改存储选型。

**事件元数据挂最后一条**：按 AG-UI 的做法，token 用量、trace id、finish reason 可以在最终事件上一次带齐，不必单开统计通道。

**指标清单与采集点**（复用现有 `execution_event` 表，不引入新存储）：

| 指标 | 采集点 | 口径 |
| --- | --- | --- |
| 分通道命中率 | 召回处 | 词面命中数 / 语义命中数 / 两者皆无 |
| 语义分数分布 | 召回处 | top1 与 top3 分数，用于盯阈值漂移 |
| embedding 成本 | 向量生产 + 查询 | token 数与调用次数 |
| 索引新鲜度 | 探测处 | 最新 marker 与当前时间的差 |
| 门闸澄清率 | 意图门闸 | 澄清轮次占比 |
| 证据引用率 | 答案生成后 | 答案引用的证据数除以提供的证据数 |
| 预算超限率 | 装配处 | 超限返回错误的比例 |
| 延迟分位 | 执行器 | 每类事件的 P50 / P95 |

**成本三段式归因**：把 token 拆成「向量 / 排序 / 生成」三段分别记账，先只记 token 数不换算金额（单价表会变，token 数不会）。金额口径等 Harness 设置里的 `defaultBudgetUsd` 有了用量口径再补——现在它存了但没有读取方。

**采样**：按错误与延迟采样，不做随机采样；正常路径保留全量，失败路径永久保留。

---

## 十一、跨工作区共享知识

### 业界怎么做

共享不是「一套库所有人读」，而是**分层 + 谓词**：物理分层（collection / 表 / 分区）或逻辑分层（作用域 ID + 过滤谓词），再叠加策略层（Casbin / OPA）决定「谁能读哪一层」。

开源侧：

- **Dify**：默认**不共享**——workspace 是强隔离边界，全部资源归属单一 workspace，成员按 role 访问；跨工作区共享必须显式走「外部知识库 API」这条带契约的通道，而不是直接连库。
- **Mem0**：`app_id` 表达「跨用户共享的应用级记忆」，`user_id` 个人私有，`agent_id` 智能体私有，`run_id` 单次运行——四层叠加即可搭出共享/私有组合。
- **Weaviate**：共享落在 collection 内多 tenant；默认关闭且写入不存在 tenant 会报错，忘开 `autoTenantCreation` 会直接写入失败。
- **pgvector**：共享与隔离靠分区/分表落地。
- **Casbin / OPA**：策略层可对「跨 workspace 的资源访问」做统一判定，而不是把授权逻辑散在每个模块。

大厂侧：

- **Foundry IQ**：一个知识库（= 一组知识源 + 检索参数 + 权限解析策略）**被多个 agent 复用**；查询时 agentic retrieval 规划查询、选择数据源、并行检索、聚合，并**逐次执行用户权限**。
- **AgentCore Memory**：namespace 粒度四档决定共享范围；跨账号靠 resource-based policy 授权数据面调用。
- **OpenViking**：`resources` / `user` / `agent` 三 scope 明确区分「公共知识 / 用户私有 / **跨 agent 共享**」。
- **Anthropic 缓存**：缓存条目**在组织之间、以及同组织不同 workspace 之间隔离**——缓存隔离本身就是隐式的租户边界。
- **Salesforce Agentforce**：知识接地依赖 Data Library + User Permission Set，权限模型仍是「用户 → 权限集 → 对象」，跨团队共享靠共享 Data Library 而非共享权限。
- **百炼**：挂 N 个知识库则检索 token 消耗 ×N。

坑：

- 共享设计的最大坑在**写路径与读路径的作用域不对称**：只在读时加过滤、写入时不落作用域字段，就会出现跨租户可见性泄漏。
- Dify 的强隔离代价：跨 workspace 共享必须走外部 API 契约，不能直连，延迟与鉴权都要单独设计。
- 共享与权限必须在**同一次检索调用**里生效，拆开做就会出现越权召回。

### 本仓库现状

- 检索严格按 `workspace_id` 隔离：索引主键 `(workspace_id, source_id)`（`python_backend/modules/retrieval/workspace_index.py:135-148`），FTS 检索 `WHERE workspace_id=?`（`:428`、`:443`），`remove_source` 按 workspace 删（`:190-199`）。
- 记忆范围：同 `workspace_id` 的多个会话共享一个 scope（`scope_id = sha256('workspace:' + workspace_id)`，`memory/store.py:75-86`）。
- **没有任何共享/全局知识表**；向量表按 `file_id` 过滤，**连 `workspace_id` 列都没有**（`vector_store.py:63-77`、`:147`、`:191`）。
- 无跨 workspace 检索参数、无共享层权限过滤、无共享知识发布与引用计数。

结论：属「**刻意未做**」而非「做错」——共享表属于其他模块的边界，与第四节的多用户模型一起做才有意义。

### 建议方案

**三级作用域**

| 级别 | 范围 | 落地 |
| --- | --- | --- |
| 工作区私有 | 现状 | 本地索引 + `doc:` / `file:` 前缀 |
| 组织共享 | 同组织只读 | 独立 source 前缀（如 `shared:<org>:<id>`），检索时按作用域合并候选 |
| 公共知识 | 全局 | 同上，标签为公开 |

**边界与前置**

- 共享知识必须与第四节的权限模型一起做，否则「组织共享」会退化成无差别泄露。
- 共享库与工作区私有库**物理分开**（不同表或不同库），避免权限过滤互相干扰。
- 共享内容进入工作区上下文时，同样走「证据 + 来源 + 层级」这套结构；模型侧不区分来源级别，权限判定在检索期完成。
- 跨工作区共享若外部系统已有知识，走「检索代理」形态（本仓出查询、外部返回带 `score` 的片段），而不是直连对方的库——这条路的接口形状参考 Dify 外部知识库 API：`knowledge_id` / `top_k` / `score_threshold` / `metadata_condition` → 返回带 `score` 的条目。

---

## 十二、本仓库明确缺失的能力（代码级清单）

以下是逐条检索确认「代码里确实没有」的能力，供排期时直接取用：

1. 检索重排模型（cross-encoder / LLM rerank）与 MMR 多样性重排——全仓 `rerank|cross_encoder|bge-reranker` 零命中。
2. 事实级有效期、`supersedes` 链、冲突检测与裁决；同一事实多版本并存。
3. user / tenant / role / ACL 实体与表；鉴权中间件；检索期用户级裁剪。
4. 可验证身份——`X-Harness-Owner` 是客户端自证，可伪造。
5. 向量摄取队列、批量摄取、增量差分向量写入、embedding 成本预算与账单。
6. 跨 SQLite / Postgres / MinIO 的事务或全局 outbox；补偿表与死信（记忆投递是唯一的局部 outbox）。
7. OpenViking 部署编排、探活、熔断、真实环境验收数据。
8. CI（仓库无 `.github`）与把评测分数接进 release gate 的通路。
9. 知识库片段的可核查引用（出处编号 + 原文对齐展示）。
10. trace/span 层级、金额成本统计、延迟分位、业务成功率指标。
11. 跨工作区共享知识层与共享表。
12. 前端测试运行入口——`package.json` 无 test 脚本，两个 `node:test` 用例跑不起来。
13. `numpy` / 向量检索加速——当前是纯 Python 点积，只适合小规模工作区。
14. 金额预算执行——`defaultBudgetUsd` 没有用量口径，真正被执行的是 token 预算。
15. 历史生成文件的产物登记——需要人工登记，不会自动进入产物列表。

---

## 十三、分期建议

**P0（下一轮可直接开工，各项都能用现有标注集验收）**

1. 融合后重排层（确定性版，不引入模型调用）。
2. 冲突与时效识别（事实结构扩展 + 确定性冲突判定）。
3. 向量摄取批量化（复用现有 `embed_batch`）+ 成本记账 + 缓存键。
4. outbox 与幂等（单一事实源 + 派生物可重建）+ 对账任务。
5. 评测三层化 + 标注集版本化 + **把 `scores.json` 接进 release gate** + 前端补 test 脚本。

**P1（上生产前必须）**

6. 权限模型（身份、检索期过滤、装配前复核、审计）。
7. OpenViking 真实部署、探活与抽取质量评测。
8. 前端证据卡片与可核查引用。
9. 业务指标采集（trace 三列、延迟分位、成本三段式）。

**P2（规模化之后）**

10. 跨工作区共享知识与共享库分离。

**明确不做**：不引入 RAGAS / Langfuse / OTel SDK 等第三方栈来替代自研判定器与埋点（eval 目录用 Ragas 是隔离环境里的选型，不进主环境）；不引入分词器依赖，中文分层继续靠 FTS5 trigram + bigram；不在本阶段改共享向量库表结构；不引入 Casbin/OPA 作为起步依赖，等出现第二个授权消费方再抽。

---

## 十四、验证命令

文档改动只需核对路径与命令一致性。涉及代码改动时执行仓库约定的验证命令：

    .\.venv\Scripts\python.exe -m unittest python_backend.modules.context_engineering.test_chain python_backend.modules.context_engineering.test_snapshots -v
    .\.venv\Scripts\python.exe -m unittest python_backend.modules.retrieval.test_workspace_index python_backend.modules.retrieval.test_recall_quality -v
    .\.venv\Scripts\python.exe -m compileall python_backend
    .\.venv\Scripts\python.exe skill-center/test_center.py
    .\.venv\Scripts\python.exe skill-center/test_agent_tools.py
    npm --prefix frontend run build

需要真实 embedding 服务的语义评测默认跳过，显式打开：

    $env:HOTLINE_SEMANTIC_EVAL=1
    .\.venv\Scripts\python.exe -m unittest python_backend.modules.retrieval.test_semantic_recall -v

提示词静态检查（零成本，可进 CI）：

    .\.venv\Scripts\python.exe eval\prompt_checks.py

前端用例（Node 内置 runner，无新依赖）：

    node --test frontend/src/modules/workspaces/paths.test.js frontend/src/modules/execution/progress.test.js

---

## 十五、参考来源

访问日期均为 2026-11-10（star 数为该日检索快照）。开源项目条目标 star 与 release 标签；大厂条目标官方文档或官方博客。

### 开源项目

- pgvector（23,625 star）：混合检索示例、迭代扫描、HNSW 默认值、过滤与分区、租户隔离 —— https://github.com/pgvector/pgvector
- Qdrant（35,479 star，v1.20.0）：prefetch、RRF/DBSF、快照语义、payload 索引漏召回 —— https://qdrant.tech/documentation/concepts/hybrid-queries/ ；https://github.com/qdrant/qdrant/issues/9373
- Weaviate（16,944 star，v1.40.4）：alpha 语义、v1.24 默认改 Relative Score Fusion、explainScore、多租户 —— https://weaviate.io/developers/weaviate/search/hybrid ；https://weaviate.io/developers/weaviate/manage-data/multi-tenancy
- Milvus（46,614 star，v3.0.5）：多向量字段与混合重排 —— https://milvus.io/docs/multi-vector-search.md
- Dify（160,699 star，1.19.0）：两层检索设置、索引方式二选一与不可逆、外部知识库 API、workspace 隔离 —— https://docs.dify.ai/en/use-dify/nodes/knowledge-retrieval ；https://docs.dify.ai/en/self-host/use-dify/knowledge/create-knowledge/setting-indexing-methods.md ；https://docs.dify.ai/en/self-host/use-dify/knowledge/external-knowledge-api.md ；https://docs.dify.ai/en/self-host/use-dify/workspace/readme.md
- RAGFlow（93,799 star）：服务拆分、摄取画布、引用标记与 token 预算 —— https://github.com/infiniflow/ragflow ；https://github.com/infiniflow/ragflow/blob/main/internal/agent/component/citation_sources.go ；https://github.com/infiniflow/ragflow/blob/main/internal/agentic_rag/citations.go
- FlagEmbedding / BGE（12,304 star，v1.4.2）：bge-m3 三种检索法、bge-reranker 系列 —— https://github.com/FlagOpen/FlagEmbedding
- Zep / Graphiti（32,670 star，v0.31.2）：双时态事实、冲突作废、Context Block 格式 —— https://help.getzep.com/facts.md ；https://github.com/getzep/graphiti
- Mem0（68,662 star，v2.2.1）：ADD-only、Dream 三动作、四级作用域、过滤 —— https://docs.mem0.ai/core-concepts/memory-operations/add.md ；https://docs.mem0.ai/platform/features/dream.md ；https://docs.mem0.ai/platform/features/entity-scoped-memory.md ；https://github.com/mem0ai/mem0/issues/4896
- Letta（25,389 star，0.16.8）：持久身份、MemFS git 版本化记忆、权限四档 —— https://docs.letta.com/concepts/memfs/index.md ；https://docs.letta.com/configuration/permissions/index.md
- LangMem（1,754 star）：记忆分类与载体 —— https://github.com/langchain-ai/langmem
- Cognee（33,155 star，v1.6.7）：持久 AI 记忆定位 —— https://docs.cognee.ai/llms.txt
- Casbin（20,489 star，v3.11.0）/ OPA（12,452 star，v1.22.2）：策略层 —— https://github.com/casbin/casbin ；https://github.com/open-policy-agent/opa
- Celery（29,145 star）/ Temporal（24,284 star）/ Prefect（24,138 star）/ Airflow（47,421 star）：幂等与持久执行 —— https://github.com/celery/celery ；https://github.com/temporalio/temporal ；https://github.com/PrefectHQ/prefect
- Ragas（16,261 star，v0.4.3）：Faithfulness 与 Context Precision@K 公式 —— https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/index.md
- DeepEval（19,375 star）/ promptfoo（26,975 star，0.125.1）/ Langfuse（37,175 star，v4.77.0）/ Phoenix（12,208 star）/ Opik（23,277 star，2.2.143）：评测与门禁 —— https://github.com/confident-ai/deepeval ；https://www.promptfoo.dev/docs/intro/ ；https://langfuse.com/docs/evaluation/experiments/experiments-ci-cd.md ；https://arize.com/docs/phoenix/evaluation/llm-evals
- OpenTelemetry GenAI 语义约定（527 star，语义仍标记 Development）：span 命名与必填属性、指标名、异常事件名；旧仓路径已迁移 —— https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md
- OpenLLMetry（7,528 star）/ LiteLLM（62,940 star）/ Envoy AI Gateway → Agent Router（2,368 star，v1.2.1）：instrumentation、virtual key 与 spend tracking、用量归属 —— https://github.com/traceloop/openllmetry ；https://github.com/BerriAI/litellm ；https://github.com/theagentrouter/agent-router
- Unstructured（15,701 star）/ Docling（70,315 star，v2.149.0）/ MinerU（83,357 star）：文档解析与统一表示 —— https://github.com/Unstructured-IO/unstructured ；https://github.com/docling-project/docling
- LangGraph（44,672 star）：checkpointer 与 store、durable execution、checkpoint 需 prune —— https://docs.langchain.com/oss/python/langgraph/durable-execution
- 解析层参考（既有实现）：Tencent WeKnora（混合检索、父子分块、引用、跨会话记忆与用户确认）—— https://github.com/Tencent/WeKnora

### 大厂与官方规范

- Azure AI Search：语义排序、混合检索、向量索引参数、限流、文档级访问控制与 ACL 强制执行 —— https://learn.microsoft.com/en-us/azure/search/semantic-search-overview ；https://learn.microsoft.com/en-us/azure/search/vector-search-how-to-create-index ；https://learn.microsoft.com/en-us/azure/search/search-limits-quotas-capacity ；https://learn.microsoft.com/en-us/azure/search/search-query-access-control-rbac-enforcement
- Microsoft Foundry IQ（知识库复用与 agentic retrieval）—— https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/what-is-foundry-iq
- Microsoft 365 Copilot Agent Evaluations CLI（默认阈值表）—— https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/evaluations-cli-overview
- Amazon Bedrock Knowledge Bases：切片策略、检索与重排配置 —— https://docs.aws.amazon.com/bedrock/latest/userguide/kb-chunking.html ；https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-retrieve.html
- Amazon Bedrock AgentCore Memory：术语、组织与 namespace、策略、检索、TTL、观测、跨账号 —— https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory.md ；https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-organization.md ；https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/long-term-retrieve-records.html
- Amazon Bedrock Evaluations 与 AgentCore Evaluations —— https://aws.amazon.com/bedrock/evaluations/ ；https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/evaluations.html
- Google Cloud：RAG Engine 检索与重排、grounding check 与矛盾引用 —— https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/rag-engine/retrieval-and-ranking ；https://docs.cloud.google.com/generative-ai-app-builder/docs/builder-apis
- 阿里云百炼：知识库计费与检索参数、长期记忆与记忆库 —— https://help.aliyun.com/zh/model-studio/billing-for-knowledge-base ；https://help.aliyun.com/zh/model-studio/long-term-memory
- 扣子 Coze：知识库检索节点与限制 —— https://loop.coze.cn/open/docs/guides/knowledge_node ；https://www.coze.com/open/docs/guides/knowledge_limits
- Anthropic：prompt caching 与计费、context engineering —— https://platform.claude.com/docs/en/build-with-claude/prompt-caching ；https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- MCP 授权规范（2025-11-25）与 A2A 规范 v0.3.0 —— https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization ；https://a2a-protocol.org/v0.3.0/specification
- AG-UI 事件模型 —— https://docs.ag-ui.com/concepts/events
- OpenViking 产品页（`viking://` 协议与三层加载，厂商自述数据）—— https://www.openviking.ai/product
- 字节 CloudWeGo Eino（Memory / Session / Store 属业务层的边界声明）—— https://cloudwego.io/docs/eino

### 二手来源（用于取数与结论方向，非权威定义）

- contextual retrieval 与 late chunking 的 nDCG 对照与索引成本 —— https://particula.tech/blog/contextual-retrieval-vs-late-chunking
- Mem0 去重与更新策略的实测比较 —— https://blog.csdn.net/kanhaoning/article/details/165128345
- LLM 可观测平台对比（Langfuse / LangSmith / Phoenix）—— https://scored.tools/blog/langsmith-vs-langfuse-vs-arize-phoenix-llm-observability
- 火山引擎 VikingDB 架构分析（存算分离、租户隔离、权限管理器）—— https://www.zybuluo.com/changedi/note/2645044
- 阿里云 AnalyticDB for MySQL AI Agent MemStore 长期记忆方案（官方文档）—— https://help.aliyun.com/zh/analyticdb/analyticdb-for-mysql/long-term-memory-overview
- 腾讯 WeKnora 版本演进（官方发布记录）—— https://github.com/Tencent/WeKnora/releases
