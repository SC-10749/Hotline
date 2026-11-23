# Hotline Agent 持久协作规则

本规则适用于 `F:\Hotline` 及其全部子目录。用户要求：任何时候都不得上传 `.env`、真实密钥或包含其真实服务地址的文件。

## 项目结构与目录管理

- 所有开发者和 Agent 开始开发前，必须阅读并遵循本文件；子目录另有说明文件时一并遵循。子目录规则不得放宽本文件中的私密信息保护要求。
- **本仓库是单一项目 Hotline Agent**：Java 21 入口（`java_backend/`）、Vue 前端（`frontend/`）、FastAPI 后端（`python_backend/`）、技能中心（`python_backend/modules/skills/` 与 `skill-center/`，根 `skill_center.py` 为兼容入口）、静态资源与技能控制台（`static/`）、部署脚本（`deploy/`）、文档（`docs/`）同仓维护，不再有平台与项目之分。
- 修改默认限于对应子目录；涉及跨目录的公共改动（如 `.env.example`、`AGENTS.md`、根启动脚本）需在提交说明中写清影响范围。
- 项目元数据保留在 `project.yaml`，README 说明用途、当前状态、安装、启动、验证命令及配置项。
- 根目录 `README.md` 是仓库主项目说明文件；不要在子目录新增 README。模块说明、迁移边界和当前状态统一写入根 README 或本文件。补充说明、设计、草案和历史记录统一放入 `docs/`，导航位于 `docs/index.md`。原 `README.v2.md` 已按用户要求归入 `docs/readme-v2-draft.md`，作为并行排版草稿保留；在用户明确决定替换前，不要删除或用它替换主 README。
- 根目录 `DESIGN.md` 是前端视觉唯一事实源；不要在 `frontend/` 或模块目录维护第二份设计锚。
- `python_backend/modules/` 与 `frontend/src/modules/` 是能力边界目录。新增模块先建立接口与验证，再迁移旧实现；模块之间不得直接读取彼此的数据库细节。
- 模块命名保持前后端对应：`memory`、`retrieval`、`storage`、`context_engineering`、`skills`、`mcp`、`execution`、`workspaces`、`artifacts`、`intent`；`execution` 统一承载脚本、EXE 和后台任务执行能力；`intent` 统一承载意图目录与意图分类（关键词粗筛 → embedding 向量召回 → 大模型判定的三级级联，含置信度分级）；配置决策模型后该层改走 System One 协议（`modules/intent/decision.py`，阿里云百炼 decision-model-preview，与 TypeSafe Jev 同接口），一次前向同时给出意图与诉求歧义度，门闸按歧义度判断是否澄清；置信度不足时由门闸转成需求澄清，用户作答后作为新一轮对话重新进入级联。
- 运行数据及生成文件统一保存在被 Git 忽略的 `data/` 目录；真实配置遵循下方私密信息规则。
- 仓库根 `skills/<技能名>/` 存放技能包（`SKILL.md` + 可选 `references/`），技能正文控制在 8000 字符内；机器人只能绑定 `data/skills/` 里已安装的技能（`SkillRegistry.install_from_dir` 或 `/skill/upload`），机器人记录落在 `data/harness-bots.db`。`python -m python_backend.seed_bots` 是本地数据种子入口：把仓库技能（`requirement-analysis`、`hotline-tdd`）包装进 `data/skills/` 并登记「需求分析助手」机器人，可重复执行。
- 需求级澄清门闸落在 `modules/intent/requirement.py`：绑定 `requirement-analysis` 技能的机器人先判需求说不说不清，说不清就发 `clarify` 事件（三个理解方向 + 自由输入），上一轮刚澄清过时不再追问；用户在回答助手上一轮提问时也不重复澄清；通用意图门闸保持原有行为。
- 机器人绑定需求分析技能时，聊天推荐项里始终带一条「按 TDD 把这些需求写成测试」，从第一轮提问起就给。推荐项是结构化的 `{"label": ..., "skill": ...}`：标签文案只由 `modules/execution/engine.py` 定义，前端按 `skill` 字段切到技能助手（`frontend/src/modules/requirement/handoff.js`），两端不再各写一份同一句话。
- 需求正文随会话交接，不靠前端传：需求助手产出的那轮回答在 `thinking` 里打上 `需求条目` 标记，技能流按标记取最近一次需求正文注入提示（`engine.py` 的 `_requirement_brief`），技能助手因此能直接看到 FR/NFR 与验收条件。
- 两端需求契约一致：需求助手每一轮都用最终格式编号输出（`FR-001`/`NFR-001`/`SC-001` + Given/When/Then），没定的部分在同一条里标 `[NEEDS CLARIFICATION: ...]`，不写「待定稿后编号」这类占位说法；TDD 技能接受带 `NEEDS CLARIFICATION` 的草稿，已定稿条目照常出测试清单，未定稿条目单列「待确认」，不自己补默认值、也不因为是草稿就说没拿到需求。交接提示里明说草稿状态（`engine.py` 的交接段），避免助手否认已收到。
- 技能助手（TDD）阶段不另起输入框：底部对话框整块由技能接手——候选答案面板与输入框都留在底部那块区域，顶部加 `.skill-bar` 标识、输入框占位改成「在这里回复技能助手…」，文案集中在 `frontend/src/modules/skills/composer.js`；模式条保留以便切回普通对话，其余模式底部输入区不变。候选答案面板抽成 `frontend/src/modules/requirement/OptionPanel.vue`。
- 底部输入区容器不铺背景：`.composer-area` 背景透明、无阴影，只有输入框（`.composer-box`）和候选面板自己带底色，消息流直接透过，不要把输入区容器扩成一大块。
- 交接口令由后端认定：`engine.stream` 开头用 `_is_tdd_handoff` 判定 query 是「按 TDD 把这些需求写成测试」时把本轮 agent 置为 `skills`，前端漏切模式也照走技能流；同时用 SSE `agent` 事件把本轮实际助手类型告诉前端，前端据此切模式条、换底部输入区形态。会话列表与详情的 `agentType` 取**最后一条**消息（标题仍取第一条），否则「先澄清后进 TDD」的会话重开会被标成对话助手。
- 推荐项在会话历史里存的是字符串：后端序列化时统一升级成结构化项（`python_backend/modules/skills/handoff.py`），这样旧会话点「按 TDD 把这些需求写成测试」同样能切到技能助手。
- 助手正文里「编号问题 + 其下候选答案」的候选答案会被前端抽走（`frontend/src/modules/requirement/question-options.js`），正文只留问题，普通列表原样保留；抽出的候选显示在输入框上方的多选面板（每题从 A 重新编号，可跨题多选），点「发送所选」切到技能助手，把 `<问题>——<字母>. <候选>` 直接交给 `hotline-tdd` 继续追问（不再拼前缀文案）；面板只跟随最新一轮回答，用户发消息即清空。
- 需求分析技能包在 `skills/requirement-analysis/`：正文按“状态诊断（R0 只有方案没有问题 → R1 方案先行 → R2 需求含糊 → R3 隐藏约束 → R4 范围蔓延）+ 四阶段提问（问题发现 → 需求澄清 → 约束发现 → 范围定义）”组织，正文控制在 8000 字符内，深度内容放 `references/`（diagnosis.md、templates.md、checklist.md）；升级后仍要过 `catalog.validate` 与 `security_scan`。
- 机器人作为工具登记在 `harness_tool`（`source='agent'`，`input_schema.agent.bot_id` 指向机器人），由 `modules/execution/agent_tool.py` 装配成工具并挂到技能智能体的工具列表；调用复用 `prepare_tool_call` 的白名单、参数校验与审批链。子会话不落库，澄清答案由调用方带 `clarification` 参数回传。设计与实现记录见 `docs/agent-as-tool-design.md`。
- 机器人的开关是全局语义：`BotStore.enabled_bot()` 返回当前开启的机器人，同一时间只留一个（开启新的会在 `update`/`create` 里关掉其余），开启后所有会话都复用它的人设与技能，会话绑定只作为没有开启机器人时的回退。机器人页左侧栏列出机器人并各带一个开关；列表和详情都不展示角色指令，只有编辑表单里能改。
- 不擅自创建嵌套 Git 仓库或子模块。历史嵌套仓库 `projects/ai/dodo-agent` 已并入本仓库，其提交历史备份在 `data/dodo-agent-history.bundle`（Git 忽略，仅供恢复参考）。
- 交付前执行验证命令：`python -m compileall python_backend`、`python skill-center/test_center.py`、`npm --prefix frontend run build`（改动前端时）。改了意图或执行链路时补跑 `python -m unittest python_backend.test_agent_gate python_backend.test_requirement_gate`。文档修改仅核对与现有目录和命令的一致性。未经明确要求，不移动或重构现有目录结构。
- 本机没有可用的 MySQL，`import python_backend.fastapi_app` 会在 `PgVectorStore` 连接处抛 `Access denied`，所以整包导入失败不代表代码有问题。要验证路由与接口，用临时目录里的 store 单独装配 `api/routers/*` 的工厂函数（`create_*_router`）再打请求；测试用 `F:\Hotline\.venv\Scripts\python.exe` 运行。
- 本机 8888 后端由两个进程组成：网关 `python -m uvicorn main:app --host 127.0.0.1 --port 8888` 与执行 Worker `python -m python_backend.modules.execution.worker`。Java 启动时会在「静态寻址 + 本机回环 + 端口空闲」条件下自动拉起这两个进程（`hotline.python.launch.*`，可用 `HOTLINE_PYTHON_AUTOSTART=false` 关闭），Java 退出时连同子进程一起回收；Python 已在运行时只复用不重复拉起。只起网关时 `/agent/*/stream` 返回 503（Worker 未运行），`/health/ready` 会显示 `executionWorker: unavailable`。

