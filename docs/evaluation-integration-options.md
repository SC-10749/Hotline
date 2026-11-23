# 顶级项目哪些能接进 Hotline（接入评估）

> 更新日期：2026-11-23
> 前提：现有规格 S-002 / S-003 把「不引入外部评测框架」写成非目标。真要接入外部项目，必须**新开规格**并修订这条口径，不能在旧规格下偷渡。
> 依据：[顶级高星项目的评测是怎么做的](evaluation-practices.md)、[评测能力差距清单](evaluation-gap-analysis.md)

## 结论

| 建议 | 项目 | 接入边界 | 为什么 |
| --- | --- | --- | --- |
| **接** | Ragas（已在用） | 数据边界：把产物并进同一份运行报告 | 零新依赖，解决「检索指标与 Agent 报告分离」 |
| **接** | OpenTelemetry（标准件） | 数据边界：execution 事件流导出 span | vendor-neutral，先有出口再谈平台；一次接入，任意后端可用 |
| **接（可选）** | promptfoo | 进程边界：外部 CLI 打我们的 HTTP 接口 | 借它最全的红队插件与断言库，主进程零侵入 |
| 先不接 | Phoenix / Opik / Langfuse 本体 | 服务边界 | 我们已有自建控制台；等 OTel 出口就绪再说，且它们是重服务 |
| 不接 | Inspect AI / deepeval | 库边界 | 与我们自建评分层重叠、侵入深，收益不抵成本 |
| 不接 | SWE-bench / lm-evaluation-harness | — | 评的不是我们的产品（裸模型 / 真实仓库 patch） |
| 先不接 | DSPy | 库边界 | metric+optimizer 闭环很漂亮，但要先有训练集与可优化的提示词模板，工作量最大 |
| 抄不接 | Toolathlon / BFCL / agentdojo / promptfoo 红队插件 | 资产边界 | 抄任务集、话术、判定逻辑，不引它们的运行时 |

## 四种接入边界（决定了代价与风险）

| 边界 | 形态 | 代价 | 风险 |
| --- | --- | --- | --- |
| A 库边界 | 装进我们的 Python 进程 | 依赖体积、版本冲突、模型客户端重复 | 我们的评分层被外部约定绑架 |
| B 进程边界 | 外部 CLI 调我们的 HTTP 接口 | 多一个运行时（Node）、配置双份 | 主进程零侵入，失败不影响主链路 |
| C 数据边界 | 独立服务消费我们的导出数据 | 需要 collector / 服务、运维 | 平台绑定；但可先用标准格式解耦 |
| D 资产边界 | 抄任务集、话术、判定逻辑 | 无依赖 | 许可证与出处要记录（参考 `skills/resume-writing/PROVENANCE.md` 的做法） |

## 逐个评估

### Ragas —— 接（已在 eval/.venv，零新依赖）

- **现状**：`eval/collect.py` + `eval/score.py` 产 `scores.json`，报告与 Agent 测评报告**分离**。
- **接入方式（最小）**：Agent 测评运行时可选带一个 `ragReportPath`，把该报告的关键指标并入运行 summary（faithfulness / context_precision / answer_relevancy），并在 summary 里标注**切片口径与主链的差异**（我们自己文档里承认那是「理想化切片」）。
- **代价**：几乎为零，环境已隔离在 `eval/.venv`，主环境不装 ragas。
- **解决**：差距清单第 25 条（检索指标与 Agent 报告并表）。

### OpenTelemetry —— 接（标准件，先做出口）

- **为什么先做它而不是先选平台**：OTel GenAI 语义约定把 chat call / tool execution / agent invocation 统一成 span 与 `gen_ai.*` 属性，**任何后端都能消费**；先做出口，将来换 Phoenix / Opik / Langfuse / Datadog 都不用改我们的代码。
- **我们的映射关系（现成）**：execution 事件流 → span：

  | 我们的事件 | OTel span |
  | --- | --- |
  | 一次执行 | `invoke_agent` |
  | `thinking` / `text` | `gen_ai.chat`（模型调用） |
  | `tool_start` / `tool_end` | `execute_tool` |
  | `usage` | `gen_ai.usage` 属性（token 数） |

- **代价**：主环境新增 `opentelemetry-sdk`（体积不大）；需要决定导出时机（worker 落事件时推，还是独立导出器读 `execution_event` 表）。
- **注意**：GenAI 语义约定截至 2026-10 仍是 Development 稳定性，**属性名要留版本余量**（集中在一个映射文件里，别散落在业务代码）。
- **解决**：差距清单第 15 条，并为 S-010 铺路。

