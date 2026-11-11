> 实施记录：保留 Harness 建设过程、接口与验收说明。涉及迁移前目录和入口的内容仅供追溯，当前组件路径、Java 入口和启动命令以 [主 README](../README.md) 为准。

# Harness 功能实施计划

## 目标

把 Harness 从演示型控制面逐步改成可以验证、可以追踪、可以治理的真实工程页面。每个菜单只负责一个 bounded context，跨模块内容通过只读 ID 关联，不复制对方的编辑入口。

## 当前原则

- 执行任务只负责提交、排队、停止、重试、运行事件、Trace 和单次运行产物关联。
- 测评中心只负责测评集、样本、评分器、评测配置、质量门禁和历史报告。
- Agent 实例只负责 Agent 定义、版本、模型、工具权限和运行策略。
- 工作空间只负责仓库、分支、快照和文件变更。
- 工具与 MCP 只负责工具目录、Schema、连接、权限和审批策略。
- Skills 只负责 Skill 包、版本、启停、绑定和发布关联。SkillRegistry 与 Catalog 保持对象分离。
- 模型路由只负责提供商、路由、fallback、成本和可用性策略。
- 机器与运行时只负责节点、容量、心跳、隔离和排空。
- 待审批只负责审批请求、决定、操作者和审计记录。
- 产物与存储只负责产物索引、预览、下载和保留策略。
- 追踪与日志只负责 Trace、日志、指标查询和导出，不负责启动或停止任务。
- 发布治理负责灰度、promote、rollback、rollouts 和自动回滚，不编辑测评样本。
- Harness 设置负责运行时默认值、审批策略、审计保留和系统级策略模板。

## 实施顺序

### 1. 执行任务

目标是让运行任务形成真实闭环。

- 运行列表、状态筛选、搜索和分页
- 创建运行表单
- 运行详情和状态刷新
- 取消排队或运行中的任务
- 事件流和 Trace 读取
- 错误信息、结束时间和失败状态
- 单次运行上下文和产物只读关联
- 运行重试和复制配置
- Worker readiness 和加载态、空态、错误态

验收标准是创建一条运行后可以在列表中看到真实 `runId`，状态可以从 queued 变化到 running 或 terminal，取消后状态为 cancelled，刷新页面仍可恢复详情。

### 2. 测评中心

- 测评集 CRUD 和版本
- 样本编辑、期望结果、工具断言和评分器
- Agent、Skill、模型版本选择
- 评测配置保存
- 评测运行记录和样本级结果
- 失败样本回放
- 报告比较、导出和质量门禁结果

验收标准是一次测评可以生成独立 `evalRunId`，并通过 `runId` 只读关联执行任务，不把测评配置混入普通运行。

### 3. 发布治理

- 当前绑定版本
- 灰度比例
- promote、rollback、rollouts
- 错误率和自动回滚记录
- 发布前质量门禁

验收标准是只有通过质量门禁的版本才能进入灰度，回滚后后续请求不再选择被撤回版本。

### 4. Agent 实例与工作空间

- Agent 定义、版本差异、权限和策略
- 工作空间、仓库、分支、快照和文件变更
- 运行与 Agent、Workspace 的只读关联

### 5. 工具与 MCP、Skills、模型路由

- 工具 Schema、连接测试、风险和审批策略
- Skill 包、Catalog 版本、绑定和启停
- 提供商、fallback、成本和可用性

### 6. 机器与运行时、待审批

- 节点注册、排空、容量、心跳、运行时版本
- 审批队列、审批详情、拒绝原因、超时和审计导出

### 7. 产物、追踪与日志

- 产物索引、预览、下载、Hash 和保留
- Trace、日志、指标、时间范围、过滤和导出

### 8. Harness 设置

- Worker 和运行时默认值
- 审批策略
- 审计保留周期
- 默认预算、超时和重试策略

## 统一接口约定

- 列表接口返回 `items`、`total`、`nextCursor` 或明确分页字段。
- 资源详情返回稳定 ID、版本、状态、更新时间和数据来源。
- 所有运行关联使用 `runId`，测评关联使用 `evalRunId`。
- 运行事件使用递增 `eventId`，支持从游标恢复。
- 前端区分 loading、empty、error、offline 和 demo 状态。
- 未接入后端的操作必须禁用或明确显示为演示动作，不显示成功的真实语义。

## 本轮实施范围

