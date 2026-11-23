# 意图识别与澄清（intent）

> 模块路径：`python_backend/modules/intent/`
> 前端对应：`frontend/src/modules/intent/`（只有 `.gitkeep`，无独立前端实现；澄清交互由 `frontend/src/modules/requirement/`、`frontend/src/modules/skills/` 承接）
> 状态：意图目录 + 三级级联分类（关键词粗筛 → embedding 向量召回 → 大模型判定）+ 置信度分级门闸 + System One 决策层（意图与诉求歧义度）+ 意图级/需求级澄清 + 检索链路路由；决策模型启用后门闸改按歧义度判断。

## 意图目录与别名解析
### 入口
- `python_backend/modules/intent/catalog.py:ACTION_CATALOG` —— 顶层动作目录（file/ppt/deep/skills/chat，默认 chat）
- `python_backend/modules/intent/catalog.py:RETRIEVAL_CATALOG` —— 检索链路目录（semantic/keyword/text2sql/graph/hybrid，默认 hybrid）
- `GET /intent/catalogs` —— 对外暴露两个目录（只含 scope、default 与 name/label/description）
### 行为
- 每个意图含 name、label、description、keywords、examples：keywords 供粗筛，examples 供模型提示。
- `resolve()` 归一化模型输出：去空格、转小写、连字符与空格转下划线，先查别名表再按名称大小写不敏感匹配，都不中返回 None；别名表由 `IntentCatalog.aliases` 提供，两个内置目录当前未配置别名。
### 关键实现
- `python_backend/modules/intent/catalog.py:IntentCatalog.resolve` —— 归一化与别名解析
- `python_backend/modules/intent/catalog.py:Intent.prompt_block` —— 意图提示片段渲染

## 关键词粗筛
### 入口
- `python_backend/modules/intent/classifier.py:score_keywords`
- `python_backend/modules/intent/classifier.py:keyword_candidates`
### 行为
- 纯子串匹配，不调用模型；排序键为「命中数降序 → 命中关键词最长者降序 → 名称升序」，命中数相同时更具体的关键词优先（如 `ppt` 胜过 `这份`）。
- `keyword_candidates` 默认取前 3 个候选；一个都没命中时返回该目录的默认意图。
- 置信度由命中分布估算：只命中 1 个泛用词压到 0.55；多次命中基准 0.9，领先第二名再加 0.05，上限 0.95。
### 关键实现
- `python_backend/modules/intent/classifier.py:_confidence_from_scores` —— 关键词命中到置信度的估算规则

## embedding 向量召回
### 入口
- `python_backend/modules/intent/retrieval.py:ExampleVectorStore`
- `python_backend/modules/intent/retrieval.py:embed_text`
### 行为
- 第二层把目录里的示例句向量化，按余弦相似度为一次提问召回候选意图；送入 embedding 的文本先经 `python_backend/modules/context_engineering/privacy.py:sanitize_text` 脱敏。
- 示例向量首次使用时批量计算并缓存到进程内存；`warmup()` 失败即把本层标记为不可用。
- 相似度低于 `MIN_SIMILARITY`（0.45）视为无候选；`recall` 默认取前 3 名，排序为分数降序、名称升序。
- embedding 未配置、接口不通、返回维度与配置不一致一律返回 None，整层跳过，链路不中断。
### 关键实现
- `python_backend/modules/intent/retrieval.py:ExampleVectorStore.recall` —— 余弦召回与相似度下限过滤

## 大模型判定与多次采样聚合
### 入口
- `python_backend/modules/intent/classifier.py:classify`
- `python_backend/modules/intent/classifier.py:_aggregate`
### 行为
- 提示要求返回 `{"intent","confidence","probabilities"}`：intent 只能取候选集合，probabilities 必须覆盖全部意图，否则概率退化成 1.0、门闸失去区分度。
- 同一问题并行采样 3 次（`GATE_SAMPLES`），某次失败单独丢弃，不影响其余采样。
- 聚合：意图取多数票，票数相同看累计概率；置信度取各次自报 confidence 的平均，保留三位小数；概率分布按总和归一化，模型只回旧格式（intent 加 confidence）时按单点分布处理。
- 模型不可用、调用失败或输出不合法时退回关键词结论；连关键词候选都没有才落默认意图（置信度 0.0，tier 为 low）。
### 关键实现
- `python_backend/modules/intent/classifier.py:_sample` —— 三次并行采样与聚合

## 置信度分级与门闸
### 入口
- `python_backend/modules/intent/classifier.py:_tier`
- `python_backend/modules/execution/engine.py:_intent_gate`
### 行为
- 分级阈值：`CONFIDENT=0.75` 为 high，`AMBIGUOUS=0.35` 为 medium，更低为 low。
- 向量层另有门槛 `VECTOR_CONFIDENT=0.85`：相似度达到即直接采用向量层结论，不再问模型。
- `classify` 判定顺序：向量层高分 → 关键词高置信度 → 决策层 → 大模型 → 关键词兜底 → 默认意图。
- `IntentResult.needs_clarification` 为「tier 是 medium 或已被门闸拦下」；门闸由调用方传入 `gate` 阈值，低于阈值即标 `gated=True`、tier 降为 medium。
- 引擎侧阈值 `AgentEngine.INTENT_GATE = 0.6`，只对 `chat`、`deep` 且未选中文档的提问生效；命中后发 SSE `clarify` 事件终止本轮，用户作答后作为新一轮对话重新进入级联。
### 关键实现
- `python_backend/modules/intent/classifier.py:_gated` —— 门闸判定（歧义度优先）
- `python_backend/modules/execution/engine.py:_fallback` —— 产出 `clarify` 事件

