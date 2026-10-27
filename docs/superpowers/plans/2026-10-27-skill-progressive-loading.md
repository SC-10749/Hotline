# LangChain 工具调用与自定义 Skill 渐进披露 Implementation Plan

> **状态：四阶段实现已完成，离线测试通过；替代本文件此前的手写 Agent 循环方案。未连接真实模型服务。**
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 不自动提交、推送或创建分支；代码实施前按用户授权确认独立分支。

**Goal:** 用 LangChain 处理当次模型—工具调用循环，自行实现“技能摘要进入消息上下文，正文及资料按需读取”，且明确解耦模型、执行、上下文与技能内容。

**Architecture:** 现有 agents.py 仅作为模式分流和旧接口适配入口。LangChain 集成放 execution，纯上下文格式化放 context_engineering；现有 skills.py 提供技能目录和受限资源访问，skill_center.py 保有数据库细节。仓库根 skills/ 仅存技能包，不放 Agent 基础设施。

**Tech Stack:** Python >=3.11、现有 FastAPI、LangChain create_agent、OpenAI-compatible 模型适配器、SQLite、unittest。仅工具循环使用 LangChain，不接 LangChain history、checkpointer、持久化记忆或 LangSmith 云端追踪。

**Spec:** 本文件“设计约定”章节，来自当前对话。实现预算和新接口是拟定默认值，不代表已实现或完全复刻 Codex。

## 设计约定

1. 根 `skills/` 是仓库技能包来源，现有技能为 `skills/hotline-tdd/SKILL.md`。不移动、修改该开发流程技能；它用于验证发现和读取，不代表 Agent 已具备执行测试或改代码的工具。
2. 保留现有 `data/skills/` 安装包来源、技能中心项目绑定来源；配置分别管理仓库技能根和原安装目录，不覆盖 `SKILLS_DIRECTORY` 的现有语义。
3. 首次消息上下文只包含技能 ID、名称、摘要和逻辑入口，不包含正文。已有 SKILL.md 的 YAML frontmatter 可以被扫描解析，但不能为枚举目录加载正文或附属资料。无缓存时只解析有界头部。
4. 摘要目录位于 system 消息，不位于 read_file 的工具描述；技能名不是工具名。正文和资料通过通用受限 read_file 以工具结果进入当前模型循环。
5. URI 使用 `skill://<request-local-opaque-id>/SKILL.md`；后台映射至具体源、版本和技能根。附属资料采用同根 URI。模型不获得宿主机真实路径或任意文件读取能力。
6. LangChain create_agent 拥有模型—工具循环，我们不再手写第二套循环。工具注册表只包含实际提供的工具，第一版为 read_file。
7. 每次用户请求独立执行，只提供当前输入及当前技能目录。循环中的 assistant/tool 消息临时保留，但不读取历史问题答案、不接 checkpointer、不建立 history 服务。
8. 现有会话 ID、停止接口及问答结果保存可继续作为外层兼容行为，不等于把历史重新传给 LangChain。其他 Agent 模式不迁移。
9. 不增加脚本执行、任意 Shell、动态工具安装、多 Agent、工作流引擎、向量检索、跨请求缓存或通用事件总线。

## 当前实现与约束