## 禁止外传的内容

- `.env`、`.env.*`、`*.env`，以及它们的备份、导出、压缩包和副本。只有已确认完全脱敏的 `.env.example` / `.env.sample` 可提交。
- 用户的真实服务地址（公网或内网 IP、域名、端口、连接字符串、部署地址）、API Key、密码、令牌、私钥和其他凭据，无论出现在哪种文件中。普通源码、文档、日志、截图或技能样本夹带这些信息也不得上传。
- 禁止通过 Git 暂存、提交、推送、PR 附件、发布产物或外部服务上传上述文件或内容；不得在消息、日志或工具输出中展示敏感值。

## 工作方式

- 本地运行可以使用私密配置，但必须留在本地；对外示例使用明确占位符。本地回环地址和公开第三方文档链接不属于用户私密服务地址。
- 新增包含真实服务地址的配置，保存为 `*.local.*`、`*.private.*`，或放入 `private/`、`secrets/` 目录，并确认 Git 忽略。不要把真实配置复制进可提交文件。
- 暂存和提交前，检查文件清单及敏感内容；不盲目执行 `git add .` / `git add -A`，不得使用 `git add -f` 绕过私密文件的忽略规则。发现敏感信息时先脱敏或将文件排除，再继续。
- 上传或推送前检查待发布内容及待推送提交历史；发现密钥或真实服务地址时停止该次上传，处理泄露来源。不能通过 GitHub 解除密钥拦截来绕过本规则。
- `.gitignore` 不会自动移除已跟踪文件，也不会清理历史提交。取消跟踪时保留本地文件；清理历史涉及改写提交，须有用户明确授权，不擅自改写或强推。
- 后续修改配置、文档、构建或发布流程时，始终保留本规则及忽略规则。
- 协作开发使用独立分支；代码或文档先提交到个人分支，合并到主分支时再处理冲突。

## 文档维护规则

- 文档必须描述当前代码和可验证命令；历史方案、已废弃技术栈和未实现能力不得继续作为现状说明。
- 规划内容只保留在根 README 的规划小节或明确标注为草案的文档中；功能完成后及时删除过时规划，避免与代码重复描述。
- 修改文档后至少核对路径、启动命令、端口、模块名称和验证命令；不复制 `.env`、真实服务地址或运行数据到文档。

