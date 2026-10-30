# RAG 自动评测（Ragas）

对应任务清单第 13 条「引入 RAG 测评组件 Ragas 自动化指标评测」。

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