2026-11-07 对全文勾选项做了逐条代码核查：修正了 8 处「文档标 `[x]` 但运行时并未生效」的条目，补齐了 21 项未实现能力，并把仍未实现的部分从勾选里拆出来单独列明。执行任务、测评中心、发布治理、待审批、机器与运行时、追踪与日志、产物、Agent 实例、工作空间、工具与 MCP、模型路由、Harness 设置均已接入真实后端能力；Harness 页面已接入对应接口，不再用演示数据冒充真实结果。

尚未实现的能力见文末「仍未实现」小节，不使用勾选表示。

## 实施记录

### 执行任务，第一阶段

- [x] SQLite 运行列表、详情和事件查询
- [x] 按 `runId` 取消 queued 或 running 任务
- [x] 创建运行接口和前端新建运行表单
- [x] 执行任务页接入真实列表和事件接口
- [x] Worker 不可用时显示错误，读取失败保留上次真实记录
- [x] Vite 开发代理增加 `/execution` 路由
- [x] 复制运行配置创建新任务
- [x] 运行上下文快照（脱敏、限长的调用前输入预览）

### 执行任务，第二阶段

- [x] 失败运行按原配置创建新的重试运行
- [x] 重试继续使用独立 `runId`
- [x] 运行详情失败状态显示真实重试入口
- [x] 运行 Trace 展示当前 read_skill 工具调用参数、返回预览、状态与耗时
- [x] 运行事件实时 SSE 和按事件游标断线续传
- [x] 运行列表 offset 分页、服务端状态筛选和搜索

### 执行任务，真实事件与状态展示

- [x] 运行列表和详情使用执行服务数据，空列表可正常显示
- [x] 完成、失败、取消和排队状态独立展示，移除共享 running 布尔状态
- [x] 切换 runId 时立即清空事件，拦截旧请求的迟到响应
- [x] 展示任务输入、文本输出、提交信息、时间和实际 Worker
- [x] Trace 展示后端记录的原始事件，并可下载 JSON
- [x] 已连接过服务后请求失败时显示缓存与错误，保留正确任务归属
- [x] 真实详情移除示例审批、产物、上下文、成本和进度信息
- [x] Worker 记录当前工具调用循环的参数、返回预览和错误状态
- [x] SSE 实时流、事件去重、断线续传和列表分页
- [x] 新生成 PPT 的真实产物关联
- [x] 调用前上下文快照、运行归属和只读详情

列表每页 25 条，按创建时间和写入顺序倒序分页；状态与搜索由服务端筛选，切换条件回到首页。当前页每 5 秒刷新，新增记录会使 offset 分页的位置变化，分页不提供固定快照。创建或重试后清除筛选并回到首页选中新运行。

执行详情通过只读 `/execution/runs/{runId}/stream` 接收带事件编号、时间和正文的 SSE，使用 `after` 与 `Last-Event-ID` 续传并去重；结束时补齐末尾事件并关闭连接。切换运行、服务地址或离开执行任务页时清理旧连接，迟到请求与旧事件不覆盖当前任务。原对话 SSE 保持既有事件正文与 `[DONE]` 格式，并接收实际工具调用事件。总览指标和节点表仍为明确标注的演示内容。

验证：`python -m unittest python_backend.modules.execution.test_execution -v`（使用已安装项目依赖的 Python 环境），覆盖分页、服务端筛选、SSE 续传、只读边界、对话流兼容和末尾事件竞态。

### 执行任务，工具调用 Trace

- [x] Skills 的 read_skill 通过工具执行中间件实时发出 tool_start / tool_end
- [x] 每次调用保留 toolCallId、工具名、实际参数预览、返回预览、状态和耗时
- [x] 并行调用按调用编号关联，返回错误、异常与取消分别记录
- [x] Worker 将事件写入所属 runId，可通过 JSON API、SSE 续传和 Trace 导出读取
- [x] 运行详情展示参数与结果，聊天时间线识别工具失败、停止及实际耗时
- [x] 常见凭据字段、Bearer、URL、IP 和私钥文本遮盖；异常不写入原始异常消息
- [x] 参数 / 结果预览分别限制为 4000 / 12000 个 JSON 字符，截断时附标记，不改变传给工具和模型的原值
- [x] deep / file / ppt 内部检索与生成步骤的独立追踪

当前工具事件仅覆盖实际使用工具执行循环的 Skills / read_skill，不把其他模式的内部步骤标成工具调用。工具返回错误后模型仍可恢复并完成任务，因此工具状态与任务最终状态分别展示。遮盖为常见模式匹配，不保证识别所有自由文本中的敏感信息；事件保存在本地运行数据库，不启用外部追踪上传。未完成的调用在 Worker 被强制终止时可能只留下开始事件。

