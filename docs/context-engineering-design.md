# Hotline 上下文工程实现与验收

本文记录当前代码路径、边界和验证方式。根 README 提供启动和配置入口，本文展开链路实现与验收口径。

## 请求链路

主聊天与 Harness 将会话、工作区、模式和可选文档标识传给执行入口。主聊天沿用 `/agent/*/stream`，Harness 使用 `POST /execution/runs`，两者经过执行应用服务进入同一队列和 Worker。

Worker 将 workspace_id 传到 AgentEngineRuntime 和 AgentEngine。普通回答、文件问答、深度回答、PPT 规划和技能分支使用同一上下文服务。技能分支同时召回工作区及所选文档证据。适用请求先经过意图级联，用户作答后的澄清请求重新分类。

入口实现位于 `frontend/src/api.js`、`python_backend/api/routers/execution.py`、`python_backend/application/execution_service.py`、`python_backend/runtime/agent_runtime.py` 和 `python_backend/agents.py`。

## 工作区与私密文件边界

浏览器目录通过 `POST /harness/workspaces/import` 导入。服务端检查路径、重复文件和大小后，在新的临时目录写入文件，目录就绪后创建资源记录，失败时清理本次新建目录。相对目录结构和根 AGENTS.md 得到保留。每次导入最多 5000 个文件，单文件 50 MB，总量 512 MB。

主聊天从后端加载工作区列表，持久化名称与标识。选择不同工作区为已有对话建立新会话，历史详情返回原 workspaceId。会话已有范围绑定由 MemoryStore 继续检查，活动运行的幂等判断包含工作区与 Agent 标识。

客户端目录收集、导入服务、索引扫描、向量生成、检索和原文读取共同执行文件级过滤。环境配置及备份、local/private 文件、private/secrets 目录、常见密钥文件、依赖和运行数据目录被排除。WorkspaceIndex 打开时清理旧索引中的私密来源，并为旧表补齐分层字段。

内容脱敏覆盖模型、embedding 和 OpenViking 出站请求。原始证据留在本地，检索内容作为带来源的数据参与模型输入。单用户部署以工作区为跨会话共享范围，独立会话使用各自范围。真实多租户身份与授权需结合部署环境实现。

## 状态、摘要与原文

`data/context-memory.db` 保存原始交互、工具结果、FTS 历史索引、任务状态、阶段摘要、分段 checkpoint、撤销记录和持久化 outbox。

任务事实包含 key、quote、sourceId 与 status。自动抽取只接受当前用户原话中的引用，同一 key 更新有效状态，revision 保护并发修改。对话轮次结束与业务任务完成分别表达。

历史超过最近 4 轮后生成累计摘要。每次 checkpoint 另保存本次覆盖区间的摘录与起止消息 ID，后续可按主题检索，并使用 `checkpoint:消息ID` 读取来源。累计摘要调用失败时使用有来源的限额摘录。

已完成交互与投递任务在同一事务写入，工具结果完整归档后进入有界模型上下文。过期的工具交互以完整调用周期压缩，保留工具调用 ID 的关联。

实现位于 `modules/memory/store.py`、`modules/context_engineering/service.py` 与 `modules/execution/langchain_agent.py`。

## 上下文装配与预算

系统提示、工作区规则、任务状态和当前问题构成受保护输入。近期完整问答预留剩余额度的三分之一，检索证据、待投递交互、累计摘要、相关 checkpoint、历史召回和远端记忆按优先级加入。

默认窗口配置 128000、输入预算 64000、输出预留 8192、安全余量 2048。实际输入上限取输入预算与窗口减预留的较小值。估算采用 UTF-8 字节上界，工具定义与消息结构参与检查，实际用量以 provider usage 为准。

必需输入超限返回明确错误。证据段按分配裁剪或省略，manifest 记录来源、裁剪状态、历史范围、任务版本、记忆状态及已加载层级。调用前快照和执行事件保留对应预览，供运行详情页查看。

## 工作区检索与 L0/L1/L2

工作区文件维护 FTS5 trigram、中文 bigram 与文件向量索引。文件时间戳和大小作为增量版本，删除文件同步移除。向量生成每次默认处理 40 个变更文件，分批填充。工作区使用过的文档作为成员进入同一检索范围，语义候选独立于本轮词面命中。语义阈值和真实 embedding 评测沿用根 README 中的配置。

每个来源保存三个读取层级。

| 层级 | 内容 | 使用方式 |
| --- | --- | --- |
| L0 | 256 字符以内的抽取式摘要 | 快速定位来源 |
| L1 | 章节数量、代表片段及分块来源 ID | 规划正文读取范围 |
| L2 | 原始分块正文和版本标记 | 按字符分页读取 |

L1 最多均匀选取 16 个分块作为概览，保留覆盖数量。全局问题附目录计数、代表摘要、来源总数和实际展示数量。目录与来源清单受展示额度限制时明确记录部分覆盖，回答应据此说明依据范围。

技能工具 `read_context_source` 接受 `workspace:file:相对路径` 和 `workspace:doc:文档ID`，支持 abstract、overview、detail。读取使用会话绑定的工作区标识。`search_memory` 同时支持工作区证据补查。

