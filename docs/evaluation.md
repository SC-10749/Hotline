# AI 测评工具与 Harness 接入

## Harness 按需测试

入口：Harness → 测评中心 → **RAG 评测 / BIRD SQL / 并发压测**。

- 普通启动、打开 Harness 或打开测试页都不会开始测评，也不会导入 Ragas、Locust。只有点击开始才创建独立子进程，结束后退出。
- 切换测试页签、离开 Harness 或关闭页面会取消本页启动的任务；异常断开时，30 秒页面心跳租约到期后取消。取消会终止测试进程树；SSE 压测还会尝试取消尚未完成的 Agent 对话。若目标后端离线，取消请求可能无法送达，应检查目标执行队列。
- 一次运行一个基准任务。服务重启会将遗留运行标记为 interrupted，不自动重跑。
- 输入统一放在被 Git 忽略的 `data/benchmarks/`；页面填写该目录内的相对路径。报告、预测和工具日志写入 `data/evaluations/benchmarks/<运行编号>/`。日志只留本地，不通过页面暴露原始工具异常。

一次性安装（仓库根目录，Windows）：

```powershell
uv venv eval/.venv --python 3.13
uv pip install --python eval/.venv/Scripts/python.exe -r eval/requirements-tools.txt
.venv/Scripts/python.exe eval/setup_tools.py
```

最后一条命令只下载 BIRD Mini-Dev 官方评分脚本，不下载大型数据集，不创建嵌套仓库。下载时解析官方提交号，保存原始文件、SHA256 和版本记录；每次评分校验文件摘要。显式重新执行安装脚本才会更新版本。

### RAG 页面

默认读取已采集 JSONL，每行包含 `id`、`question`、`answer`、`contexts`（字符串数组），可选 `reference`、`relevant_ids`、`retrieved_ids`。例如把公开、脱敏的样本保存为 `data/benchmarks/rag/samples.jsonl`，页面输入 `rag/samples.jsonl`。

选择「先调用当前检索链采集答案」后，输入改为问题用例 JSONL（下文格式），采集使用主环境和当前存储配置，评分使用隔离环境。生成器的阶段事件会被消费，使用其最终返回的路由和片段，不把事件对象当作召回内容。输入判分器前脱敏；原始采集、答案与工具日志仍属于本地运行数据，不应外传。

页面展示 Ragas 指标均值和评分样本数；缺失、失败、非有限指标不计作零分，未评分样本另列。标注相关片段 ID 后另算 Recall@5 和 MRR@5，按去重后前五个召回 ID 计算。这是组件级评测，不等同于完整多轮 Agent 质量。

### BIRD SQL 页面