验证：`python skill-center/test_agent_tools.py`，包括离线模型驱动的工具执行、实时开始事件、并行关联、失败与取消、预览遮盖和截断，以及真实 Worker 落库与 SSE 回放；无需访问外部模型。

### 执行任务与产物，真实归属和下载

- [x] 产物模块独立 SQLite 登记表，保存稳定 artifactId 与真实 runId
- [x] PPT Worker 生成成功后登记文件名、大小、生成时 SHA-256、类型、存储方式和存储键
- [x] 同一会话的不同运行使用各自 runId 目录和对象键，重试不覆盖上一运行
- [x] 产物查询按实际 runId 筛选并分页，移除生成目录扫描与推测归属
- [x] 执行任务详情通过只读接口查看本次产物，产物页独立筛选、分页和刷新
- [x] 产物页读取失败显示错误或保留缓存，真实空列表不回退到演示记录
- [x] 本地下载限制在生成目录内；对象存储通过产物 ID 代理读取，不向页面暴露服务地址
- [x] Worker 写入 artifact 事件，聊天下载入口兼容新的下载路径
- [x] 产物预览与保留清理
- [x] 按用户身份的下载权限（身份来自请求头 `X-Harness-Owner`）
- [x] 其他生成入口的产物登记
- [ ] 历史文件的人工归属迁移

当前覆盖 FastAPI / Execution Worker 新生成的 PPT。元数据位于 `data/artifacts.db`（使用配置的数据目录），API 与 Worker 需共享数据目录及生成文件目录。本次不修改未登记历史文件，也不根据文件名补归属；旧版直接生成入口的文件不会自动出现在登记列表。

PPT 模式在运行时成功返回后才生成文件。生成前取消或运行时失败不登记产物；若生成或登记后才收到取消，已生成产物可保留供诊断，任务仍以取消状态结束。文件删除或存储未配置时下载返回明确错误。SHA-256 记录生成时内容，当前下载不重新计算 Hash。现有身份认证与多用户授权尚未扩展到此接口。

验证：`python -m unittest python_backend.modules.artifacts.test_artifacts -v`，覆盖真实 PPT 生成、同会话多次运行隔离、持久化、分页过滤、本地下载、目录越界、对象存储代理与错误、失败和取消分支。对象存储使用测试替身，不访问外部服务。

### 执行任务，上下文快照

- [x] 普通模式在回答调用前捕获已组装消息，记录实际选入历史、文件来源、检索路由和搜索证据数量
- [x] 检索路由分类与 Text2SQL 的模型输入分别记录快照
- [x] Skills 每轮模型请求捕获系统消息、当前问题、工具定义、已有工具请求和实际工具返回
- [x] 快照含捕获时间、模型名称、配置状态、阶段、消息数和来源信息
- [x] 复用运行事件日志持久化，通过 runId 归属；新增只读 `/execution/runs/{runId}/context` 查询
- [x] 执行详情增加上下文页签，随现有事件 SSE 更新；Trace JSON 导出包含快照事件
- [x] 历史运行按记录读取，重试生成独立记录；未捕获的历史运行显示空态
- [x] 模型失败保留已捕获快照；来源组装失败或执行前取消不补造快照
- [x] 并发 Worker、历史变更与配置变更不覆盖其他运行的已存快照

快照在模型调用前构建，随后随运行事件流写入本地执行数据库。只记录明确选取的模型名和输入字段，不采集服务地址、凭据或完整模型对象配置。普通回答历史仍遵循最近 4 个有效轮次及历史回答 1500 字符限制；Skills 仍只使用当前问题及本次工具循环，不加入旧会话历史。

每份快照最多展示前 24 条消息、前 8 个工具定义；单条消息内容预览上限 6000 个 JSON 字符，工具消息关联与来源信息各 4000 个，工具定义 12000 个，超限附截断或省略标记。常见敏感模式复用工具 Trace 遮盖规则，不保证识别所有自由文本中的秘密。快照是准备输入的预览，不是完整可重放请求，也不证明外部模型调用成功；本地无模型降级会明确标记。旧记录不会根据当前配置补建快照。

验证：`python -m unittest python_backend.modules.context_engineering.test_snapshots -v` 与 `python skill-center/test_agent_tools.py`，覆盖历史选取、路由与 SQL 输入、Skills 渐进工具上下文、失败、限长遮盖、Worker 持久化、只读查询、重试与并发隔离。

