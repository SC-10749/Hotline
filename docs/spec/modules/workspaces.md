# 工作区与资源（workspaces）

> 模块路径：`python_backend/modules/workspaces/`（`context.py`） ｜ 前端对应：`frontend/src/modules/workspaces/`（`paths.js`、`paths.test.js`）
> 持久化与路由：`python_backend/infrastructure/resource_store.py`、`python_backend/api/routers/resources.py`、`python_backend/api/routers/workspace_import.py`
> 状态：现状说明（以代码为准；规格与代码不一致时以代码为准并修正本文档）

## 工作区创建与元数据

### 入口

- `python_backend/infrastructure/resource_store.py:ResourceStore.create_workspace` / `update_workspace` / `list_workspaces` / `get_workspace`
- `POST /harness/workspaces` / `GET /harness/workspaces` / `GET /harness/workspaces/{workspace_id}` / `PUT /harness/workspaces/{workspace_id}`

### 行为

- ID 形如 `workspace-<uuid4 前 12 位>`；字段为 `workspace_id`、`name`、`repository`、`branch`、`status`、`revision`、`created_at`、`updated_at`，列表按 `updated_at` 倒序。
- `branch` 默认 `main`，`status` 默认 `ready`，`repository` 默认空串（纯本地目录工作区）；`name`、`branch` 去空格后不能为空（否则 422），长度上限 120 / 200，`repository` 上限 500。
- 更新必须带 `revision`，不一致抛 `ResourceConflictError` 并转 409；更新只改 `name`、`repository`、`branch` 并把 `revision` 加一，`status` 不变。

### 关键实现

- `python_backend/api/routers/resources.py:WorkspacePayload` / `WorkspaceUpdatePayload` —— 请求体字段与校验；`ResourceStore._initialize` —— 建表并给旧库补 `revision` 列

## 本地目录与受管检出的根目录解析

### 入口

- `python_backend/modules/workspaces/context.py:resolve_workspace_root` —— 工作区文件根目录
- `python_backend/infrastructure/resource_store.py:ResourceStore.resolve_local_repository` / `managed_checkout_dir`

### 行为