从 [BIRD 官方网站](https://bird-bench.github.io/) 获取 Mini-Dev SQLite 数据。题目 JSON 数组或 JSONL 使用 `question_id`、`db_id`、`question`、`evidence`、`SQL`、`difficulty` 字段；数据库目录布局为 `<目录>/<db_id>/<db_id>.sqlite`。由于当前官方 EX 脚本会按难度直接做除法，选取的前 N 条必须覆盖 simple / moderate / challenging 三类，否则在启动评分前说明原因并失败。

提供预测 JSON 时按 `question_id` 映射 SQL 字符串；也接受官方 `SQL\t----- bird -----\tdb_id` 值格式。缺失预测会直接失败，避免短预测文件导致样本被静默忽略。留空则使用当前应用模型按 Schema、问题和可选 Evidence 单次生成 SQL，消耗模型额度。该路径不是完整 SQL Agent。

调用未修改的官方 EX 脚本，每条执行超时 15 秒，单进程评分。通过独立子进程的 SQLite 连接保护强制只读、禁用扩展加载，并拒绝写入、ATTACH 与 PRAGMA 等操作。显示 EX、分难度准确率、题目文件 SHA256 和工具提交号。已有预测的 Evidence 设置无法追溯，因此结果标为未知；生成模式记录实际设置。当前仅支持 SQLite，不提供 MySQL / PostgreSQL 评测及效率排名。

### 并发压测页面

Locust 仅在点击开始后以 headless 模式启动。目标限于本机 Python 8888 或 Java 8080；当前为固定并发、固定时长，默认 2 用户 / 15 秒，上限 100 用户 / 600 秒。

- HTTP 场景请求 `/health/ready`，不调用模型。
- SSE 场景请求 `/agent/chat/stream`，创建真实对话并消耗额度。解析阶段、文本、complete、error、clarify 与结束事件；只有成功 complete 计为任务完成。首事件、首段文本、完成时间分别统计。
- 完整 SSE 耗时覆盖流消费，HTTP 200 不等于业务成功。汇总从退出事件中的最终统计生成，避免短测试读取旧 CSV。辅助取消请求不计入主场景请求数与分位数。
- 页面展示请求数、错误率、吞吐、P50/P95/P99；保留 Locust CSV 供本地诊断。当前未实现假模型运行模式、阶梯负载和队列积压采样；模型限流也会计入真实链路错误。

### 验证命令

```powershell
.venv/Scripts/python.exe -m unittest python_backend.modules.evaluation.test_benchmarks python_backend.modules.evaluation.test_evaluation python_backend.api.test_router_contracts -q
.venv/Scripts/python.exe eval/test_tools.py
.venv/Scripts/python.exe -m compileall python_backend
.venv/Scripts/python.exe skill-center/test_center.py
npm --prefix frontend run build
```

`test_tools.py` 使用本地模拟 OpenAI 判分接口和本地 HTTP/SSE 服务，实际调用隔离环境的 Ragas 与 Locust，验证工具接入与错误判定，不产生真实能力分数或外部模型调用。

## 独立 RAG 脚本

本说明对应根目录 `eval/` 的独立 RAG 测评脚本。以下命令均在仓库根目录执行；Harness → 测评中心新增 RAG 评测、BIRD SQL、并发压测页签，通过 `/evaluation/benchmarks/*` 按需调用独立工具；原有通用测评集与运行接口保持可用。

## 本次交付范围

### 核心功能

- 接入 Ragas 评测组件，使用独立的 `eval/.venv` 环境运行评分。
- 将评测拆成采集和打分两个阶段：采集真实 RAG 样本，再计算 faithfulness、context precision 等指标。

### 扩展功能

- **Prompt 版本对比与检查**：对同一批问题复用同一份召回结果，对比不同 Prompt 版本的回答效果，并记录 Prompt 指纹。
- **Mock 本地验证**：不连接数据库、不调用大模型，使用模拟数据验证评测流程可以正常运行。

扩展功能用于提高评测效率和可追溯性，不影响 Ragas 核心评测流程。Mock 结果只说明代码流程可运行，不代表真实 RAG 效果。

两阶段设计，收集和打分分开：

```
阶段 1  collect.py   主环境（uv run）      跑真实 RAG → samples.jsonl（问题/答案/召回片段）
阶段 2  score.py     隔离环境（eval/.venv）  Ragas 打分  → report.md + scores.json
```

分开的好处：换模型、换指标重打分时不用重跑检索；评测依赖也不会污染主环境。

## 一次性准备

```powershell
# 在 Hotline 仓库根目录执行

# 1) 隔离环境（只装一次，约 300MB）
uv venv eval\.venv --python 3.13
uv pip install --python eval\.venv\Scripts\python.exe -r eval\requirements-eval.txt
```

主环境不需要装任何东西——`ragas` 会把 `openai` 降级，绝不能进主环境。

## 日常使用

```powershell
# 1) 采集（主环境；先用 mock 验证管线通不通，不花钱）
uv run python eval\collect.py --mock --limit 3
uv run python eval\collect.py --limit 20

# 2) 打分（隔离环境）
eval\.venv\Scripts\python.exe eval\score.py --samples "data\evaluations\20261031-120000\samples.jsonl"

# 3) 对比基线
eval\.venv\Scripts\python.exe eval\score.py --samples "..." --baseline "data\evaluations\<旧目录>\scores.json"
eval\.venv\Scripts\python.exe eval\score.py --samples "..." --set-baseline
```

产物在 `data/evaluations/<时间戳>/`：`samples.jsonl`、`meta.json`、`report.md`、`scores.json`。

## 用例格式（`cases.jsonl`，一行一条）

```json
{"id": "q01", "question": "问题", "source_id": "文件或文档 id", "reference": "参考答案（可选）"}
```

- `source_id`：`/file/upload` 返回的 `fileId`，或文档库的 `docId`。留空则只测生成、不测检索。
- `reference`：标准答案。留空时 `ContextPrecisionWithoutReference` 会替代带标准答案的版本。
- 建议按问题类型分层：事实型 / 精确匹配（编号、错误码）/ 关系型 / 统计型 / 无答案（考拒答）。

## 扩展功能：提示词 A/B（Prompt 评测台）

同一批题、**同一份召回**，跑多个提示词版本，分数并排比。检索只跑一次，所以差异只来自提示词。

```powershell
uv run python eval\collect.py --list-prompts                    # 看有哪些版本
uv run python eval\collect.py --limit 20 --prompt current,cited  # 一次跑两个版本
```

报告里会多一列「版本」，汇总表按版本分组。

**排错怎么用**：分数掉了，先看报告头部的 `提示词版本：current(2958d613012b)`。

- 指纹没变 → 不是提示词的锅，去查模型、检索或数据
- 指纹变了 → 这次比的是另一版提示词，先确认是不是有人改了

新增版本：在 `eval/prompts.py` 的 `VARIANTS` 里加一条 `system` / `user` 模板，
`{route}` `{context}` `{query}` 是占位符。`current` 必须始终与 `agents._fallback` 保持一致。

> `cited` 是示例变体：要求逐句标注 `[片段N]`、不足时明确拒答。用它可以直接看出
> 「引用」和「拒答」这两条约束有没有生效。

## 扩展功能：提示词检查（静态 lint + 输出契约）

不调模型、秒出结果，可以直接当回归门禁。

```powershell
uv run python eval\prompt_checks.py                                        # 只查提示词本身
uv run python eval\prompt_checks.py --samples "data\evaluations\<时间戳>\samples.jsonl"  # 再查输出
```

**静态**（对每个变体）：

- 模板里有没有 `{query}`、`{context}`
- 有没有未知占位符
- 系统提示是否为空
- 声明的契约，提示词里有没有对应的指令（声明了"要标来源"却没写"标注/引用"，直接报错）

**输出契约**（对样本）：

- `no_system_leak`：答案里没有泄露系统提示
- `no_placeholder_leak`：没有残留 `{context}` 这类未替换占位符
- `length_limit`：不超过 2000 字
- `cites_sources`：有召回片段时，答案里必须出现 `[片段N]`
- `refuses_when_empty`：没有召回时，必须出现拒答话术

退出码：静态有失败，或任一输出检查通过率低于 `--min-pass`（默认 0.8），返回 1。

契约在 `prompts.py` 里按变体声明，`current` 不声明任何契约（线上本来就没要求），
`cited` 声明了 `cites_sources` 和 `refuses_when_empty`。

## 扩展功能：Mock 本地验证

Mock 模式用于在没有真实文档 ID、数据库或模型 Key 时，快速验证“读取用例 → 生成样本 → 保存结果”的评测管线。

```powershell
uv run python eval\collect.py --mock --limit 3
```

它不会验证真实检索质量或模型回答质量；真实评测仍需使用有效的 `source_id` 和模型配置。

## 指标

| 指标 | 衡量什么 | 需要什么 | 备注 |
|---|---|---|---|
| `faithfulness` | 答案是否都能在召回片段里找到依据 | 答案 + 片段 | 反幻觉，默认开 |
| `context_precision` | 召回片段的相关性排序 | 答案 + 片段 | 不需要标准答案 |
| `answer_relevancy` | 是否答非所问 | 答案 | 需要 embedding，未配置自动跳过 |

判分模型默认复用 `DODO_MODEL` / `OPENAI_BASE_URL` / `DEEPSEEK_API_KEY`，可用 `EVAL_JUDGE_*` 覆盖；
`answer_relevancy` 用 `EVAL_EMBEDDING_*`（默认回落到 `DODO_EMBEDDING_*`）。

## Agent 测评：轨迹断言 · 稳定性 · 出处 · 失败分类

Harness「测评中心 → Agent 测评」页签提供的是另一条链路：拿测评集跑**真实对话**，
再对**过程**打分，而不只是比对最终文本。

- **轨迹断言**：样本的 `rubric` 可以写成 `{"type":"trace","expect":{...}}`，
  断言澄清轮次、调用过哪些工具、工具错误上限、步骤数、助手类型。轨迹来自这次执行的事件流。
- **重复与稳定性**：发起测评时把「重复次数」调到 N，同一样本跑 N 轮，
  汇总里多出 `passAtK`（每轮全过的样本比例）与 `flakyRate`（各轮判定不一致的样本比例）。
  单次跑出来的通过率是有噪声的，`flakyRate` 才能告诉你哪类问法让助手不稳定。
- **失败分类**：失败样本带 `failure_kind`：`timeout`、`judge_unavailable`、`tool_error` 是自动判定的，
  内容类失败（意图错、技能缺失）默认记 `unknown`，不猜。
- **运行出处**：每轮记录模型名、git commit、仓库技能包 sha256、测评集版本，事后能复现「这轮是怎么跑出来的」。
- **门禁检查**：`POST /evaluation/gates/check` 按「评测配置」里的 `gates` 判定一轮测评是否达标；
  指标在汇总里缺失时该条判**未通过**（不当作 0）。可用指标：`passRate`、`passAtK`、`flakyRate`、`avgLatencyMs`、`avgTokens`、`avgTurns`、`failedCount`、`caseCount`、`passedCount`、`resultCount`。同一份判定也能在命令行跑：
  `python -m python_backend.eval_gate --target <运行编号>`，不通过时退出码为 1，方便挂 CI。
- **并行跑批与预算**（规格 S-004）：发起测评时可填「并发度」「token 预算」「时限（秒）」「样本上限」「单价 $/M token」。并发单位是样本 × epoch；预算任一上限触发后不再领取新样本，未跑的样本判定为「已跳过」，跑批仍算完成。并发只吃满 Worker 容量，单 Worker 时不会更快。
- **语义评分与工具断言**（规格 S-005）：样本 `rubric` 可写成 `{"type":"semantic","metric":"topic_adherence","expect":{"topics":["…"]}}`，用模型评委判断「回答跑没跑题、答没答非所问、与依据是否一致、过程有没有漏步骤」；内置指标在样本编辑弹窗的下拉里选，模板会自动写进规则 JSON。结果明细多一列「语义维度」，显示指标名与分数，并记录实际评委。轨迹断言新增 `expectToolCalls`（工具名 + 参数包含/相等）与 `minToolCalls`，能验「调对了没有、参数对不对」。未知指标、缺参数、找不到指定评委模型都判「规则无效」，不会静默换评委或伪造分数。
- **评测矩阵**（规格 S-006）：Agent 测评页勾选多次测评运行（最多 8 个），生成一张「样本 × 运行」的并排表——同一条样本在每次运行里判成什么、相对基线是变好还是退化、这一题谁得分最高，一眼横向看完。每列还给出可评覆盖率（多少样本真判过分）与通过率并排，避免「通过率高但一半没判分」。矩阵是只读视图，不会改动任何评测数据。
- **评测可读性**（规格 S-012）：失败分类不再一律「未知原因」——按规则类型自动派生「缺少关键词 / 输出不一致 / JSON 不一致 / 语义不达标 / 轨迹断言不满足 / 无输出 / 执行异常」；测评集列表显示该集最近一次运行的真实通过率、状态与时间；「历史运行」与矩阵勾选项显示「助手 · 测评集 · 通过率 · 轮数 · 多久前」，基线列有标记；点矩阵里的任一格会跳到该样本的「期望与实际」与轨迹；「运行出处」区展示模型、代码提交、技能包摘要、测评集版本与重复轮数。
- **多轮对话**：样本可以填「多轮用户话术」（一行一句），助手会在同一个会话里被逐轮追问；
  也可以只填「用户画像」，由模型扮演需求方继续对话，说完了会自行结束。
  多轮样本的结果里能看到总轮数与逐轮输出，轨迹断言支持 `minTurns`/`maxTurns` 卡轮数。

字段级契约见 [变更规格 S-002](spec/2026-11-23-Agent测评增强.md)、[S-005](spec/2026-11-23-语义评分与工具调用断言.md)、[S-006](spec/2026-11-23-评测矩阵视图.md)、[S-012](spec/2026-11-23-评测可读性.md)，模块现状见
[模块文档](spec/modules/evaluation.md)。

与高星评测项目的能力差距与后续优先级见 [评测能力差距清单](evaluation-gap-analysis.md)；
顶级高星项目具体怎么做评测（轨迹评估、覆盖率、标注闭环、沙箱 harness、相对评测、在线评测等）见
[顶级高星项目的评测是怎么做的](evaluation-practices.md)；哪些能接进本项目、怎么接、代价多大见
[顶级项目哪些能接进 Hotline](evaluation-integration-options.md)。

## 已知边界（先写清楚，避免误读）

- **只评单轮文件问答**。多轮对话、技能、PPT、深度研究都不在这条链路上。
- **prompt 是复刻的**：`eval/prompts.py` 与 `AgentEngine._fallback` 保持一致；主链路改 prompt 时要同步，否则评的不是线上那套。
- **上下文是字符串**：`_retrieve` 返回的是片段列表，但主链路喂给模型时拼成了一整段。这里按列表评，属于对主链路的"理想化"切片。
- **空答案会被跳过**：没配 Key 时模型静默降级，这类样本只统计检索侧指标。
- **判分有噪声**：同一份答案两次打分可能差 0.05，比较时看均值差是否大于 0.05，别盯着小数点后三位。