### 测评中心，第一阶段

- [x] 独立 SQLite 测评集、样本、配置和评测运行存储
- [x] 测评集列表、创建和样本写入接口
- [x] 评测配置读取与保存接口
- [x] 评测运行记录使用独立 `evalRunId`
- [x] Harness 测评集创建表单和配置保存入口
- [x] 测评执行器无样本、无 Worker 或执行失败时显示 blocked / failed 状态，不伪装成已执行
- [x] 测评集详情和样本编辑器
- [x] 规则型评分器、真实执行与样本级报告
- [x] 模型评分（可选 rubric `{"type":"model"}`）
- [x] 失败样本回放与报告导出
- [x] 报告对比

### 发布治理，第一阶段

- [x] 独立发布治理菜单和职责说明
- [x] 灰度、发布记录和线上指标读取接口
- [x] promote、rollback 和 metric 接口
- [x] Harness 页面显示当前灰度、发布记录和线上指标
- [x] 发布治理操作保持与测评中心、执行任务分离
- [x] 发布前质量门禁校验
- [x] 灰度比例推进
- [x] 定时观察
- [x] 错误率阈值配置
- [x] 自动回滚详情

### 测评中心，第二阶段

- [x] 测评集详情读取
- [x] 样本新增和编辑
- [x] 期望输出和评分规则 JSON 保存
- [x] 样本编辑不创建执行任务
- [x] 样本删除、批量导入和版本快照
- [x] 评分器运行、样本级结果和失败回放

### 发布治理，第二阶段

- [x] 发布前质量门禁接口
- [x] 端到端通过率阈值
- [x] RAG 忠实度阈值
- [x] 高风险工具误调用阈值
- [x] promote 必须携带通过的门禁结果
- [x] 发布页面增加门禁检查和灰度前置条件
- [x] 门禁结果持久化并关联 evalRunId
- [x] 发布记录展示门禁证据和审批人

### 发布与测评、审批审计关联

- [x] 质量门禁支持传入 `evalRunId`
- [x] 发布门禁校验 `evalRunId` 是否存在
- [x] 审批请求提供单条详情读取
- [x] 审批记录包含 runId、理由、操作者决定时间字段
- [x] 门禁记录持久化快照
- [x] 发布页面展示门禁历史和完整门禁 ID
- [x] 发布记录展示审批人和完整证据

### Harness 设置，第一阶段

- [x] 运行时默认隔离方式
- [x] 审计保留周期
- [x] 审批策略
- [x] 默认预算、超时和重试次数
- [x] 设置读取和保存接口
- [x] 设置页面不保存密钥或服务凭据

### Agent 实例与工作空间，第一阶段

- [x] Agent 目录读取和创建接口
- [x] 工作空间目录读取和创建接口
- [x] Harness 页面显示独立的 Agent 和工作空间资源页
- [x] 创建入口不启动运行任务
- [x] 运行任务与资源通过只读关联保持边界
- [x] Agent 权限、Skill 绑定、版本差异和启停
- [x] 工作空间快照和文件变更
- [x] 仓库连接与分支检出
- [x] 资源详情页和编辑操作

### Agent 实例，详情与编辑

- [x] 通过 agentId 读取最新配置并打开编辑表单
- [x] 创建和编辑名称、说明、版本标签、模型路由及策略 JSON
- [x] 策略必须是 JSON 对象，必填字段拒绝空白值
- [x] 旧数据补充 revision，保存冲突返回 409 并保留表单输入
- [x] Agent 读取与其他目录请求独立，服务返回空列表时展示空态
- [x] 版本历史与差异对比
- [x] Worker 按 Agent 定义装配权限、模型和技能

当前模型路由与策略为目录元数据，保存后可重新读取。本轮已接入启停、工具权限与 Skill 绑定、版本历史快照与差异对比；Worker 按 Agent 定义装配模型、工具白名单与 Skill，被停用的工具在调用前被拦截。

### 工作空间，详情与编辑

- [x] 通过 workspaceId 读取详情，展示状态、修订号和更新时间
- [x] 创建和编辑名称、仓库标识、分支
- [x] 旧数据自动补充 revision，陈旧修订保存返回 409 并保留输入
- [x] 名称和分支拒绝空白值
- [x] 工作空间独立刷新，真实空列表显示空态
- [x] 快照和文件变更
- [x] 仓库连接与分支检出

本轮已接入仓库检出（`POST /harness/workspaces/{id}/checkout`，只落到 `data/workspaces/<id>/repo`，不触碰用户真实工作树）、目录快照与文件变更登记；快照反映的是目录现状而非提交历史。

