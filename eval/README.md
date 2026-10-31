# RAG 自动评测（Ragas）

对应任务清单第 13 条「引入 RAG 测评组件 Ragas 自动化指标评测」。

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
cd C:\workspace\agent\Hotline

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
eval\.venv\Scripts\python.exe eval\score.py --samples "eval\runs\20261031-120000\samples.jsonl"

# 3) 对比基线
eval\.venv\Scripts\python.exe eval\score.py --samples "..." --baseline "eval\runs\<旧目录>\scores.json"
eval\.venv\Scripts\python.exe eval\score.py --samples "..." --set-baseline
```

产物在 `eval/runs/<时间戳>/`：`samples.jsonl`、`meta.json`、`report.md`、`scores.json`。

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
uv run python eval\prompt_checks.py --samples "eval\runs\<时间戳>\samples.jsonl"  # 再查输出
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

## 已知边界（先写清楚，避免误读）

- **只评单轮文件问答**。多轮对话、技能、PPT、深度研究都不在这条链路上。
- **prompt 是复刻的**：`collect.py` 里的 `build_prompt` 与 `agents._fallback` 保持一致；主链路改 prompt 时要同步，否则评的不是线上那套。
- **上下文是字符串**：`_retrieve` 返回的是片段列表，但主链路喂给模型时拼成了一整段。这里按列表评，属于对主链路的"理想化"切片。
- **空答案会被跳过**：没配 Key 时模型静默降级，这类样本只统计检索侧指标。
- **判分有噪声**：同一份答案两次打分可能差 0.05，比较时看均值差是否大于 0.05，别盯着小数点后三位。