### promptfoo —— 接（进程边界，可选）

- **它能补什么**：红队插件库（prompt-injection / PII / 越权 / SSRF / 越狱 × 多种策略）与分层断言（确定性 / 结构 / 语义相似度 / 模型判分 / 延迟 / 成本），是当前生态里最全的。
- **接入方式**：它作为外部 CLI 跑我们的产品——`providers` 用自定义 HTTP provider 指向本机 `http://127.0.0.1:8888/agent/chat/stream`，`tests` 写断言，`redteam` 写插件与策略；产物是它自己的报告与 JSON。
- **代价**：需要 Node 运行时（用 `npx` 跑，不进 `frontend/package.json`，保持前端依赖不变）；我们的 SSE 流要写 `transformResponse` 解析——**这一点需先验证 promptfoo 的 HTTP provider 能否稳定吃 SSE**。
- **红线**：红队用例会真的调我们的模型与工具，**必须配合 S-004 的预算护栏**（token 预算 + 样本上限 + 时限），并只跑回环地址。
- **解决**：差距清单第 5 条（红队）与第 6 条（多维风险指标）的一半；另一半（安全/毒性/稳健性维度）仍要靠 S-005 的语义指标。

### Phoenix / Opik / Langfuse —— 先不接

- 它们的价值在「trace 一等公民 + 在线评测 + 现成 judge 模板」。
- 但我们已有自建控制台与轨迹回放，直接上平台=双份 UI + 一套额外服务（Docker / K8s / 托管账号）。
- **正确顺序**：先把 OTel 出口做出来（S-010 的前半段），平台选择变成可选项；真需要在线评测时再接，那时我们的 trace 数据已经就位。

### Inspect AI / deepeval —— 不接

- Inspect AI 是完整框架（task/solver/scorer/sandbox/log viewer），接它等于**替换**我们的 evaluation 模块，S-002/S-003/S-004 的成果全部作废。
- deepeval 的指标库确实诱人，但它自带 LLM/embedding 客户端与 dashboard 概念，和我们已有的 `model` rubric + S-005 语义模板重复；**把它的指标实现成我们的语义模板更快、更可控**。

### SWE-bench / lm-evaluation-harness —— 不接

- SWE-bench 评的是「Agent 能不能改仓库让测试通过」，需要真实 GitHub 仓库 + 容器 + 打 patch；我们不产 patch。
- lm-evaluation-harness 评的是裸模型在学术任务上的表现，和「评我们自己的 Agent」不是一件事。
- 这两个的**理念**（任务集冻结 + 官方判定脚本 + 结果快照 + 基线 diff）值得抄，已经写进 S-009。

### DSPy —— 先不接

- metric + optimizer 的闭环是本轮看到的最优雅做法：用评测指标自动优化提示词。
- 但前提是：**有训练集**（我们没有）、**提示词是可优化的模板**（我们的提示词写在 Python 代码里，要先抽成模板文件）、**指标可微/可优化**（我们的语义指标是 0-1 分数，可以，但噪声会传导到优化循环）。
- 建议：等 S-005（语义指标）与 S-007（样本来源）落地后再评估，否则优化器没有可信的信号。

### Toolathlon / BFCL / agentdojo / promptfoo 红队插件 —— 抄不接

- **Toolathlon**：108 个长程任务、32 个真实应用、604 个工具（多为 MCP），每任务独立容器。任务集本身是宝贵资产，但依赖其 Docker 环境与多个真实应用，本机跑不动 → 抄它的**任务形态**（模糊指令、约 20 轮工具调用、确定性判定脚本）作为 S-009 的模板。
- **BFCL**：AST 判定函数调用正确性的逻辑可以抄（我们 S-005 的参数级断言本质相同）。
- **agentdojo / promptfoo 红队**：话术与插件清单可抄成我们的红队样本模板（S-007）。
- 抄的时候记录出处与许可证，别把别人的任务集当成自己的资产。

## 推荐执行顺序

1. **先做零依赖的**：Ragas 报告并表（补差距 25）。
2. **再做标准件的**：OTel 出口（补差距 15，为 S-010 铺路）。
3. **最后考虑外部执行器**：promptfoo 红队（补差距 5），必须配预算护栏。
4. **不碰的**：Inspect AI / deepeval / SWE-bench / lm-eval-harness。

每一步都要新开规格（S-006 起），并同步修订 S-002 / S-003 里「不引入外部评测框架」的口径——允许**边界外的接入**（CLI / 导出 / 资产），仍然禁止把外部框架嵌进我们的评分层。