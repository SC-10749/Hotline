# Hotline 项目测试数据使用

本包依据当前仓库人工整理，适合实际执行测试；不是生产用户数据或已经测得的模型表现。知识原文为 [Hotline 测试知识库](hotline-knowledge.md)，题目和参考答案位于 `eval/project_cases.json`。

## 通用测评中心

在仓库根目录运行：

```powershell
.venv/Scripts/python.exe eval/seed_project_data.py
```

刷新 Harness → 测评中心，选择 **Hotline 项目知识与拒答 v1（自带上下文）**。共 16 题，覆盖架构、Worker 排障、目录规范、意图级联、RAG 输入、SQL 难度、SSE 成功判定和两条无答案拒答。每题自带上下文，可直接使用 chat Agent 开始测评，不要求模型访问源码或知识库。运行 Agent 仍需网关、Worker 和模型配置。

评分使用现有 equals、contains、json_equals 规则，不额外调用判分模型。精确输出题要求只输出指定格式；关键词题只做粗粒度冒烟检查，不能据此证明语义完全正确。重复安装保留已有测评集及用户编辑；不清空历史运行。删除该测评集后重新安装可恢复初始题目。

默认写入 `data/evaluation.db`。若服务配置了其他 `DODO_DATA_DIR`，通过 `--data-dir` 指定同一个本地目录。运行文件位于该目录的 `benchmarks/hotline/`。

## 真实 RAG 测试

1. 通过项目文件上传功能上传 `docs/testing/hotline-knowledge.md`，获得 `fileId`；也可使用文档库返回的 `docId`。
2. 将实际 ID 绑定到问题文件：

```powershell
.venv/Scripts/python.exe eval/seed_project_data.py --source-id <实际fileId或docId>
```

3. 在测评中心 → RAG 评测填写 `hotline/questions.jsonl`，勾选「先调用当前检索链采集答案」，样本上限填 16，开始运行。

绑定 ID 后直接重复安装不会清除绑定。重新上传文档后需重新绑定。未绑定 ID 的问题文件只能测生成，不构成真实检索测试。交付时已在本机运行的后端上传并绑定；换环境时须重新上传。

文档较短，默认文件上传阈值下可能不触发向量分块；此时适合验证文件读取、上下文问答和拒答。若要专门验证 embedding 召回或片段排序，需要确认文档已完成向量索引。当前问题文件未提供相关片段 ID 标注，因此不会产生 Recall@5 / MRR@5；Ragas 指标仍可评估答案与实际召回上下文。

## 评分器校准

RAG 页面输入 `hotline/calibration.jsonl`，**不勾选采集**，样本上限填 17。它包含 14 条人工正确答案与 3 条故意错误答案，用来检查评分器能否区分有据回答与幻觉。没有伪造实际采集结果；所有行都带人工来源标记。该分数不能用作系统效果报告。Ragas 打分会使用所配置的判分模型及额度。

## 本地验证

```powershell
.venv/Scripts/python.exe eval/test_project_data.py
```

此检查验证数据格式、参考答案与评分规则、重复安装和文档 ID 保留，不调用模型。