### 工具与 MCP、Skills、模型路由，第一阶段

- [x] 工具目录读取接口，包含来源、范围、风险和状态
- [x] 模型路由目录读取接口，包含提供商、路由、状态和成本策略
- [x] Skills 页面区分本地安装包目录与发布治理版本
- [x] Harness 页面显示工具、Skills 和模型的独立目录
- [x] 工具 Schema、连接测试和审批策略编辑
- [x] Skill 版本详情与本地包启停
- [x] Catalog 绑定写入入口
- [x] 提供商连接测试与 fallback
- [x] token 预算执行（`defaultTokenBudget`，超限即失败）
- [ ] 金额预算执行（`defaultBudgetUsd` 没有用量口径）

### 工具与 MCP，详情与编辑

- [x] 工具登记、详情和编辑表单
- [x] 来源标识、权限范围、风险等级、登记状态和说明保存
- [x] 参数 Schema JSON 和审批策略保存
- [x] Schema 根对象、properties、required 基本结构校验
- [x] 旧记录迁移、修订号冲突检测和失败时保留输入
- [x] 工具目录独立读取，真实空列表显示空态
- [x] MCP 连接器与服务连接测试
- [x] 工具发现与工具调用
- [x] 运行时参数校验及审批策略执行

当前保存的是工具目录配置。登记状态不代表服务连接状态，Schema 基本结构校验也尚未覆盖完整 JSON Schema 规范。本轮已接入连接测试（`POST /harness/tools/{id}/test`）、MCP stdio 的 initialize 与 tools/list、工具调用（`POST /harness/mcp/servers/{tool_id}/tools/{tool_name}/call`）、运行时参数校验与审批策略拦截。

### 模型路由，详情与编辑

- [x] 模型路由登记、详情、编辑和独立目录刷新
- [x] 提供商标识、路由用途、登记状态及成本策略说明保存
- [x] 按模型 ID 选择备用模型，校验不存在引用及循环引用
- [x] 旧记录自动补充修订号及 fallback 字段
- [x] 修订冲突返回 409，失败时保留输入
- [x] 提供商连接测试与运行时 fallback
- [x] token 预算执行（`defaultTokenBudget`，超限即失败）
- [ ] 金额预算执行（`defaultBudgetUsd` 没有用量口径）

当前提供商、成本策略与 fallback 是目录配置，成本策略为文本说明。本轮已接入连接测试、运行时 fallback 切换与 token 预算执行；金额预算（`defaultBudgetUsd`）仍只是配置项，没有用量口径。

### Skills，本地安装包详情与启停

- [x] 修正 getSkills 数组返回值读取，独立刷新本地安装目录
- [x] 真实空目录显示空态，演示记录不提交真实启停请求
- [x] 查看安装包来源、入口、安装时间、启用状态和 SKILL.md 文本
- [x] 详情复用既有本地包启停接口，成功后同步列表与弹窗状态
- [x] 停用包仍可预览，预览拒绝越界、符号链接和非文本文件
- [x] 元数据使用原子替换，写入失败保留原启停状态
- [x] Catalog 版本正文、版本差异和项目绑定详情

正文预览最多展示前 12000 个字符，入口文件超过 1 MiB 时拒绝读取。本页操作仅针对本地安装包，Catalog 版本与发布治理保持独立。

本轮验证还补齐了发布路由已引用的 evaluation_store.get_run 查询方法，通过本地 SQLite 配置的完整 FastAPI 启动和 Skill API 联调。

### Skills，Catalog 版本与绑定展示

- [x] 本地安装包与 Catalog 版本使用独立页签和请求
- [x] 当前项目的绑定版本、灰度比例只读展示
- [x] 查看指定 Catalog 版本正文与附加资源清单
- [x] 同名技能版本正文差异比较及资源新增、删除、修改清单
- [x] 缺失版本返回明确错误，读取和比较不修改绑定
- [x] 附加资源正文的逐文件比较

Catalog 版本预览展示前 12000 个字符。正文差异最多展示 2000 行且不超过 120000 字符。本轮已接入项目绑定写入（`POST` / `DELETE /harness/skills/catalog/bind`）与附加资源正文的逐文件差异（`resourceDiffs`）；绑定写入当前项目，实际请求采用的灰度版本仍由运行时按比例选择。

### 机器与运行时、待审批，第一阶段

