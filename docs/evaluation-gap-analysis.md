# 评测能力差距清单（对照高星开源项目）

> 更新日期：2026-11-23
> 对照对象分四类：评测框架、基准榜单、观测/生产化平台、具身仿真。star 数据来源与实测日期见文末说明。
> 说明：本清单只写**能力差距**，不写实现过程。优先级对应 `docs/spec/` 里的后续规格编号。

## 一句话结论

结构类能力（轨迹断言、多轮、用户模拟、出处、门禁、成本护栏）已经**对齐甚至领先**高星项目；
真正的差距集中在三处：**语义层评分**、**样本来源**、**执行隔离**。
再往下一层是**在线化与观测对接**（生产 trace 上跑评测、OpenTelemetry 出口），属于第二阶段的事。

## 对照项目全景

| 类别 | 代表项目 |
| --- | --- |
| A. 评测框架 | Inspect AI、promptfoo、deepeval、OpenAI Evals、Opik、Giskard、Deepchecks、Evidently AI |
| B. 基准榜单 | SWE-bench、BFCL、Toolathlon、AgentBench、τ-bench / τ²-bench、WebArena、agentdojo、MT-Bench / Arena-Hard / AlpacaEval、HELM、lm-evaluation-harness |
| C. 观测 / 生产化 | Phoenix (Arize)、Opik (Comet)、Langfuse、MLflow、Evidently AI |
| D. 具身仿真 | EmbodiedBench、GenSim、RMBench、leRobot 等 |

一个值得记住的信号：**OpenAI Evals 的官方托管平台已于 2026-11-30 关停，官方迁移指南推荐迁往 promptfoo**。
连 OpenAI 都在把评测平台交给工具型框架，而不是自建大而全平台——这印证了本项目「不追平台规模、只补评测有效性」的路线。

## 能力对照矩阵