## System One 决策协议（意图与歧义度）
### 入口
- `python_backend/modules/intent/decision.py:DecisionClient`
- `python_backend/modules/intent/decision.py:build_questions`
### 行为
- 一次前向同时给出意图、该意图的置信度与用户诉求的歧义度，不生成文本。
- 请求体为 `{"model","state","questions"}`，`state` 截断到 2000 字符；questions 含一个 choice 型 `intent` 与一个 noul 型 `ambiguous`，choice 每一项都带示例，避免 file 与 chat 等近似意图混淆。
- 响应解析 `answers.intent.choice`（经目录归一化）与 `answers.ambiguous.noul`，数值收进 0~1，非数字记 0。
- 决策层优先于大模型层，未配置或调用失败返回 None 并自动落回大模型判定；决策层启用时门闸改看歧义度，`AMBIGUITY_GATE=0.86`，歧义度达到即先澄清。
### 关键实现
- `python_backend/modules/intent/decision.py:DecisionClient.judge` —— 调用决策端点
- `python_backend/modules/intent/decision.py:parse_decision` —— 响应解析与数值收敛

## 澄清请求（三个方向加自由输入）
### 入口
- `python_backend/modules/intent/clarify.py:build_clarify_request`
- `python_backend/modules/intent/clarify.py:ClarifyRequest`
### 行为
- 固定给三个方向（`CLARIFY_OPTIONS = 3`），每条含意图名、中文标签与一句说明。
- 方向优先由模型给出；模型不可用、报错或输出不合法时用候选意图自己的说明兜底，保证始终给得出三条；方向池顺序为级联候选在前、目录其余意图补齐，重复意图去重。
- 返回体为 `{question, options:[{intent,label,hint}], candidates}`，question 保留原问题原文。
- 用户除点选三个方向也可自由输入；自由回答按新一轮对话重新进入级联。
### 关键实现
- `python_backend/modules/intent/clarify.py:parse_clarify_reply` —— 解析、去重、截断到三条

## 需求级澄清
### 入口
- `python_backend/modules/intent/requirement.py:build_requirement_clarify_request`
- `python_backend/modules/execution/engine.py:_requirement_gate`
### 行为
- 判定标准是需求三要素：目标用户、核心范围、验收标准，三项都说得清才算清楚；判定为清楚一律不拦，模型不可用或输出不合法同样放行，模型失败不阻断回答。
- 需求不清时给三个方向（`REQUIREMENT_OPTIONS = 3`），label 不超过 12 字且要求大白话；模型没给方向时用固定三要素兜底（谁在用、这一版做哪些事、怎么算做完）。
- 引擎只在绑定 `requirement-analysis` 技能的机器人（需求模式）下启用，且只对 `chat`、`deep` 且未选中文档的提问生效。
- 上一轮刚澄清过、或本轮是在回答助手上一轮的提问，都不再追问；需求模式下一律不跑通用意图门闸。
### 关键实现
- `python_backend/modules/intent/requirement.py:build_requirement_prompt` —— 准入判定提示（含不要重复澄清的约定）

## 检索链路路由（retrieval route）
### 入口
- `python_backend/modules/intent/__init__.py:retrieval_fallback`
- `python_backend/modules/intent/__init__.py:parse_retrieval_route`
- `python_backend/modules/execution/engine.py:_choose_retrieval`
### 行为
- 链路取值：semantic（语义检索）、keyword（关键词检索）、text2sql（文档查询）、graph（关联检索）、hybrid（综合检索）。
- 无模型可用时按历史关键词规则兜底：命中「多少数量统计列表总数有哪些」或「count、list、how many、sql」判 text2sql，命中「关系依赖关联上下游谁负责属于」判 graph，都不中判 hybrid。
- 有模型时先合并候选（关键词粗筛加向量召回），再让模型在候选里选一条；输出非法或调用失败时保留兜底结果，引擎把选择过程发成 `retrieval_route` 步骤事件，带中文标签与耗时。
### 关键实现
- `python_backend/modules/intent/__init__.py:_ROUTE_KEYWORD_RULES` —— 历史关键词规则

## 数据与存储

- 无独立持久化：意图目录是模块内常量；澄清请求只以 SSE 事件下发，不落库。
- 向量缓存只存在进程内存（`ExampleVectorStore._vectors`），重启或多进程后需重新 `warmup()`。
- 配置只写项名：`embedding_api_key`、`embedding_base_url`、`embedding_model`、`vector_dimension`、`decision_base_url`、`decision_api_key`、`decision_model`（取值见 `python_backend/config.py`）。

## 接口清单

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/intent/catalogs` | 返回 action 与 retrieval 两个意图目录（scope、default、intents） |
| `POST` | `/intent/classify` | 对一次提问跑三级级联，返回 intent、label、confidence、source、tier、needsClarification、candidates |

意图路由没有独立前缀；澄清请求由 `/agent/*/stream` 的 SSE `clarify` 事件下发。

## 边界与已知限制

- 关键词层只做子串匹配，不处理否定、同义与上下文。
- 向量层要求 embedding 返回维度与 `vector_dimension` 一致，否则整层跳过。
- 大模型层的概率分布按模型自报值归一化，不保证与真实概率一致；判定主要看自报 confidence 的均值。
- 决策模型未配置时门闸退回自报置信度阈值（`INTENT_GATE=0.6`），与歧义度口径不同。
- `/intent/classify` 未传 gate 与 decision，因此该接口不会返回 `gated=True`，也不走 System One。
- 意图级与需求级澄清只作用于 `chat`、`deep` 且未选中文档的提问；PPT、技能、文件问答不触发。
- 检索链路的关键词兜底规则与意图目录关键词两处并存，改动时两处都要看。
- 前端无独立 intent 模块，澄清交互由 requirement 与 skills 前端模块承接。
