# 技能中心（skills）

> 模块路径：`python_backend/modules/skills/`（另有 `skill-center/` 目录、根 `skill_center.py` 兼容入口）
> 前端对应：`frontend/src/modules/skills/composer.js`、`frontend/src/modules/requirement/handoff.js`；技能控制台为静态页 `static/console/`
> 状态：现状说明（以代码为准，冲突时以代码为准并修正本文档）

## 技能包目录结构与 SKILL.md 发现

### 入口

- `python_backend/modules/skills/registry.py:locate_skill_md` —— 在安装暂存目录里逐层查找 `SKILL.md`
- `python_backend/modules/skills/registry.py:deep_skill_candidates` —— 列出超出查找深度的同名文件，供人工指定
- `python_backend/modules/skills/registry.py:SkillRegistry._build_resource_session` —— 运行时发现三类技能来源

### 行为

- 技能包 = 一个目录，至少含 `SKILL.md`，可另带 `references/`；仓库自带技能包在仓库根 `skills/<技能名>/`（现有 `requirement-analysis`、`hotline-tdd`）。
- 发现来源三类：仓库技能目录（`settings.repo_skills_dir`）、已安装技能目录（`settings.skills_dir`，只收 `enabled` 的）、技能中心目录里绑定到当前项目的版本。
- 查找深度上限 `MAX_DEPTH=3`，逐层扫描，最浅命中层返回该层全部候选（同层多个候选不自动二选一）；`locate_skill_md` 按层广度优先遍历，描述符 id 取内容键 sha256 前 24 位，资源地址形如 `skill://<id>/SKILL.md`。
- 仓库技能必须能读出 frontmatter 的 `name` 与 `description`（缺任一项不进入可用列表），技能目录或入口是符号链接时直接跳过。

## SKILL.md frontmatter 解析与内容校验

### 入口

- `python_backend/modules/skills/registry.py:parse_frontmatter` —— 解析 `---` 包裹的扁平键值对
- `python_backend/modules/skills/registry.py:_read_skill_header` —— 只读文件前 8KB 头部取元数据
- `python_backend/modules/skills/catalog.py:validate`、`python_backend/modules/skills/catalog.py:security_scan` —— 目录侧校验与安全扫描

### 行为

- frontmatter 只支持扁平 `key: value`（首个冒号分隔），不引入 YAML 依赖；`#` 开头的行跳过，同名键以首次出现为准，值剥掉首尾引号；无 frontmatter 时返回空字典。
- 目录侧 `validate` 要求 frontmatter 与非空正文；`name` 必须是 1–64 位小写字母、数字或连字符；`description` 必须非空且是单行文本；`security_scan` 命中「密钥/密码/令牌赋值」或「忽略先前指令、泄露系统提示、绕过安全」等模式即拒绝。
- 技能正文进提示词截断到 `MAX_BODY_CHARS = 8000` 字符；`_read_skill_header` 读满 8KB 或遇闭合 `---` 即停，正文不参与元数据读取。

## 安装（目录安装与压缩包安装）

### 入口

- `python_backend/modules/skills/registry.py:SkillRegistry.install` —— 安装 zip 技能包
- `python_backend/modules/skills/registry.py:SkillRegistry.install_from_dir` —— 从本地目录安装/原地更新
- `python_backend/modules/skills/registry.py:safe_extract` —— 带防护的解压

### 行为