| # | 能力维度 | 高星基线 | Hotline 现状 | 差距 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| 1 | 语义/模型评分库 | Inspect 内置 scorer 库 + 自定义 scorer；deepeval 20+ metrics（G-Eval、answer relevancy、faithfulness、contextual precision/recall、hallucination、bias、toxicity）；promptfoo 断言分层（确定性 / 结构 / 语义相似度 / 模型判分 / 延迟 / 成本） | `rubric` 类型：`always` / `contains` / `equals` / `json_equals` / `model`（通用 criteria）/ `trace` / `multi`；模型判分只有一条通用通道 | **缺**：语义指标库（话题偏离、答非所问、事实一致性等），也没有延迟/成本断言 | **S-005** |
| 2 | 工具调用正确性 | ragas agent metrics（tool accuracy、topic adherence）；BFCL 用 AST 评估调用正确性 | 只能断言「调过哪些工具」（`expectTools` / `forbidTools`） | **缺**：参数级断言（调对没有、参数对不对） | **S-005** |
| 3 | 评委可替换与判分校准 | JudgeArena（评委模型/来源可换）、MT-Bench（人机一致性）、promptfoo 模型判分 | 判分模型固定走 `config.settings`，没有「判分与人工标注吻合率」这类校准 | **缺**：评委可配 + 判分一致性度量 | **S-005**（并入） |
| 4 | 样本自动合成 | deepeval Synthesizer（从文档生成 goldens）；promptfoo 从知识库生成用例 | 样本全手写，靠人肉出题 | **缺**：合成链路 | S-014 |
| 5 | 安全红队评测 | promptfoo redteam（OWASP LLM Top10 插件 × 策略：prompt-injection / PII / 越权 / SSRF / 越狱）；agentdojo 提示注入基准 | 无 | **缺**：整块能力 | S-014 |
| 6 | 多维风险指标 | HELM 七类指标（accuracy / calibration / robustness / fairness / bias / toxicity / efficiency）；Evidently（幻觉、边缘 case、PII 泄露、越狱） | S-012 已按 rubric 类型派生失败分类（missing_keyword / output_mismatch / semantic_mismatch / trace_assertion_failed 等），不再一律 `unknown` | **缺**：安全、公平、毒性、稳健性维度 | S-014 |
| 7 | 相对 / 对战式评估 | Arena-Hard、AlpacaEval、Chatbot Arena（同一问题两版答案谁更好） | 只有绝对阈值门禁 | **缺**：相对判定 | S-006 |
| 8 | 多变体矩阵对比 | promptfoo 招牌能力：同一批用例 × 多 prompt 版本 / 多模型并排矩阵 | 只有「历史报告」里两两 run 对比（base/target） | **缺**：矩阵视图 | S-006 |
| 9 | 可靠性指标 | τ-bench 的 **pass^k**（每次都对才算可靠）与无偏估计；Inspect epochs + reducer + `--compare` | `passAtK`（≈pass^k）、`flakyRate` | **缺**：宽松版 `pass@k`、置信区间 / 噪声判定 | S-006 |
| 10 | 执行隔离 | Inspect 支持 Docker / K8s 沙箱；SWE-bench per-instance 容器；Toolathlon 每任务独立容器 | 仅 `eval:` 命名空间 + 会话列表过滤，跑的是真实 Worker | **缺**：沙箱与副作用隔离 | S-015 |
| 11 | CI 门禁 | promptfoo 官方 GitHub Action；Inspect 退出码 | 有 CLI（`python -m python_backend.eval_gate`，退出码 1），但仓库无 CI workflow | **缺**：流水线接入 | S-015 |
| 12 | 长程任务与工具调用专项基准 | Toolathlon（108 个长程任务 / 32 个真实应用 / 604 个工具，多为 MCP，平均约 20 轮工具调用，确定性评分脚本）；BFCL V4（单轮 / 多轮 / agentic，含 AST 评估） | 无长程任务集，无函数调用专项集 | **缺**：任务集与工具专项评测 | S-016 |
| 13 | 任务集 / 环境注册表 | Inspect 200+ 内置基准；SWE-bench 真实 GitHub issue；AgentBench 可扩展环境注册表 | 有 BIRD SQL（SQLite 子集） | **缺**：任务集抽象与环境注册表 | S-016 |
| 14 | 在线评估与回归监控 | Opik online eval（对生产 trace 跑规则）、Evidently monitor、Deepchecks | 只有离线跑批 | **缺**：生产 trace 上的持续回归监控 | S-017（候选） |
| 15 | 观测对接 / OpenTelemetry 出口 | Phoenix、Opik、Langfuse 都以 OTel 接收 trace，评测与生产 trace 同管道 | 有自有事件流与「追踪与日志」页，无 OTel 导出 | **缺**：与外部观测栈对接 | S-017（候选） |
| 16 | 成本与限流 | Inspect token/cost accounting + 资源限额 | S-004 已加 token / 样本数 / 时限三种预算 + 成本估算 | 基本对齐 | — |
| 17 | 日志与回放 | Inspect log viewer（每条消息、工具调用、分数、耗时） | 轨迹回放（事件表 + 逐轮输出 + 出处） | 基本对齐 | — |
| 18 | 多轮与用户模拟 | τ-bench user simulator + 数据库交互 | 脚本多轮 + 模型扮演用户 + `avgTurns` | 基本对齐 | — |
| 19 | 具身评测 | EmbodiedBench / GenSim / RMBench：仿真环境 + 感知/操作指标；leRobot / openpi 等数据与仿真栈 | 无 | 差一个量级 | S-016（只留接口） |
| 20 | 标准化 harness 与多模型适配 | lm-evaluation-harness（统一任务接口 + 多 provider）；OpenAI Evals（YAML registry） | 自建 rubric / store / 路由，绑定单一模型入口 | 有意不做多 provider；YAML registry 不追 | — |
| 21 | 语义轨迹评分 | LangChain / LangGraph trajectory evaluator；OpenHands 的 trace 分析（评过程，不只评终答） | 只有结构轨迹断言 | **缺**：过程语义评分 | **S-005** |
| 22 | 可评覆盖率（gradable coverage） | Dify 评测台：每条用例判 Pass / Fail / Not gradable / Untested，并给覆盖率 | 只有 `passRate`，skip 与未评分的口径分散 | **缺**：覆盖率与 notGraded 计数 | S-006 |
| 23 | 人工标注回流 | Dify「标注 → 批量测试 → 对比」闭环；OpenAI Evals 用人工示例做 model-graded 基准 | 样本全手写，没有标注闭环 | **缺**：标注回流为回归集 | S-014 |
| 24 | 定期回归机制 | lm-evaluation-harness / vLLM / Transformers：固定 revision + 结果快照进版本库 + nightly 重跑与基线 diff | 有 snapshot 与 provenance，但样本改动无 diff、无定期回归 | **缺**：基线 diff + 定期回归任务 | S-018（候选） |
| 25 | 检索指标与 Agent 报告并表 | RAGFlow / GraphRAG（local、global 分开评）/ LightRAG：召回与生成同切片同报告 | Ragas 在 `eval/` 独立脚本里跑，切片与主链不同，报告分离 | **缺**：并表 + 切片口径标注 | S-014（附带项） |

顶层项目的具体做法拆解见 [顶级高星项目的评测是怎么做的](evaluation-practices.md)。