- [x] Worker 列表、进程、心跳和当前运行读取
- [x] 审批请求存储、待审批列表和决定接口
- [x] Harness 页面拆分运行时节点和审批队列
- [x] 审批批准、拒绝和理由保留独立审计记录
- [x] 节点排空、容量和运行时版本
- [x] 节点错误日志
- [x] 审批超时、批量决定和风险策略
- [x] 审批通知

### 产物、追踪与日志，第一阶段

- [x] 运行产物登记索引接口，按真实 runId 查询
- [x] Trace 运行列表和事件读取接口
- [x] Harness 页面拆分产物索引与追踪日志
- [x] 产物和 Trace 保持只读边界
- [x] 新生成 PPT 的 Hash 与按产物 ID 下载
- [x] 产物预览与保留清理
- [x] 按用户身份的下载权限（身份来自请求头 `X-Harness-Owner`）
- [x] Trace 按时间、级别、工具和错误筛选
- [x] Trace JSON 导出与运行指标聚合
- [x] 跨运行日志导出与指标趋势

### 核查与修复，2026-11-07

按代码而非文档逐条核对后，发现并修复了以下偏差。文档原先的勾选反映的是「打算做什么」，与代码实际状态不一致。

| 条目 | 核查发现的偏差 | 修复方式 |
|---|---|---|
| 质量门禁关联 evalRunId | `governance_store.save_gate` 读 `eval_run_id`，上游传的是 `evalRunId`，关联永远写成 NULL | 统一为 snake_case，保存端兼容两种键名 |
| 审批重复决定 | UPDATE 带 `status='pending'` 条件，已决定项再决定仍返回旧行，前端提示成功 | 已决定抛 `ApprovalStateError`，接口返回 409 |
| 机器与审批列表 | 连接成功但数据为空时回落到演示节点与演示审批 | 只在未连接时使用演示数据，真实空列表显示空态 |
| 测评中心质量门禁与 KPI | 写死 91.7% / 89.6% / 失败 24 例等演示值 | 改为读取真实测评运行与门禁记录，取不到数据显示「—」并标注演示 |
| 历史报告导出 | 点击只提示「已准备」，没有任何真实导出 | 改为按真实测评运行导出 CSV；没有真实数据时按钮禁用 |
| Harness 设置 | 6 个字段存进库，但运行时没有任何读取方 | Worker 读取超时、重试与隔离；审批超时取自设置；审计保留驱动定期清理 |
| Trace 事件读取 | 后端接口与前端封装都在，却没有任何页面调用 | 追踪页接入事件明细、级别/工具/错误/时间筛选与 JSON 导出 |
| 发布记录 | 读的是技能自进化的 `evolution_runs`，promote 与 rollback 不写这张表 | 新增 `release_record` 表，发布、推进、回滚、自动回滚都真实落库 |

另外修正了两处会破坏数据的行为：灰度推进复用 promote 时会把回滚目标覆盖成候选版本自身，导致回滚退化为空操作；产物下载与预览的本地路径校验抽成共用实现，避免两处规则漂移。

### 本轮补齐的能力

测评中心：数据集删除、版本快照与快照列表、样本批量导入、样本级结果、规则型评分器（contains / equals / json_equals / always，未知规则记 invalid_rubric）、失败样本回放、测评运行改为后台线程执行并可轮询进度。

发布治理：发布记录落库并展示门禁证据与审批人、灰度比例推进、门禁阈值与错误率阈值可配置、promote 强制携带通过的门禁结果。

待审批：审批超时过期、批量决定、审计 CSV 导出、详情读取、审批超时时长取自 Harness 设置。

机器与运行时：节点容量、运行时版本、排空与恢复、离线状态判定。

追踪与日志：事件按级别、工具、错误、时间范围与类型筛选，指标聚合接口，Trace JSON 导出。

产物与存储：文本类产物预览、按保留天数清理登记并可同时删除本地文件、列表返回存留天数。

Agent 实例：启停、工具权限与 Skill 绑定、版本历史快照与字段级差异对比、与执行运行的只读关联。

工作空间：仓库目录快照、文件变更登记、与执行运行的只读关联。

工具与 MCP：工具连接测试、MCP stdio 连接器（initialize 探测）、运行时参数校验、审批策略在工具调用前真正拦截。

模型路由：提供商连接测试、fallback 链与环检测、运行时失败回退。

执行任务：复制运行配置创建新任务、运行与 Agent / 工作空间的真实 ID 关联（不再显示 `file:xxx` 占位）。

Harness 设置：超时、重试、隔离、审批超时、审计保留、产物保留全部有运行时读取方或清理任务。