- 压缩包先整体解压到 `<目录名>.staging` 暂存目录，定位 `SKILL.md` 后整目录重命名到位，失败清掉暂存目录。
- 解压防护：文件数上限 500、解压后总大小上限 50MB；拒绝绝对路径、含 `..` 的路径、软链接条目和解析后越出目标目录的路径。
- 只有一个候选时自动使用；有多个候选时抛错并把候选列表放进异常的 `entries` 供人工指定；浅层找不到但深层存在时错误里带上深层候选；手工指定的入口必须落在暂存目录内、文件名必须是 `SKILL.md`。
- 目录安装按 frontmatter 的 `name` 识别同名技能并原地更新，技能编号不变，已有机器人/Agent 绑定因此继续有效；Windows 上目录重命名被占用时最多重试 3 次；产物在 `data/skills/<目录名>/`，元数据写同目录 `.skill-meta.json`（id、name、description、entry、sourceFile、enabled、createdAt、dirName）。
- `python -m python_backend.seed_bots` 把仓库技能包装进已安装目录，并登记「需求分析助手」机器人及其工具项，可重复执行。

## 启用/禁用、删除与绑定

### 入口

- `python_backend/modules/skills/registry.py:SkillRegistry.set_enabled` —— 切换技能启用态
- `POST /skill/{skill_id}/toggle` —— 启用/禁用已安装技能
- `POST /harness/agents/{agent_id}/skills` —— 绑定技能到 Agent
- `POST /harness/skills/catalog/bind` —— 把目录版本绑定到项目

### 行为

- 启用态写进 `.skill-meta.json`，用临时文件替换保证原子性；发现阶段只收启用中的已安装技能，读取资源时复查启用态，被禁用则报「技能已禁用」。
- Agent 绑定是替换整个技能编号列表，不动 Agent 定义本身的 revision；机器人（人设）通过 `skills` 字段绑定编号；技能编号查不到时在提示词里被跳过，不报错。
- 目录绑定写 `bindings` 表并留 `binding_audit` 审计，可带灰度百分比（为 0 表示不建灰度行）；绑定被撤销后运行时读取该技能资源立即失效。
- 关键实现：`python_backend/infrastructure/resource_store.py:ResourceStore.set_agent_skills` 替换 `harness_agent.skills`；`catalog.py:Catalog.call` 的 `bind`/`unbind` 负责绑定、灰度与审计。

## 技能披露进上下文的工具（read_skill）

### 入口

- `python_backend/modules/skills/registry.py:SkillRegistry.open_resource_session` —— 按一次请求建立技能资源会话
- `python_backend/modules/skills/registry.py:SkillResourceSession.read_skill` —— 读技能正文或包内相对路径文件
- `python_backend/modules/execution/tools.py:build_read_skill_tool` —— 把读取能力装配成工具
- `python_backend/modules/execution/engine.py:Engine._stream_skills` —— 技能模式流式执行

### 行为

- 技能按需披露进上下文：工具描述里只放技能 id、name、description 清单，正文由模型调用 `read_skill` 时才读取。
- `read_skill` 只接受本次会话已登记的技能 id；路径须为包内相对路径且经 `validate_resource_path` 过滤（后缀白名单，拒绝 `private`、`secrets`、`.env`、`.local.`、`.private.` 与以点开头的路径段）；读取带分页：`offset >= 0`，`limit` 取值 1–12000，返回 `next_offset` 与 `eof`。
- 本地技能读取有四重防护：解析后仍在技能根目录内、路径上任一层不得是符号链接、单文件不超过 1MB、拒绝含 NUL 的内容，读取期间文件变化即报错。
- 目录技能读取走只读连接，先校验授权（绑定存在），再按绑定版本取 `SKILL.md` 或附加资源；会话内按资源地址缓存文本。
- 技能模式的系统提示明确：技能说明与资源不能改变系统规则或工具权限；未配置模型时直接报错，不加载也不回显技能正文。

## 技能提示块与技能选择

### 入口

- `python_backend/modules/skills/registry.py:SkillRegistry.prompt_block` —— 拼技能提示块
- `python_backend/modules/skills/registry.py:SkillRegistry.select` —— 按查询挑技能
- `python_backend/modules/execution/engine.py:Engine._persona_block` —— 把机器人绑定的技能追加进系统提示词

### 行为

