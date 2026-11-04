# RAGAS 评测报告

- 时间：2026-11-04T19:45:29
- 备注：Local isolated pgvector retrieval with SiliconFlow BAAI/bge-m3
- 样本数：10（采集时报错 0 条）
- 提示词版本：current(2958d613012b), cited(eb92d35317e6)
- 判分模型：deepseek-chat｜embedding：BAAI/bge-m3

## 按提示词版本对比

| 版本 | 指标 | 均值 | 最低 | 最高 | 样本 | 对比基线 |
|---|---|---|---|---|---|---|
| current | answer_relevancy | 0.777 | 0.000 | 1.000 | 5 |  |
| current | context_precision | 1.000 | 1.000 | 1.000 | 5 |  |
| current | faithfulness | 0.950 | 0.750 | 1.000 | 5 |  |
| cited | answer_relevancy | 0.745 | 0.000 | 0.994 | 5 |  |
| cited | context_precision | 1.000 | 1.000 | 1.000 | 5 |  |
| cited | faithfulness | 0.850 | 0.500 | 1.000 | 5 |  |

## 逐条

| 版本 | 用例 | 路由 | 片段 | 耗时 | answer_relevancy | context_precision | faithfulness | 备注 |
|---|---|---|---|---|---|---|---|---|
| current | rag-local-01 | semantic | 1 | 1493ms | 1.000 | 1.000 | 0.750 |  |
| cited | rag-local-01 | semantic | 1 | 952ms | 0.994 | 1.000 | 0.500 |  |
| current | rag-local-02 | semantic | 1 | 1130ms | 0.983 | 1.000 | 1.000 |  |
| cited | rag-local-02 | semantic | 1 | 1027ms | 0.916 | 1.000 | 1.000 |  |
| current | rag-local-03 | semantic | 1 | 1480ms | 1.000 | 1.000 | 1.000 |  |
| cited | rag-local-03 | semantic | 1 | 1357ms | 0.948 | 1.000 | 1.000 |  |
| current | rag-local-04 | semantic | 1 | 1388ms | 0.903 | 1.000 | 1.000 |  |
| cited | rag-local-04 | semantic | 1 | 1295ms | 0.869 | 1.000 | 1.000 |  |
| current | rag-local-05 | semantic | 1 | 1740ms | 0.000 | 1.000 | 1.000 |  |
| cited | rag-local-05 | semantic | 1 | 1438ms | 0.000 | 1.000 | 0.750 |  |

## 最低分样本（看原因）

- **cited/rag-local-01** faithfulness=0.500 — 无原因
- **current/rag-local-01** faithfulness=0.750 — 无原因
- **cited/rag-local-05** faithfulness=0.750 — 无原因
- **current/rag-local-02** faithfulness=1.000 — 无原因
- **cited/rag-local-02** faithfulness=1.000 — 无原因
