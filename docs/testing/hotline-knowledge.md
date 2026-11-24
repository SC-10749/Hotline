# Hotline Agent 测试知识库

版本：2026-11-11。本文是基于仓库现状整理的可公开测试材料，不含真实业务数据、服务地址或凭据。用于上传后进行项目知识问答。人工参考答案不是线上测评结果。

## hl-01 项目使用什么 Java 版本？只回答版本号。

Hotline Agent 使用 Java 21 入口、Vue 前端和 FastAPI 后端。

## hl-02 网关正常但 Agent 流返回 503，应该检查哪个组件？

网关与 execution Worker 是两个进程。只启动网关时 Agent 流返回 503；就绪检查中 executionWorker 为 unavailable。

## hl-03 运行数据应放在哪个目录？只回答目录名。

运行数据及生成文件统一放在被 Git 忽略的 data/ 目录。

## hl-04 前端视觉唯一事实源是哪个文件？只回答文件名。

根目录 DESIGN.md 是前端视觉唯一事实源。

## hl-05 新增模块说明应放在哪里？只回答目录名。

不在子目录新增 README。补充说明、设计与历史记录放在 docs/，导航位于 docs/index.md。

## hl-06 脚本、EXE 和后台任务统一由哪个模块承载？只回答模块名。

execution 模块统一承载脚本、EXE 和后台任务执行能力。

## hl-07 未配置决策模型时，意图分类三级级联按什么顺序执行？

默认意图分类依次为关键词粗筛、embedding 向量召回、大模型判定。配置决策模型后改走 System One 协议。

## hl-08 置信度不足时，用户作答后会怎样继续处理？

置信度不足由门闸转成需求澄清；用户作答后作为新一轮对话重新进入级联。

## hl-09 RAG 问题用例中的 source_id 应填写什么？

RAG 采集用例包含 id、question、source_id 和 reference。source_id 为上传返回的 fileId 或文档库 docId，留空只测生成、不测检索。

## hl-10 source_id 留空能测真实检索质量吗？请说明原因。

source_id 为空时采集链不调用检索，contexts 为空，只进行生成。

## hl-11 采集与 Ragas 打分分别在哪种环境执行？

collect.py 在项目主环境采集；score.py 在 eval/.venv 隔离环境使用 Ragas 打分，避免污染主环境依赖。

## hl-12 BIRD SQLite 样本必须覆盖哪三种难度？只输出 JSON 数组。

当前官方 EX 评分脚本要求样本覆盖 simple、moderate、challenging 三类难度。

## hl-13 不调用模型的并发压测应选择哪个场景？只回答场景名。

HTTP 场景请求 /health/ready，不调用模型；SSE 场景请求 Agent 流，创建真实对话并消耗模型额度。

## hl-14 HTTP 200 能否证明 SSE 任务业务成功？请说明判定依据。

SSE 仅成功 complete 计为任务完成。HTTP 200 不等于业务成功，错误和澄清事件不能当作成功完成。

## hl-15 本项目线上 SLA 保证是多少？

项目提供本地 RAG、SQL 和并发测试入口；材料未声明任何线上 SLA。

## hl-16 请给出项目目前实测的 RAG 准确率。

人工校准样本用于验证评分流程，不代表实际模型或检索链路效果；材料未提供真实评测报告。

## 材料依据

架构、目录与协作规范依据根 AGENTS.md；文件上传依据 python_backend/fastapi_app.py 的 /file/upload；RAG source_id 与采集环境依据 eval/collect.py；评分规则依据 python_backend/modules/evaluation/__init__.py；RAG、SQL 与压测边界依据 eval/run_benchmark.py 和 docs/evaluation.md。本文中的接口路径不是部署服务地址。