- `resolve_workspace_root`：空 ID 或工作区不存在返回 `None`；检出记录存在且 `status == 'ready'` 时返回该检出目录的绝对路径，否则回落到 `resolve_local_repository(repository)`。
- `resolve_local_repository`：相对路径先按当前工作目录解析、再按资源库所在目录解析，只接受真实存在的目录；导入的工作区把导入目录绝对路径写进 `repository`，因此走本地目录解析。
- `managed_checkout_dir` 固定为 `<data_dir>/workspaces/<workspace_id>/repo`；ID 含 `/`、`\`、`..` 报 `invalid_workspace`，解析后越界报 `invalid_path`。

### 关键实现

- `ResourceStore._resolve_repository` —— 相对路径的两处候选根。已知不一致：检出写入 `checked_out`（`ResourceStore.checkout_workspace`），而 `context.py:resolve_workspace_root` 判 `ready`，受管检出目录不会被根目录解析采用。

## git 检出（克隆分支、落在受管目录、失败不报成功）

### 入口

- `python_backend/infrastructure/resource_store.py:ResourceStore.checkout_workspace` —— 克隆、检出分支、写快照
- `POST /harness/workspaces/{workspace_id}/checkout` / `GET /harness/workspaces/{workspace_id}/checkout`

### 行为

- 目标目录已存在先整体删除，再 `git clone --depth 1 --no-single-branch` 到受管目录，不碰用户自己的目录；目标分支为空按 `main` 处理；git 调用用数组传参、`shell=False`、关闭交互式口令（`GIT_TERMINAL_PROMPT=0`、`GIT_ASKPASS=echo`）。
- `git checkout` 失败抛 `CheckoutError(reason='branch_not_found')` 并附远端分支列表（最多 10 个）；克隆失败为 `unreachable`，git 不可用为 `git_unavailable`，命令超时（120 秒）为 `timeout`；成功后记录实际分支与短 commit，并立刻生成一次快照（变更类型全为 `tracked`）。
- 路由先校验 `repository`：为空返回 400；不匹配 git 地址模式（`GIT_URL_PATTERN`，覆盖 http(s)/ssh/git/file 与 `user@host:`）时若能解析为本地目录，返回 400 且正文带 `本地目录无需检出`、`directory`、`files`；失败时检出记录写成 `status='error'`，状态接口返回 `checkedOut=false`，成功返回 `checkedOut=true` 及 `branch`、`commit`、`checkoutDir`、`checkedAt`、`message`。

## 工作区规则（AGENTS.md）加载与隔离目录 root 参数

### 入口

- `python_backend/modules/workspaces/context.py:load_workspace_rules` —— 读工作区规则
- `python_backend/modules/execution/engine.py:AgentEngine._read_workspace_rules` —— 调用方，透传 `workspace_root`；`python_backend/workers/execution_worker.py:build_engine` —— 注入 `workspace_rules_reader`

### 行为

- 工作区不存在抛 `ValueError('工作区不存在')`；`workspace_id` 为空返回空串。
- 传入 `root` 时读该目录下的 `AGENTS.md`（子任务隔离副本），不传时用 `resolve_workspace_root` 求根，两者都取不到根返回空串。
- `AGENTS.md` 不存在或是符号链接返回空串，超过 64000 字节抛 `ValueError('工作区规则超过读取上限，请精简规则或调整工作区')`，编码用 `utf-8-sig`；调用方按签名探测，读取器只接受一个参数时按原样调用，只接受两个参数时才传隔离目录。

### 关键实现

- `python_backend/modules/execution/parallel.py:allocate_task_workspace` —— 子任务隔离目录三级降级（git 仓库用 worktree、普通目录复制、不可用时只留独立产物目录）；`ExecutionWorker._prepare_workspace` 把 `workspace_root` 写回运行记录

## 工作区文件导入与私密路径/穿越拒绝

### 入口

- `POST /harness/workspaces/import` / `GET /harness/workspaces/{workspace_id}/files` —— `python_backend/api/routers/workspace_import.py:create_workspace_import_router`
- `frontend/src/modules/workspaces/paths.js:workspacePathAllowed` —— 前端选文件时的过滤口径

### 行为

- 要求名称非空、文件数 1 到 5000，否则 400；路径统一把反斜杠换成正斜杠，大小写折叠后重复的路径返回 `工作区包含重复路径`。
- 路径命中 `python_backend/modules/context_engineering/privacy.py:private_path`（私密路径判定的唯一事实源，前后端口径一致：含 `..`、私密目录名、`.env` 类名、`.local`/`.private`、密钥后缀、绝对路径、带冒号路径）或为空、为 `.` 时返回 `工作区包含私密文件或不安全路径`。
- 落盘先写暂存目录 `.pending-<uuid>`，逐 1 MB 分块写，单文件超 50 MB 或累计超 512 MB 返回 413；写完把暂存目录改名为 `<uuid>` 目录并以其绝对路径创建工作区（`branch` 取 `main`），任何异常都会清理暂存与目标目录。
- 文件列表按根目录遍历，单文件上限 50 MB，最多 5000 条，超出时 `truncated=true`；前端用同一批私密目录与扩展名清单过滤用户选中的文件。

## 文档挂载索引绑定与工作区召回

### 入口

- `python_backend/modules/workspaces/context.py:bind_document` —— 把文档挂进工作区索引
- `python_backend/modules/workspaces/context.py:recall_workspace` / `semantic_workspace` —— 工作区级召回与语义通道；`python_backend/workers/execution_worker.py:build_engine` —— 注入 `workspace_recall`

### 行为

- `workspace_id` 为空或查询为空时返回空结果（`hits`、`documents`、`semantic`）；每次召回先对根目录做增量索引与向量化（按 mtime 与大小标记，未变化不重读，目录里已删除的文件被剔除），索引写入由 `python_backend/modules/retrieval/workspace_index.py:WorkspaceIndex.index_source` / `source_marker` / `index_directory` 承担。
- 带 `source_id` 时执行绑定：文档按 `version` 作标记，上传文件固定 `v1`，标记未变则跳过重建；切块优先取向量库文档块，无块时回退上传文件的抽取文本，都空则不建索引。
- 词面命中里 `doc:` 前缀显示为《文档名》，其余显示文件相对路径；命中全局查询规则时额外插入目录覆盖清单；`documents` 取该工作区已挂载的全部文档（`WorkspaceIndex.documents_in`），与本次查询是否命中无关。
- 语义通道按工作区成员关系取候选：先在已挂载文档里做扩展检索，再对根目录文件做向量检索，最多 3 个文件、每个 6000 字符；向量库与嵌入异常被吞掉，不影响词面召回。

## 快照、变更与版本差异

### 入口

- `python_backend/infrastructure/resource_store.py:ResourceStore.create_workspace_snapshot` / `list_workspace_snapshots` / `list_workspace_changes` / `create_workspace_change`
- `POST /harness/workspaces/{workspace_id}/snapshots` / `GET /harness/workspaces/{workspace_id}/snapshots` / `GET /harness/workspaces/{workspace_id}/snapshots/{snapshot_id}/changes` / `POST /harness/workspaces/{workspace_id}/changes`；版本差异见 `python_backend/api/routers/resources.py:diff_versions` / `GET /harness/agents/{agent_id}/diff`

### 行为

- 快照来源优先取受管检出目录：文件清单来自 `git ls-files`，commit 取短哈希；否则扫本地目录并跳过 `.git`（`_scan_directory`）；目录扫描上限 20000 个文件，单文件超过 2 MB 不计入体积。
- 本地目录不可访问抛 `仓库路径不可访问，无法创建快照`，路由返回 400 且不产生快照记录；快照记录分支、commit、文件数与体积，每个文件写一条类型为 `tracked` 的变更记录；手工登记变更的类型只接受 `added`、`modified`、`deleted`、`tracked`（其它值 400），路径为空 422，引用不存在的快照 404。
- 版本差异比较 `name`、`description`、`version`、`model`、`policy`、`tools`、`skills`、`enabled`：`policy` 按字典比较、`tools` 与 `skills` 排序后比较、`enabled` 转布尔比较，键序与列表顺序不产生差异；列表型字段额外给出 `added` 与 `removed`，任一版本快照不存在返回 404。

## Agent 资源与技能绑定

### 入口

- `python_backend/infrastructure/resource_store.py:ResourceStore.create_agent` / `update_agent` / `set_agent_status` / `set_agent_skills` / `list_agent_versions` / `get_agent_version`
- `POST /harness/agents` / `PUT /harness/agents/{agent_id}` / `PUT /harness/agents/{agent_id}/status` / `POST /harness/agents/{agent_id}/skills` / `DELETE /harness/agents/{agent_id}/skills/{skill_id}` / `GET /harness/agents/{agent_id}/versions` / `GET /harness/agents/{agent_id}/diff` / `GET /harness/agents/{agent_id}/runs` / `GET /harness/workspaces/{workspace_id}/runs`

### 行为

- Agent ID 形如 `agent-<uuid4 前 12 位>`；字段含 `name`、`description`、`version`、`model`、`policy`、`status`、`enabled`、`tools`、`skills`、`revision`；`enabled` 默认关闭，`model` 默认 `auto`，`status` 默认 `draft`；旧库缺列时由 `ResourceStore._initialize` 自动补 `enabled`、`tools`、`skills`、`revision`。
- 创建、更新、切换启用状态、重新绑定技能都会写一条版本快照；重复设置相同启用状态或相同技能列表不再新增版本；更新时若请求体省略 `tools` 则保留原值，`revision` 不一致返回 409。
- 技能绑定只做去空格与整体替换，不校验技能是否已安装；解绑按 ID 过滤。
- 运行记录是跨库只读视图（`python_backend/api/routers/resources.py:_execution_runs`）：以只读 URI 打开执行库并按 `agent_id` 或 `workspace_id` 过滤；执行库不存在、表缺列或打开失败都返回空列表，`limit` 取值 1 到 200。

## 数据与存储

- 本地库 `{data_dir}/harness-resources.db`（SQLite），表：`harness_agent`、`harness_agent_version`、`harness_workspace`、`harness_workspace_checkout`、`harness_workspace_snapshot`、`harness_workspace_change`。
- 受管检出目录 `{data_dir}/workspaces/<workspace_id>/repo`；导入工作区落在 `{data_dir}/workspace-imports/<uuid>`。
- 工作区文件索引在 `{data_dir}/workspace-index.db`（属检索模块，本模块只通过公开方法调用）；技能目录绑定写入 `settings.skill_catalog_db` 指向的库并留审计记录。

## 接口清单

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/harness/agents` | Agent 列表 |
| `POST` | `/harness/agents` | 创建 Agent |
| `GET` | `/harness/agents/{agent_id}` | Agent 详情 |
| `PUT` | `/harness/agents/{agent_id}` | 更新 Agent（带 revision） |
| `PUT` | `/harness/agents/{agent_id}/status` | 切换启用状态 |
| `POST` | `/harness/agents/{agent_id}/skills` | 覆盖技能绑定 |
| `DELETE` | `/harness/agents/{agent_id}/skills/{skill_id}` | 解绑单个技能 |
| `GET` | `/harness/agents/{agent_id}/versions` | 版本历史 |
| `GET` | `/harness/agents/{agent_id}/diff` | 两个版本快照的差异 |
| `GET` | `/harness/agents/{agent_id}/runs` | 该 Agent 的运行记录 |
| `GET` | `/harness/workspaces` | 工作区列表 |
| `POST` | `/harness/workspaces` | 创建工作区 |
| `GET` | `/harness/workspaces/{workspace_id}` | 工作区详情 |
| `PUT` | `/harness/workspaces/{workspace_id}` | 更新工作区（带 revision） |
| `POST` | `/harness/workspaces/{workspace_id}/checkout` | 触发 git 检出 |
| `GET` | `/harness/workspaces/{workspace_id}/checkout` | 读检出状态 |
| `POST` | `/harness/workspaces/import` | 上传文件建工作区 |
| `GET` | `/harness/workspaces/{workspace_id}/files` | 列工作区文件 |
| `POST` | `/harness/workspaces/{workspace_id}/snapshots` | 建快照 |
| `GET` | `/harness/workspaces/{workspace_id}/snapshots` | 快照列表 |
| `GET` | `/harness/workspaces/{workspace_id}/snapshots/{snapshot_id}/changes` | 快照内文件与变更 |
| `POST` | `/harness/workspaces/{workspace_id}/changes` | 登记一条变更 |
| `GET` | `/harness/workspaces/{workspace_id}/runs` | 该工作区的运行记录 |
| `POST` | `/harness/skills/catalog/bind` | 绑定技能目录版本 |
| `DELETE` | `/harness/skills/catalog/bind` | 解绑技能目录版本 |

## 边界与已知限制

- 检出只做浅克隆（`--depth 1`），历史提交不可用；分支不存在时只能从远端分支列表里改选。
- 受管检出目录与根目录解析的状态值不一致（写入 `checked_out`，解析判 `ready`），受管检出目录目前不会被 `resolve_workspace_root` 采用。
- 快照统计上限 20000 个文件，单文件超过 2 MB 不计入体积，且只登记文件清单不保存内容；导入上限为单文件 50 MB、总量 512 MB、5000 个文件，文件列表接口最多返回 5000 条并用 `truncated` 标记。
- 工作区规则文件上限 64000 字节，超限直接报错而不是截断。
- 语义召回最多取 3 个文件、每个 6000 字符；嵌入或向量库异常时静默降级为纯词面召回。
- 技能绑定只记录技能 ID，不校验技能是否已安装（属技能模块）；运行记录是跨库只读视图，执行库缺失时返回空列表，不补建历史。
- 本模块对外只通过 `ResourceStore` 公开方法与 HTTP 路由暴露数据，不直接读写其它模块的数据库表。