### 本轮验证

- `python -m unittest python_backend.modules.execution.test_execution python_backend.modules.execution.test_worker_policy python_backend.modules.execution.test_runtime_policy python_backend.modules.artifacts.test_artifacts python_backend.modules.context_engineering.test_snapshots python_backend.modules.evaluation.test_evaluation python_backend.modules.retention.test_retention python_backend.modules.workspaces.test_resources python_backend.modules.mcp.test_registry python_backend.modules.governance.test_notifications python_backend.api.test_router_contracts`：196 个用例通过。
- `python skill-center/test_center.py`：6 个用例通过；`python skill-center/test_agent_tools.py`：26 个用例通过。
- `python -m compileall python_backend`：通过。
- `npm --prefix frontend run build`：通过。

测试模块：`python_backend/api/test_router_contracts.py`（前后端路径契约）、`python_backend/modules/evaluation/test_evaluation.py`（测评、门禁、审批）、`python_backend/modules/retention/test_retention.py`（保留期清理）、`python_backend/modules/execution/test_worker_policy.py`（超时与自动重试）、`python_backend/modules/execution/test_runtime_policy.py`（Agent 装配、工具白名单、token 预算）、`python_backend/modules/workspaces/test_resources.py`（Agent 与工作空间）、`python_backend/modules/mcp/test_registry.py`（工具、MCP 与模型路由）、`python_backend/modules/governance/test_notifications.py`（审批通知）。

### 第二轮补齐的能力

上一节列出的 16 项剩余能力已全部落地，前端同步接入了操作入口。

| 能力 | 实现位置 |
|---|---|
| deep / file / ppt 步骤级追踪 | `agents.py` 的 `AgentEngine.step()` 与 worker 的 `step` 事件（stage / content / durationMs / details） |
| 产物按身份下载 | `run_artifact` 增 `owner` 列，下载与预览按 `X-Harness-Owner` 请求头校验，`GET /harness/artifacts?owner=` 按归属过滤 |
| 生成入口收敛 | 已移除旧标准库 HTTP 服务，统一通过 `main:app` 与执行 Worker 生成产物 |
| 模型评分 | 可选 rubric `{"type":"model"}`，模型不可用时 verdict=`scorer_unavailable`、score=0，不伪造分数 |
| 报告对比与导出 | `GET /evaluation/runs/compare`、`GET /evaluation/runs/{id}/export?format=csv\|json` |
| 灰度定时观察 | 后台观察线程 + `POST /release/rollouts/observe` + `GET /release/observations`，观察记录落 `release_observation` 表 |
| 自动回滚详情 | `release_record` 增 error_rate / sample_count / threshold，回滚记录带当时的实测值 |
| 仓库连接与检出 | `POST` / `GET /harness/workspaces/{id}/checkout`，只落到 `data/workspaces/<id>/repo` |
| Worker 按 Agent 装配 | `execution_worker.py` 读 `harness_agent` / `harness_model`，工具白名单与停用拦截 |
| token 预算 | `defaultTokenBudget` 累计用量，超限即失败 |
| MCP 工具发现与调用 | `api/routers/mcp.py` 的 `GET /harness/mcp/servers` 与 `POST /harness/mcp/servers/{tool_id}/tools/{tool_name}/call` |
| Catalog 绑定写入 | `POST` / `DELETE /harness/skills/catalog/bind` |
| 附加资源逐文件比较 | `version_compare` 返回 `resourceDiffs` |
| 节点错误日志 | `GET /harness/machines/{worker_id}/errors` |
| 审批通知 | `harness_notification` 表 + `GET /harness/approvals/notifications`，可选 webhook 外发 |
| 跨运行导出与趋势 | `GET /harness/observability/exports`、`GET /harness/observability/trends` |

前端同步接入：审批通知面板、报告对比与样本导出、灰度观察按钮与观察记录、MCP 工具发现与调用、工作空间检出、Catalog 绑定、节点错误日志、追踪页的运行事件筛选 / 指标 / 趋势 / 跨运行导出、产物归属身份输入与带身份头下载。

新增 `python_backend/api/test_router_contracts.py`：核对 `frontend/src/api.js` 用到的每条路径在 FastAPI 中真实注册，并检查动态段没有抢占静态路径（例如 `/evaluation/runs/compare` 不会被 `/evaluation/runs/{eval_run_id}` 吃掉）。

### 第三轮补齐的能力，2026-11-07