## 已经领先、不要再花力气补的部分

- **轨迹断言**：澄清次数、工具集合、工具错误上限、步骤数、助手类型、对话轮数——Inspect 的 scorer 也要靠事件流才有同等信息。
- **运行出处**：模型名 + git commit + 技能包 sha256 + 测评集版本，事后能复现「这轮怎么跑出来的」。
- **门禁口径单一**：HTTP 接口、CLI、页面三处共用一份 `check_gates`，不会出现两套判定。
- **多轮 + 用户模拟**：脚本与模拟双模式，轮数可断言。
- **预算护栏**：三种上限 + 成本估算，比大多数框架的限额更直接。
- **控制台一体**：发起、结果、轨迹、门禁、历史、导出都在 Harness 里，不依赖外部 viewer。

## 明确不追的东西

- 不引入 Inspect AI / promptfoo / deepeval / Phoenix / Opik 等框架，也不做它们的 API 对齐。
- 不做 YAML DSL：现有 rubric 用 JSON，前端可直接编辑。
- 不做托管 dashboard（Confident AI 那种）：自带的 Harness 控制台够用。
- 不做多模型 provider 抽象：本项目只有一个模型入口。
- 不做观测平台（Phoenix / Langfuse 那种）：自建追踪页已够，OTel 出口留到需要时再接（S-017 候选）。

## 优先级路线图

| 规格 | 主题 | 为什么排这个位置 | 交付形态 |
| --- | --- | --- | --- |
| **S-005** | 语义评分与工具调用断言 | 现在能验「有没有做」，验不了「做得对不对」；这是评测有效性的核心缺口 | 新 rubric 类型 `semantic` + 内置指标模板 + 参数级工具断言 + 评委可配 |
| S-006 | 评测矩阵视图（多 run × 样本 · 相对判定 · 同题择优 · 可评覆盖率） | 有了语义分才谈得上「改 prompt 会不会退化」的并排比较 | 已实现：矩阵视图 + 相对基线判定 + 同题择优 + 可评覆盖率（置信区间与定期回归留后续规格） |
| S-012 | 评测可读性（失败分类派生 · 测评集最近运行 · 运行可读标签 · 矩阵下钻 · 运行出处） | 结论读不懂就没法用于决策；先让已有数据能被读懂，再谈扩能力 | 已实现：失败分类按证据派生、测评集列表接真实最近运行、运行标签可读、矩阵可下钻到样本、运行出处可见 |
| S-014 | 样本自动合成 + 人工标注回流 + 安全红队 + 多维风险指标 | 样本量和覆盖面是吞吐瓶颈；红队与安全维度是 Agent 上线前的硬门槛 | 从知识库合成用例；标注回流闭环；红队话术模板；安全/毒性/稳健性维度 |
| S-015 | 评测沙箱隔离 + CI 流水线 + 成本报表 | 样本量与并发度上来之后，副作用与额度风险才成为问题 | 隔离工作目录 + GitHub Actions + 成本汇总 |
| S-016 | 任务集 / 环境注册表 | Toolathlon、BFCL 证明长程与工具专项必须靠任务集；也为具身预留抽象 | 环境/任务注册表接口 + 长程工具任务集模板 |
| S-017（候选） | 在线评估与回归监控 + OTel 出口 | 离线跑批解决不了「线上变差」；等有稳定生产流量再做 | 生产 trace 上的评测规则 + OTel 导出 |

## 怎么判断优先级没排错

- S-005 做完若样本判定仍只反映「结构对不对」，说明语义层没真正落地——这是唯一的成功标准。
- S-014 之前样本量若一直上不去（靠手写），S-006 矩阵对比价值有限：矩阵要有行才有意义。
- S-015 的沙箱在样本量与并发度上来之前不急，现在跑的量还伤不到真实用户。
- S-017 依赖真实生产流量；只有离线跑批时做在线评估没有意义。

## star 数据说明

- **2026-11-23 GitHub API 实测**：promptfoo 27,556、deepeval 19,599、ragas 16,403、SWE-bench 6,235、AgentBench 3,830、inspect_ai 3,310、OSWorld 3,277、τ²-bench 2,500、τ-bench 1,515、WebArena 1,646、agentdojo 1,067；具身侧 leRobot 29,038、genesis-world 30,290、openpi 14,736、Isaac-GR00T 8,405、GenSim 363、EmbodiedBench 362、RMBench 233、EmbodiedEval 62。
- **第三方页面自述（2026-11）**：Opik 23.3k、OpenAI Evals 19.7k、Phoenix 12.3k、Evidently AI 7.5k+。
- 其余项目未取到可靠数值，正文不写星数，避免编造。