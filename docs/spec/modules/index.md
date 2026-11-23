# 模块功能规格索引

> 本目录按 **能力模块** 存放 Hotline 的功能现状说明：每个模块一份，改哪个模块就只加载那一份。
> 与上层的变更规格（`docs/spec/` 根目录）是两层东西：
> - 模块文档（本目录）= **这个模块现在有什么功能、入口在哪、约束是什么**，长期有效。
> - 变更规格（`docs/spec/*.md`）= **某一次改动定下了什么契约**，随改动新增。

## 怎么用

1. 接到改动任务，先在下方表里定位涉及哪个模块。
2. 只读该模块的文档（必要时读相邻模块），再读相关源码。
3. 改动涉及接口、表结构、跨模块语义时，按 `AGENTS.md` 的「规格驱动变更」另立一份变更规格，登记到 `docs/spec/index.md`。
4. 改了实现后，如果模块文档与代码不一致，**当场把模块文档改回来**。

## 模块地图

| 模块 | 文档 | 什么时候加载 | 关键入口前缀 |
| --- | --- | --- | --- |
| 执行与运行编排 | [execution.md](execution.md) | 改执行队列、并发子任务、Worker、工具治理、重试调度 | `/execution/*`、`/agent/*/stream` |
| 意图识别与澄清 | [intent.md](intent.md) | 改意图分类、澄清门闸、需求级澄清、检索链路 | `/intent/*` |
| 上下文工程 | [context_engineering.md](context_engineering.md) | 改上下文装配、预算、隐私、快照、记忆投递 | `/context/*` |
| 长期记忆 | [memory.md](memory.md) | 改记忆落库、乐观锁、OpenViking 接入 | 无独立路由 |
| 检索与向量召回 | [retrieval.md](retrieval.md) | 改 pgvector、工作区索引、分层召回、融合 | 无独立路由 |
| 文档解析与向量化 | [documents.md](documents.md) | 改 MinerU 解析、切块向量化、PPT 生成 | `/file/*`、`/document/*` |
| 工作区与资源 | [workspaces.md](workspaces.md) | 改工作区检出、规则加载、快照与差异、Agent 资源 | `/harness/workspaces/*`、`/harness/agents/*` |
| 存储适配 | [storage.md](storage.md) | 改对象存储与关系库适配层 | 无独立路由 |
| 技能中心 | [skills.md](skills.md) | 改技能包安装、目录、绑定、披露、自进化 | `/harness/skills/*` |
| MCP 工具接入 | [mcp.md](mcp.md) | 改 MCP 服务器接入、工具发现与调用 | `/harness/mcp/*` |
| 产物与文件登记 | [artifacts.md](artifacts.md) | 改产物登记、下载、预览与过期清理 | `/harness/artifacts/*` |
| 评测与基准 | [evaluation.md](evaluation.md) | 改数据集、用例、评分、跑批与导出 | `/evaluation/*`、`/tools/runs` |
| 审批与机器治理 | [governance.md](governance.md) | 改人工审批、审计、机器心跳与排空 | `/harness/approvals/*`、`/harness/machines/*` |
| 发布治理 | [release.md](release.md) | 改灰度、门禁、晋级与回滚 | `/release/*` |
| 数据保留与清理 | [retention.md](retention.md) | 改运行历史、审批、产物的保留窗口 | 无独立路由 |
| Harness 控制台 | [harness-console.md](harness-console.md) | 改工具与模型登记、机器人、凭据、设置、调度、可观测、代码地图 | `/harness/tools/*`、`/harness/bots/*`、`/harness/profile`、`/harness/settings`、`/harness/schedules/*`、`/harness/observability/*` |
| Vue 工作台主界面 | [chat-web.md](chat-web.md) | 改对话、文件问答、PPT、深度研究、模式条、候选答案面板、会话历史 | `/agent/*/stream` |

## 写模块文档的约定

- 结构照 [_module-template.md](_module-template.md)：`#` 模块 → `##` 功能点 → `###` 入口/行为/关键实现 → 数据与存储 → 接口清单 → 边界与已知限制。
- 每个功能点至少一个可核对入口（`文件:函数` 或 HTTP 路由）；只写代码里真实存在的行为。
- 模块文档描述**现状**，不写历史与计划；改动导致描述过时，就改文档。