- `agents.py` 的 ModelClient.chat 只返回文本；stream 在 skills 模式先 select，_fallback 再注入 prompt_block 正文。这条路径需被新实现替换，而非在旁边叠加一条循环。
- `skills.py` 的 SkillRegistry 目前只扫描配置安装目录的元数据，不直接发现根 skills/*/SKILL.md。
- `skill_center.py` 的 runtime 查询返回完整内容；新目录接口必须直接投影元数据，不能先查询正文再丢弃。
- 根 `skills/README.md` 将该目录标注为可复用 Codex 技能来源；新增业务说明只更新根 README，不新增子目录 README。
- 仓库已有 execution/context_engineering/skills 能力模块占位。这里的根 skills/ 是技能包目录，不等于 python_backend/modules/skills；本期不在后者新增实现。
- 项目已跟踪 uv.lock；新增依赖必须同时维护 pyproject.toml、requirements.txt 和 uv.lock，不只修改其中一份。
- 当前系统 python3 为 3.9，未定位到 python/uv 命令；实施前定位可用 Python >=3.11，必要时使用用户已有的本地运行时，不在本次规划中安装依赖。

## Global Constraints

- 不读取或展示 .env、真实密钥、真实服务地址；不记录请求认证头、完整模型请求/响应。离线测试使用临时目录和假模型，不调用真实外部服务。
- 不新增或接入 LangChain conversation history、checkpointer、数据库记忆、自动历史压缩或会话恢复。
- modules/execution 不导入 agents.py；modules/context_engineering 不导入 LangChain、FastAPI 或数据库。
- 模型工厂不发现技能、不组装提示词、不执行工具；skills.py 不导入 LangChain 或模型客户端。
- execution 通过传入的资源读取函数访问技能，不直接访问 Catalog.db 或查 SQLite；SQL 仅由 skill_center.py 管理。
- 技能内容不能改变工具白名单、系统权限或资源边界。描述按数据编码并转义，正文保留工具来源，不提升为全局 system 指令。
- 保留旧技能安装、启停、版本绑定、灰度和 runtime 接口。新 skills 路径不再调用 select/prompt_block；旧接口继续服务旧测试或外部调用。
- 不新增前端代码、不移动现有目录、不修改 .env，不修改既有表结构；运行数据留在忽略的 data/。

## 模块和文件边界

### 技能包：根 skills/

仅 SKILL.md、references/、assets/、scripts/ 等技能内容。本期不创建 runtime.py、runner.py、模型客户端或工具循环到此目录，也不新增样例技能；测试样例全部使用临时目录。

### 模型适配：新增 python_backend/llm.py

- 唯一职责：从现有 Settings 创建 LangChain ChatOpenAI 模型适配器，适配已有 OpenAI-compatible 配置。
- 接口：`build_chat_model(settings: Settings) -> BaseChatModel`。
- 先检查配置再实例化；缺配置、请求失败、模型不支持 tools 均返回明确的脱敏错误，不伪装为成功。
- 不修改普通模式现有 ModelClient；首期只让新的 skills 路径调用此工厂，避免顺带迁移所有模型调用。

### Agent 执行：新增 python_backend/modules/execution/langchain_agent.py

- 唯一职责：创建/调用 create_agent，并输出与旧前端格式无关的执行事件。
- 接口：`run_agent(model: BaseChatModel, system_prompt: str, query: str, tools: Sequence[BaseTool], is_stopped: Callable[[], bool]) -> Iterator[AgentEvent]`。
- AgentEvent 在同文件定义，仅 type 为 text/error/done 及对应内容，不输出模型隐藏思考或原始 tool 参数。
- 不知道 SkillRegistry、Catalog、技能扫描目录，不读取或保存会话历史，不直接生成 SSE。
- 本期输入在每个请求开始时固定，不需 middleware；无需求不创建动态上下文框架。

### 工具适配：新增 python_backend/modules/execution/tools.py

- 唯一职责：把受限文本读取函数包装成 LangChain tool，不自行实现文件授权。
- 接口：`build_read_file_tool(reader: Callable[[str, int, int], dict]) -> BaseTool`。
- 模型可见参数：`resource_uri: str, offset: int = 0, limit: int = 12000`。
- 只描述文件读取能力、分页与错误，不在 description 中列技能清单。

### 上下文组装：新增 python_backend/modules/context_engineering/skill_catalog.py

- 唯一职责：根据已授权摘要生成技能目录文本及使用规则，处理预算和转义。
- 接口：`render_skill_catalog(skills: Sequence[SkillDescriptor], max_chars: int = 8000) -> str`。
- 只依赖标准库和 skills.py 的轻量数据结构；不发现文件、不查数据库、不调用模型。
- 明确注明“技能是说明文档，不是工具；需要时用 read_file 读取入口”。

### 技能访问：修改 python_backend/skills.py

- 在现有管理服务补 `SkillDescriptor`、`SkillResourceSession`、目录发现与受限读取；不再额外拆多个技能运行文件。
- 接口：`SkillRegistry.open_resource_session(request_id: str) -> SkillResourceSession`。
- SkillResourceSession 暴露 `descriptors: tuple[SkillDescriptor, ...]` 和 `read_file(resource_uri: str, offset: int = 0, limit: int = 12000) -> dict`。
- SkillDescriptor 包含 id/name/description/version/entry_uri；本地 root 路径与数据库句柄仅存在后台映射，不可进入描述对象。
- 来源：根 skills/、现有安装目录、项目绑定 Catalog。来源限定在配置允许范围，不扫描 samples/、整个工作区、HOME 或任意传入目录。
- 请求内本地入口在首次读取时保存文本快照，继续分页不漂移；目录到首次读取间文件发生变化则拒绝并要求重试，不为提前算正文 hash 而读取正文。

### 技能中心数据：修改 python_backend/skill_center.py

- 新增 `runtime_metadata`：按项目与稳定 requestId 复用灰度规则，只返回元数据。
- 新增 `read_runtime_file`：校验已选版本访问范围并定点读取 SKILL.md 或 resources 中目标文本。
- 首次目录选择后固定版本；当前绑定升级不自动切换任务内版本；明确解绑、删除或禁用则拒绝后续读取。
- resources 是现有 JSON 字段，读取某份资源可需解析整个映射，但只将指定文本交给模型；不为物理文件级存储而重构数据库。

### 装配与旧接口：修改 python_backend/agents.py

- skills 分支创建资源 session、渲染 system 上下文、创建模型与 read_file 工具，调用 run_agent。
- 将 AgentEvent 转换为现有 thinking/text/error/complete 事件，继续由现有 FastAPI 适配 SSE。
- 在读取 history 和旧关键词匹配前分流 skills 模式；LangChain 输入只包含当前问题，不传已有 history。
- 原 chat/deep/file/ppt 分支保持不变；不把最终 LangChain AIMessage 的 tool_calls 当作回答文本。
- 无模型配置时明确不可执行且不回显正文；工具失败或请求停止不能写成业务执行成功。

## 依赖方向

```text
fastapi_app.py（现有 HTTP/SSE 入口）
    -> agents.py（装配与模式分流）
         -> llm.py（模型工厂）
         -> modules/execution/langchain_agent.py（LangChain 工具循环）
         -> modules/execution/tools.py（工具包装）
         -> modules/context_engineering/skill_catalog.py（纯上下文文本）
         -> skills.py（目录与资源访问）
              -> skill_center.py（Catalog 接口及 SQL）
              -> 仓库技能/安装包文件
```

execution 不反向导入 skills.py，通过 reader 注入实现解耦。禁止为了复用旧方法形成 agents -> execution -> agents 的环。

## 首期预算与生命周期

- 目录最多 8000 字符，稳定排序、按条目保留；缩短描述后仍超预算则明确报告省略，第一期不承诺大规模目录完全可发现。
- 单次 read_file 最多 12000 字符，返回 uri/text/next_offset/eof；文件最多 1 MiB，超限/二进制/非法编码明确报错，不静默截断。
- 每请求最多 8 次模型调用、16 次工具调用，工具文本累计最多 64000 字符；用 LangChain 内置限制 middleware 或其扩展接口实现，不手写第二套循环。
- 不依赖图 recursion_limit 作为唯一业务预算；具体所选版本的限制接口必须经过离线验证。
- 每次请求独立状态，不跨用户共享可变加载标志。重复读同一页先保证协议正确和内容可用，不为去重删减合法工具结果；完整预算照常计入。
- tool 并行访问时读取快照/预算更新须安全；第一期可显式串行执行，但不能假设框架必然串行。
- 在模型/工具边界检查停止；在途网络请求不承诺即时取消。取消后不得继续资源访问或产生成功事件。
- 默认不启用任何外部 tracing；执行前检查已有 tracing 开关是否会将内容外传，发现启用时先按私密信息规则处理。

## Review Focus

1. 根 skills/ 有 SKILL.md，但无安装元数据；必须可发现，同时不能把样例目录自动纳入。任务 1 覆盖。
2. 不同来源同名技能、灰度和绑定更新；使用独立逻辑 ID，任务内固定版本，解绑后撤销。任务 1、2 覆盖。
3. 路径编码、反斜线、symlink、私密文件及相对引用；授权限制在技能根，返回错误不暴露真实路径。任务 2 覆盖。
4. 模型幻觉工具名、并行/重复工具请求、供应商不支持 tools；白名单执行、限额和脱敏失败。任务 3 覆盖。
5. LangChain 自动带入历史、重复累计流式消息或工具输出混入答案；不接 history，仅输出最终答案可见增量。任务 3、4 覆盖。

## Task 1：独立技能目录与上下文

**Files:** 修改 config.py、skills.py、skill_center.py、test_center.py；新增 modules/context_engineering/skill_catalog.py、skill-center/test_skill_disclosure.py。

- [ ] 先写失败测试：临时仓库 skills/demo/SKILL.md 没有安装元数据也可发现；初始目录包含名称/摘要/逻辑入口、不含正文哨兵。
- [ ] 写 Catalog 元数据投影、绑定/灰度、空目录、同名不同来源和目录预算测试；扫描不包含 skill-center/samples。
- [ ] 配置新增仓库技能根字段，默认用源码根定位 skills，不依赖启动工作目录；原 skills_dir 安装目录不变。
- [ ] 实现元数据读取、SkillDescriptor、资源 session 的目录部分和纯目录渲染；禁止目录扫描时读取资源内容。frontmatter 采用有界头部解析，不顺带为此重构所有 YAML 处理。
- [ ] 跑目录测试和原技能中心测试，确认接口边界与兼容行为。

## Task 2：技能资源读取与安全

**Files:** 修改 skills.py、skill_center.py、test_center.py；扩充 test_skill_disclosure.py。

- [ ] 先写失败测试：入口正文、同根参考文档、中文分页、缺资源、只读访问；正文只在 read_file 请求后返回。
- [ ] 覆盖未知 URI、跨源 ID、绝对路径、URL 编码、反斜线、..、symlink 越界、.env/备份、private/secrets、二进制和超大文件；样例内容全部虚构。
- [ ] 覆盖本地内容变化、Catalog 选定版本升级、解绑、删除、灰度 requestId 一致性。区分升级固定版本和撤销授权。
- [ ] 实现 SkillResourceSession.read_file 与 Catalog.read_runtime_file；通过注册器调用 Catalog 接口，不从执行模块直接查库。
- [ ] 验证返回完整页和明确续读位置，不把参考文档一起附上，不在错误中泄漏真实路径；重复读取和并发读取有确定结果。

## Task 3：LangChain 模型与工具集成

**Files:** 新增 llm.py、modules/execution/langchain_agent.py、modules/execution/tools.py、skill-center/test_agent_tools.py；修改 pyproject.toml、requirements.txt、uv.lock。

- [ ] 定位 Python >=3.11 和可用依赖管理方式；确认模型适配器兼容现有 OpenAI-compatible 配置。依赖使用经解析验证的具体兼容版本，不凭空指定版本号。
- [ ] 先写假模型红测：第一轮请求无正文，模型调用 read_file 后下一轮获得正文，按需再读参考文档并最终输出。
- [ ] 用假传输验证模型配置映射但不连接真实服务；覆盖配置缺失、HTTP 错误和不支持工具协议，错误内容脱敏。
- [ ] 实现模型工厂和通用 tool 包装，再使用 create_agent 运行；没有手写 model -> tool -> model while 循环。
- [ ] 用内置或最小 middleware 添加调用/内容限额与停止边界；覆盖未知工具、参数错误、多 tool_calls、重复调用和并行预算。
- [ ] 使用 LangChain 流式接口时区分工具消息、最终文本和累计 chunk；AgentEvent 不输出工具文件全文或模型隐藏推理。并验证无需 checkpointer/history 即可运行。
- [ ] 检查执行模块不依赖 SkillRegistry/Catalog/Storage；reader 和模型均可替换为测试对象，测试不导入 FastAPI 应用或连接数据库。
- [ ] 将依赖更新同步到三个依赖文件，确保没有引入云端追踪配置或真实地址。

## Task 4：应用装配、模式隔离与交付

**Files:** 修改 agents.py、README.md；扩充 test_agent_tools.py、test_skill_disclosure.py。原则上不改 fastapi_app.py 的路由与 SSE 格式。

- [ ] 先写集成红测：skills 入口只接收当前问题，不调用 session_messages，不将上一轮答案传入 LangChain；现有结果保存不作为模型输入。
- [ ] 覆盖原 chat/deep/file/ppt 路由和事件结构不变；无模型时不读取/回显技能正文，停止/失败不产生误导性成功。
- [ ] 在 agents.py 装配目录、reader、模型和执行器；skills 模式不再 select/prompt_block，旧模式和旧 ModelClient 保留。
- [ ] 验证 root skills/hotline-tdd 的元数据可发现，但不会声称已经执行测试、脚本或修改代码。
- [ ] 更新根 README 当前能力、技能来源和验证命令；不新建子目录 README，不将已撤销方案作为现状。
- [ ] 执行以下验证；仅在离线测试通过后报告实现完成。真实模型效果/Token/耗时需另行本地验证，不冒充已测。

## 验证命令

以下 python 指已激活的 Python >=3.11 项目解释器：

```bash
python --version
python -m compileall python_backend
python skill-center/test_center.py
python skill-center/test_skill_disclosure.py
python skill-center/test_agent_tools.py
```

通过标准：编译无错误，全部 unittest 为 OK；假模型首请求只有目录和 read_file 定义，被请求的正文才进入后续工具结果；未请求资源不出现；新路径无 history 注入；旧模式协议不变。

本期不改前端，若实施时确有前端变更，另加 npm --prefix frontend run build。使用锁文件管理工具核对新增依赖与 uv.lock 一致；不因本机工具缺失就交付过期锁文件。

## 文件清单汇总

新增 6 个实现/测试文件：llm.py、execution/langchain_agent.py、execution/tools.py、context_engineering/skill_catalog.py、test_skill_disclosure.py、test_agent_tools.py。

修改 9 个现有文件：config.py、skills.py、skill_center.py、agents.py、test_center.py、pyproject.toml、requirements.txt、uv.lock、根 README.md。

不新增 skills/runtime.py 或 skills/runner.py，不重构所有 Agent 模式，不接入 history，不更改现有技能包内容。本计划文档更新另计。

## 自检与执行方式

- 四个任务覆盖目录、资源、框架执行、接口装配，Review Focus 各有对应测试。
- 模型适配、执行、上下文、技能访问依赖单向；没有 execution -> agents 回环，没有 skills -> LangChain 依赖。
- 默认由当前主 Agent 按任务逐项执行；用户未授权委派，不创建子 Agent。
- 四阶段代码已实现，使用 Python 3.12 本地隔离环境完成离线验证；未提交、推送或上传内容，未连接真实模型服务。具体结果见下方实施记录。

## 实施记录

- 已发现根 `skills/`、原安装目录和 Catalog 项目绑定来源；摘要和正文查询已分离。
- 已接入 LangChain 工具循环、受限 read_file、分页与执行限额；skills 模式不读取会话历史，其他模式保留原路径。
- 新增依赖固定为 LangChain 1.4.7、langchain-openai 1.7.3，依赖声明与 uv.lock 已同步。
- 离线验证：技能中心 6 项、渐进披露和资源安全 18 项、工具调用和入口兼容 17 项，共 41 项通过；compileall、锁文件一致性和已安装依赖兼容检查通过。
- 自查补充了只读 Catalog 连接，避免读取阶段创建数据库或执行迁移；补充了私密目录、特殊文件、版本撤销和灰度一致性测试。
- 不含 history、脚本执行、工作流引擎或逐 Token 输出；外部模型工具调用兼容性仍需使用用户本地配置单独联调。