按「只有页面、没有功能」的审计清单逐条落地：主应用四处空壳页、Harness 控制面的演示数据、后端已有但前端没接的接口，以及个人中心的两个禁用表单。

| 页面 / 区域 | 之前 | 现在 |
| --- | --- | --- |
| 安排任务 | 空壳，按钮禁用 | `harness_scheduled_task` 表 + `/harness/schedules` 五个接口 + 调度线程，到点自动提交运行 |
| 插件 | 空壳 | 技能列表真实读 `/skill/list`，启停与删除走真实接口 |
| 虚拟桌宠 | 只有一个禁用开关 | 开关与形象存本机 localStorage，右下角真的渲染桌宠 |
| 轻量机器人 | 「规划中」占位 | `harness_bot` + `harness_bot_session` 两张表 + `/harness/bots` 六个接口；人设按会话绑定并进入模型系统提示词 |
| 个人中心 · 基础信息 | disabled 表单 | `GET/PUT /harness/profile`，昵称与简介真实落库 |
| 个人中心 · API Key | disabled 表单 | `GET/PUT/DELETE /harness/profile/credentials` 与 `POST .../test`，凭证存本机 data 目录，接口只回掩码 |
| 个人中心 · 个性化 | disabled 表单 | 回答风格写进系统提示词；界面主题用 `data-theme` 切换，新增 `frontend/src/theme.css` 为 style/chat/harness 三套调色板统一提供暗色 token |

Harness 控制面：总览 5 个 KPI 与 9 个导航计数改为真实统计；移除 8 处演示数据回落、不可达的 module-page 死代码、前端自造 CSV 导出与侧栏「演示」标注。

后端已有、前端未接的接口已接线：审批详情 / 批量决定 / 审计导出、节点排空、删除测评集、运行详情真读、`/harness/models/{id}/fallback-chain`、`/execution/runs/{id}/context`、`GET+POST /release/metrics`、`GET /release/runs`。

人设链路：机器人 instruction、绑定技能与个人回答风格统一由 `infrastructure/persona.py` 汇总，Worker 通过 `AgentEngine(persona_reader=...)` 注入系统提示词（只追加、不覆盖既有规则）；机器人 `enabled=false` 时只保留个人风格。

模型凭证：`llm.model_config()` 统一合并「本机保存的凭证」与「环境变量」，本机凭证优先；`agents.py`、`documents.py`、`llm.py` 的模型调用与就绪判断全部改走这份配置。

顺带修掉一处真实缺陷：`App.vue` 调用了未导入的 `getSessions`，会话列表在运行时抛 `getSessions is not defined`。

本轮验证：

- `python -m unittest` 全量用例（execution / artifacts / context_engineering / evaluation / retention / workspaces / mcp / governance / api 契约 / bots 与 profile）共 214 个用例通过。
- `python skill-center/test_center.py`、`python skill-center/test_agent_tools.py`、`python -m compileall python_backend`、`npm --prefix frontend run build` 全部通过。
- 新增 `python_backend/api/test_bots_profile.py`：机器人增删改查与会话绑定、人设注入、偏好部分更新、凭证掩码与保留、本机凭证优先于环境变量。

### 仍然存在的限制

以下不是遗漏，是当前工程边界，文档如实标注：

- 身份体系：产物下载权限用请求头 `X-Harness-Owner` 实现（设置键 `artifactOwnerHeader`）。项目没有统一鉴权体系，接入真实身份后替换 resolver 即可。
- 金额预算：`defaultBudgetUsd` 没有用量口径，真正被执行的是 token 预算 `defaultTokenBudget`。
- MCP 传输方式：只实现 stdio JSON-RPC（initialize / tools-list / tools-call），响应不回显命令、参数和本机路径。
- 仓库检出：只允许落到 `data/workspaces/<id>/repo`，不触碰用户真实工作树；填本地目录时无需检出。
- 历史文件归属：历史生成文件不会自动进入产物列表，需要人工登记。
- 模型评分：模型不可用时判 `scorer_unavailable`，不会用规则评分器冒充模型评分。
- 模型凭证：存本机 `data/harness-credentials.db`，明文落盘、没有鉴权也没有加密；接口只回掩码，前端不回显完整密钥。多人共用机器前需要自建鉴权。
- 机器人绑定：一个会话同时只能绑定一个人设，不支持多机器人并行；停用机器人后其人设立即失效，个人回答风格仍然生效。
- 深色主题：覆盖 style.css、chat.css、harness.css 的主界面容器与控件，少数内嵌小部件仍是浅色硬编码。