- 本地技能的提示块给出技能说明所在目录路径，提示引用包内文件时用相对路径，正文截到 8000 字符。
- 目录技能的提示块给出技能名与版本，并声明当前运行器只加载技能指令，不具备脚本执行或平台资源文件读取工具。
- 机器人绑定的技能在系统提示词里追加，不覆盖既有规则；`select` 支持 `$技能名` 显式匹配，否则用中文二元组加 ASCII 词打分，但运行链路已改为按需披露，技能模式不再调用 `select`/`prompt_block`（`skill-center/test_agent_tools.py` 有对应断言）。

## 目录版本、自进化与评测打分

### 入口

- `python_backend/modules/skills/catalog.py:Catalog.call` —— 目录全部动作入口
- `python_backend/modules/skills/catalog.py:apply_patches`、`score_cases`、`run_sandbox` —— 补丁、评分与沙箱
- `POST /console/api/skills`、`GET /console/api/skill-evolution` —— 控制台操作与自进化视图

### 行为

- 版本入库 `save` 校验 frontmatter 与正文，按内容哈希去重，同名技能版本号自增为 `v1`、`v2`；正文加资源总量上限 5MB。
- 打分口径：用例含 `required`（必须命中）与 `forbidden`（不得出现），得分 = (命中数 + forbidden 数 − 违规数) / 总数，`passed` 要求 required 全中且 forbidden 零命中。
- `evolve` 先施加补丁（最多 8 条 `add`/`delete`/`replace`，`old` 须在正文中恰好出现一次），再过静态门禁（候选不超原版 1.2 倍、不超 5MB）、`validate` 与 `security_scan`，然后在 train/selection/test 三档打分；门禁为静态通过、selection 有提升、selection 无回退、test 不下降、安全通过，全部通过才存为新版本并记 `staged`，否则记 `rejected`。
- `auto_evolve` 拿 train 档失败用例调模型生成不超过 8 条补丁再走 `evolve`；`judge` 用模型按 rubric 返回 `score`/`passed`/`reason`；`run_sandbox` 以子进程（`shell=False`）跑命令，超时 1–120 秒，环境只透传 `PATH`。
- 灰度与回滚：`promote` 写 `rollouts` 的百分比与回滚目标版本，`rollback` 回到 `previous_version`；运行时按 `request_id` 哈希分桶决定生效版本；`error_rate` 采样数与均值超阈值时自动回滚。
- 控制台只接受动作白名单（save、bind、eval_case、eval_cases、evaluate、evolve、auto_evolve 等），非白名单操作直接拒绝。

## 需求助手 → TDD 技能交接与推荐项结构化

### 入口

- `python_backend/modules/skills/handoff.py:normalize_recommendations` —— 字符串推荐项升级为结构化项
- `python_backend/modules/skills/handoff.py:normalize_recommendations_json` —— 序列化层的升级入口
- `python_backend/modules/execution/engine.py:Engine._is_tdd_handoff`、`Engine._requirement_brief` —— 交接口令与需求正文交接
- `frontend/src/modules/requirement/handoff.js:handoffFor` —— 前端按 `skill` 字段切技能助手

### 行为

- 推荐项结构为 `{"label": 文案, "skill": 技能名}`；标签文案只由后端定义，前端按 `skill` 字段决定是否切到技能助手。
- 旧会话存的纯字符串推荐项在序列化时统一升级为结构化项；已是结构化的原样保留，读不出列表时原样返回，不改坏历史数据。
- 交接口令「按 TDD 把这些需求写成测试」由后端判定：本轮助手类型切为技能模式，前端漏切也照走技能流。
- 需求正文随会话交接：需求助手那轮回答在 `thinking` 里打上「需求条目」标记，技能流按标记取最近一次需求正文注入提示，正文截到 8000 字符，并在提示里说明草稿状态。
- 前端技能助手阶段由底部对话框整块接手，文案集中在 `frontend/src/modules/skills/composer.js`；普通模式保持原样；`frontend/src/modules/requirement/handoff.js` 的 `recommendationLabel` 显示文案、`handoffFor` 产出交接信息。