融合使用 RRF，词面相关性用于同分排序。文件语义召回依据归一化余弦相似度。实现位于 `modules/retrieval/workspace_index.py`、`layers.py`、`fusion.py` 与 `modules/workspaces/context.py`。

## 有界多跳补充检索

深度模式以及关联、依赖、根因、对比、跨文档和多跳问题可在首轮证据后进入补充规划。规划只接收限额证据预览，每轮最多两个查询和两个已有来源的分页读取，最多两轮。

终止条件包括证据覆盖充分、查询重复或没有新证据、输入额度不足、任务取消，以及达到轮数上限。来源读取限制在证据中已经出现的 ID，并使用当前工作区范围。规划失败时保留已有证据继续回答。

`retrieval-plan` 快照记录模型规划输入，`retrieval_expand` 事件记录已完成轮数和 stopReason。新增证据最终仍经过统一预算装配。

## OpenViking 长期记忆

应用为作用域与撤销代次生成独立 Peer。完成交互先写入本地 outbox，Worker 的后台线程上传独占 Session、提交抽取任务并轮询。上传可重建，提交通过 Session ID 查询已有任务以处理响应丢失，租约支持重启恢复。失败记录错误码并退避重试。

召回先使用 `search(mode="list", read_content=false)` 获取 L0 候选，按目录加载 L1 概览，最多对前两个 L2 来源各读 80 行。缺少概览时使用已有摘要与可用正文，manifest 记录实际加载层级。技能可进一步按 abstract、overview、detail 读取，远端正文使用行偏移与每页最多 80 行的限制。

检索、读取和删除验证当前 Peer 的路径归属。单条记忆屏蔽在 canonical URI 与 home alias 间保持一致。会话删除轮换共享作用域代次，取消旧投递并排队清理，依据保留会话重建远端派生记忆。

连接参数使用 Git 忽略的本地 env 配置，经 DODO_ENV_FILE 加载。服务端模型、embedding、Registry 和存储需要在目标环境配置，现有本地 HTTP 桩验证请求契约与状态机。

## 本地验证

```powershell
.\.venv\Scripts\python.exe -m unittest python_backend.modules.context_engineering.test_chain python_backend.modules.context_engineering.test_snapshots python_backend.modules.context_engineering.test_completion -v
.\.venv\Scripts\python.exe -m unittest python_backend.modules.retrieval.test_workspace_index python_backend.modules.retrieval.test_recall_quality python_backend.test_agent_gate -v
node --test frontend/src/modules/workspaces/paths.test.js frontend/src/modules/execution/progress.test.js
.\.venv\Scripts\python.exe -m compileall python_backend
.\.venv\Scripts\python.exe skill-center/test_center.py
.\.venv\Scripts\python.exe skill-center/test_agent_tools.py
npm --prefix frontend run build
```

测试覆盖原话抽取、约束修正、30 轮状态连续性、工作区隔离、私密来源过滤和旧索引清理、主聊天至 Worker 的范围传递、技能证据召回、澄清重分类、分层分页、多跳停止、分段摘要、远端投递幂等、撤销及 SSE 回放。

## 百万至亿级容量验收

`modules/context_engineering/benchmark.py` 使用合成 ASCII 语料，按 cl100k_base 对每个索引分块计数。语料按来源分组写入实际 SQLite FTS5 索引，通过标识符查询测 Recall@8 与延迟，并随机分页恢复来源正文核对 SHA-256，同时检查工作区隔离。

```powershell
.\.venv\Scripts\python.exe -m python_backend.modules.context_engineering.benchmark --tokens 1000000 --queries 40 --output data/context-benchmark/new-million-run
.\.venv\Scripts\python.exe -m python_backend.modules.context_engineering.benchmark --tokens 100000000 --queries 100 --output data/context-benchmark/new-hundred-million-run
```

输出目录应使用新路径，已有数据库会保留并拒绝覆盖。报告包含 tokenizer、计数方法、语料类型、索引数量与体积、建索引耗时、查询 P50/P95、Recall@8、原文恢复率、范围隔离与是否使用外部服务。

容量测试的边界是合成语料的本地索引与读取能力。实际模型窗口需匹配模型配置。真实语料的同义表达、冲突时效、长任务成功率、全局答案覆盖率、OpenViking 抽取质量和生产并发需要在目标环境另行验收，使用实际服务与标注数据记录召回、引用支持率、任务成功率、延迟、成本和投递积压。


### 本机容量验收记录

2026-11-09 的合成语料结果如下，完整报告位于本机 Git 忽略的 `data/context-benchmark/hundred-million-20261109/report.json`。

| 指标 | 实测值 |
| --- | --- |
| 分块累计 token | 100000000，cl100k_base |
| 来源与分块 | 977 个来源，125000 个分块 |
| 建索引耗时 | 1029.461 秒 |
| 索引体积 | 1099706368 字节，约 1.02 GiB |
| 标识符查询 | 100 条，Recall@8 为 1.0 |
| 查询延迟 | P50 14.220 ms，P95 24.896 ms |
| 原文分页恢复 | 抽样 5 份，SHA-256 一致率 1.0 |
| 工作区隔离 | 通过 |

语料类型为重复 ASCII 合成数据，本次外部服务调用为零，报告中的 semanticQualityMeasured 与 openVikingMeasured 均为 false。