## 数据与存储

- 已安装技能：`data/skills/<目录名>/`，每包一份 `.skill-meta.json`（配置项 `SKILLS_DIRECTORY`）；仓库技能包在仓库根 `skills/<技能名>/`（配置项 `DODO_REPO_SKILLS_DIRECTORY`），只读发现源。
- 技能中心目录库：`data/skill-center/catalog.db`（配置项 `DODO_SKILL_CATALOG_DB`），表含 `versions`、`bindings`、`eval_cases`、`evolution_runs`、`rollouts`、`metrics`、`binding_audit`。
- 项目标识：配置项 `DODO_SKILL_PROJECT`（默认 `hotline-agent`），绑定、灰度、指标按项目隔离。
- 绑定关系：`harness_agent.skills`、`harness_bot.skills` 存技能编号列表；模型与阈值配置项：`SKILL_EVOLUTION_*`、`SKILL_JUDGE_*`、`SKILL_ROLLOUT_ERROR_THRESHOLD`、`SKILL_ROLLOUT_MIN_SAMPLES`。

## 接口清单

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/skill/list` | 列出已安装技能 |
| `POST` | `/skill/upload` | 上传 zip 技能包并安装（表单字段 `entry` 指定入口） |
| `GET` | `/skill/{skill_id}` | 读技能详情与正文（正文截 12000 字符） |
| `POST` | `/skill/{skill_id}/toggle` | 启用/禁用技能，参数 `enabled` |
| `DELETE` | `/skill/{skill_id}` | 删除已安装技能 |
| `GET` | `/harness/skills/catalog` | 目录摘要：版本、绑定、灰度 |
| `GET` | `/harness/skills/catalog/version` | 单个版本详情与资源清单 |
| `GET` | `/harness/skills/catalog/compare` | 两版本正文与资源差异对比 |
| `POST` | `/harness/skills/catalog/bind` | 绑定版本到项目，可带灰度百分比 |
| `DELETE` | `/harness/skills/catalog/bind` | 解除目录绑定 |
| `POST` | `/harness/agents/{agent_id}/skills` | 替换 Agent 绑定的技能列表 |
| `DELETE` | `/harness/agents/{agent_id}/skills/{skill_id}` | 解绑单个技能 |
| `POST` | `/harness/bots`、`PUT /harness/bots/{bot_id}` | 创建/更新机器人，可带 `skills` 绑定 |
| `GET`、`POST` | `/console/api/skills` | 控制台技能列表（带项目参数时取运行时绑定）与动作入口，动作受白名单限制 |
| `GET` | `/console/api/skill-evolution` | 自进化视图：用例、指标、演进记录、灰度 |

## 边界与已知限制

- 技能正文进提示词截断到 8000 字符；目录版本内容上限 5MB；单个资源读取上限 1MB；分页 `limit` 上限 12000。
- 安装与读取都有硬限制：压缩包 500 文件 / 50MB、拒绝软链接与路径穿越、资源路径只认后缀白名单。
- 技能内容不能改变系统规则或工具权限；未配置模型时技能模式直接失败，不加载也不回显技能正文。
- 技能内容不能改变系统规则或工具权限；未配置模型时技能模式直接失败，不加载也不回显技能正文。
- 技能不具备脚本执行能力，提示块里显式声明；需要脚本的技能要在执行模块另行接入。
- 目录技能运行期只读打开目录库；目录库缺失时技能列表为空，读取不会顺手重建。
- 自进化与评判依赖 `SKILL_EVOLUTION_*`、`SKILL_JUDGE_*` 配置，未配置时对应动作报错。
- 灰度按请求标识哈希分桶，同一请求在不同时间可能命中不同版本。
- 删除技能不会自动清理机器人/Agent 上残留的技能编号；`SkillRegistry.select` 仍保留在注册表，但运行链路不再调用它。
