# Harness 控制台（harness-console）
> 模块路径：`python_backend/api/routers/{registry,bots,profile,settings,schedules,observability,code_map}.py` + `python_backend/infrastructure/{registry_store,bot_store,persona,profile_store,credential_store,settings_store,scheduled_store}.py` + `python_backend/modules/execution/scheduler.py`
> 前端对应：`frontend/src/HarnessApp.vue`（控制台壳层）、`frontend/src/modules/harness/panels/*Panel.vue`（各 section 面板）、`frontend/src/modules/bots/BotPage.vue`（bot）、`frontend/src/modules/automation/AutomationPage.vue`（自动化）、`frontend/src/modules/profile/ProfilePage.vue`（个人中心）、`frontend/src/modules/artifacts/CodeMapPage.vue`
> 状态：现状说明（以代码为准，冲突时以代码为准并修正本文档）

## 工具与模型登记
### 入口
- `python_backend/api/routers/registry.py:create_registry_router` —— 工具与模型登记路由；`python_backend/infrastructure/registry_store.py:RegistryStore` —— SQLite 登记表读写
- `GET/POST /harness/tools`、`GET/PUT /harness/tools/{tool_id}`、`POST /harness/tools/{tool_id}/test`
- `GET/POST /harness/models`、`GET/PUT /harness/models/{model_id}`、`POST /harness/models/{model_id}/test`、`GET /harness/models/{model_id}/fallback-chain`
- 前端：`frontend/src/modules/harness/panels/ToolsPanel.vue`「工具与 MCP」、`frontend/src/modules/harness/panels/ModelsPanel.vue`「模型路由」；接口封装在 `frontend/src/modules/harness/tools/api.js`（`getHarnessTools/createHarnessTool/updateHarnessTool/testHarnessTool`）与 `frontend/src/modules/harness/models/api.js`（`getHarnessModels/createHarnessModel/updateHarnessModel/testHarnessModel/getModelFallbackChain`）
### 行为
- 工具登记项含 `name/source/scope/risk/status/description/input_schema/approval_policy`；`name/source/scope/status` 去空格后不能为空。
- `input_schema` 必须是 JSON Schema：根 `type` 为 `object`、`properties` 为对象、`required` 为字符串数组，且 `required` 中每个字段都在 `properties` 里声明过（`registry.py:ToolPayload.object_schema`）。
- `risk` 只允许 `low/medium/high`；`approval_policy` 只允许 `risk-based/always`。
- 工具更新带 `revision` 乐观锁：库中 `revision` 与提交值不一致返回 409（`RegistryConflictError`），提示重新打开详情再保存。
- 模型登记项含 `name/provider/route/status/cost_policy/fallback_model_id`；`name/route/status` 不能为空。
- 回退链沿 `fallback_model_id` 逐级展开，顺序即回退顺序；保存时校验备用模型存在且不成环，成环或引用不存在返回 400。
- 工具连通性测试按 `source` 分派：`mcp:` 开头走 MCP stdio 的 `initialize` 探测；`source=agent` 检查机器人是否存在与是否启用；`source` 为空或 `builtin` 时按名称找同名内置工具；其余 `source` 返回「暂不支持的连接方式」。
- 模型连通性测试走 `probe_model`：用当前生效的模型配置发一次极短请求；探测失败只回显异常类型，不回显命令、参数或本机路径。
### 关键实现
- `python_backend/infrastructure/registry_store.py:create_tool/update_tool/fallback_chain/_validate_fallback` —— 写入维护 `revision` 与 `updated_at`；链展开与环检测
- `python_backend/llm.py:probe_model/probe_credentials`、`python_backend/modules/mcp/__init__.py:probe_stdio_server` —— 探测实现
- `python_backend/modules/execution/tools.py:registry_tool/enforce_approval` —— 运行期按工具名取登记记录，按 `approval_policy` 与 `risk` 决定是否阻塞等待人工审批（`always` 或 `high` 风险）
- `python_backend/workers/execution_worker.py` —— 把 Agent 资源绑定的模型名匹配到登记模型，带出 `modelRoute` 与 `fallbackModelId`

## 机器人
### 入口
- `python_backend/api/routers/bots.py:create_bots_router` —— 机器人 CRUD 与会话绑定路由；`python_backend/infrastructure/bot_store.py:BotStore` —— 存储
- `GET/POST /harness/bots`、`GET/PUT/DELETE /harness/bots/{bot_id}`、`POST /harness/bots/{bot_id}/sessions`
- `python_backend/infrastructure/persona.py:load_persona` —— 汇总注入模型的人设
- 前端：`frontend/src/modules/bots/BotPage.vue` 与 `BotSidebar.vue`「bot」页（左侧栏列表 + 每个机器人一个开关）；`frontend/src/modules/bots/api.js` 的 `getBots/createBot/updateBot/deleteBot`（会话绑定接口只在后端开放，前端没有调用）
### 行为
- 机器人 = 名称 + 角色指令 + 绑定技能 + 启用状态；名称去空格后为空返回 422。
- 开关是全局语义：开启一个机器人会把其余机器人全部关闭（`BotStore._disable_others`），同一时间只留一个开启的。
- `enabled_bot()` 返回当前开启的机器人，开启后对所有会话生效；会话绑定只在没有开启机器人时作为回退（`session_bot`）。
- 会话绑定以 `conversation_id` 为主键，一个会话只对应一个人设；删除机器人会连带删除它的全部会话绑定。
- 人设内容 = 角色指令 + 绑定技能 + 个人回答风格（`concise/detailed/friendly`），由 `AgentEngine._persona_block` 追加到系统提示词末尾，不覆盖既有规则。
- 前端列表与详情不展示角色指令，只有编辑表单里能改。
### 关键实现
- `python_backend/infrastructure/bot_store.py:create/update/delete/bind_session` —— 写库时同步维护「只留一个开启」
- `python_backend/seed_bots.py` —— 本地数据种子入口，把仓库技能包装成机器人并登记为 `harness_tool` 的 `agent` 来源；同时播种 6 个角色机器人（产品经理、前端/后端/AI/运维/测试工程师），按名称 upsert 并保留用户设置的开启状态
- 前端头像：`frontend/src/modules/bots/useBots.js` 的 `BOT_META` 按机器人名称映射头像图片、Lucide 角色图标与主题色，列表小头像 + 详情大头像 + 右下角角标贴图（样式在 `frontend/src/style.css`，图片在 `frontend/src/assets/bot-*-avatar.jpg`）

## CI 工作流开关
### 入口
- `python_backend/api/routers/ci_workflow.py:create_ci_workflow_router` —— 读状态与启停工作流的路由
- `python_backend/infrastructure/github_workflow.py:GitHubWorkflowClient` —— GitHub Actions 工作流客户端（stdlib urllib，不引入新依赖）
- `GET /harness/ci-workflow`、`POST /harness/ci-workflow`（请求体 `{"enabled": true|false}`）
- 前端：`frontend/src/modules/bots/BotSidebar.vue` 左侧栏机器人列表下方的「CI 工作流」开关；`frontend/src/modules/bots/api.js` 的 `getCiWorkflow/setCiWorkflow`
### 行为
- 开关直接调用 GitHub 的 `PUT /repos/{owner}/{repo}/actions/workflows/{workflow}/enable|disable`，关闭后推送与 PR 不再触发该工作流。
- 凭据只从本机环境变量读：`HOTLINE_GITHUB_TOKEN`、`HOTLINE_GITHUB_REPOSITORY`、`HOTLINE_GITHUB_CI_WORKFLOW`（默认 `ci.yml`）；不进数据库、不写日志、不随请求外传。
- 未配置 Token 或仓库时，`GET` 如实返回 `configured: false` 并说明原因，`POST` 返回 409；前端开关置灰，不做猜测。
- GitHub 侧出错时统一转成 502，错误消息只带状态码，不带凭据。
- 前端只展示后端返回的状态与目标（仓库 + 工作流文件），不自己推断；切换后以后端返回的状态为准。
### 关键实现
- `GitHubWorkflowClient.workflow_state` 把 GitHub 的 `state` 映射成 `enabled`：只有 `active` 算开启，`disabled_manually` 等都算关闭。
- 开关状态与机器人列表一起刷新（`useBots.refreshBots` 内调用 `refreshCiWorkflow`），进页面或定时刷新时都能看到最新状态。

## 画像与凭据
### 入口
- `python_backend/api/routers/profile.py:create_profile_router` —— 画像与模型凭据路由；`python_backend/infrastructure/profile_store.py:ProfileStore`、`python_backend/infrastructure/credential_store.py:CredentialStore`
- `GET/PUT /harness/profile`、`GET/PUT/DELETE /harness/profile/credentials`、`POST /harness/profile/credentials/test`
- 前端：`frontend/src/modules/profile/ProfilePage.vue`「个人中心」页；`frontend/src/modules/profile/api.js` 的 `getProfile/saveProfile/getCredential/saveCredential/deleteCredential/testCredential`
### 行为
- 画像字段 `nickname/bio/answerStyle/theme`；`answerStyle` 只接受 `default/concise/detailed/friendly`，`theme` 只接受 `system/light/dark`，其它取值返回 400。
- 画像是部分更新：未提交的字段沿用旧值，只改主题不会把昵称清空。
- 凭据只存本机 SQLite；读取接口只回显掩码（首 3 字符 + 掩码 + 末 4 字符），并用 `hasKey` 标记是否已配置。
- 保存凭据时不提交 `apiKey` 会保留原有密钥；从未保存过时删除返回 404。
- 连通性测试：未接入探测函数时返回 501；否则用本次提交的凭证发起真实请求，缺项回落到已保存的凭据。
- 本机保存的凭据优先于环境变量（`python_backend/llm.py:model_config`）。
### 关键实现
- `python_backend/infrastructure/credential_store.py:mask/public/save` —— 掩码回显与密钥保留
- `python_backend/llm.py:probe_credential/probe_credentials` —— 连通性探测；`profile_store.py:save` —— 按默认字段集合做部分更新

## Harness 设置
### 入口
- `python_backend/api/routers/settings.py:create_settings_router` —— 设置读写路由；`python_backend/infrastructure/settings_store.py:SettingsStore` —— 单行设置存储
- `GET /harness/settings`、`PUT /harness/settings`
- 前端：`frontend/src/modules/harness/panels/SettingsPanel.vue`「Harness 设置」分区（接口在 `frontend/src/modules/harness/api.js`：`getHarnessSettings/saveHarnessSettings`）
### 行为
- 设置项：`isolation`、`auditRetentionDays`、`approvalPolicy`、`defaultBudgetUsd`、`defaultTimeoutSeconds`、`defaultRetryCount`、`approvalTimeoutSeconds`、`artifactRetentionDays`、`defaultTokenBudget`、`approvalNotifyEnabled`、`notificationWebhookUrl`、`artifactOwnerHeader`。
- 取值范围：保留天数 1–3650，默认预算 0–100000，默认超时 1–86400 秒，默认重试 0–10，审批超时 60–86400 秒，默认令牌预算 0–100000000。
- 读取时用默认值补齐缺失键并附带 `updatedAt`；整份设置是单行记录，保存即覆盖。
- 执行期消费同一份设置：工具审批等待时长取 `defaultTimeoutSeconds`（`modules/execution/tools.py:_approval_wait_seconds`），数据保留清理也读它（`modules/retention/maintenance.py`）。
### 关键实现
- `python_backend/infrastructure/settings_store.py:get/save` —— 读取补默认值，保存只写提交的键；`api/routers/settings.py:HarnessSettingsPayload` —— 字段与范围校验

## 定时任务与调度
### 入口
- `python_backend/api/routers/schedules.py:create_schedules_router` —— 定时任务路由；同文件 `create_schedule_runner/submit_task_run` —— 到点扫描与提交运行
- `python_backend/infrastructure/scheduled_store.py:ScheduledStore` —— 定时任务存储；`python_backend/modules/execution/scheduler.py:register_runner/run_once/stop_schedule_loop` —— 调度线程
- `GET/POST /harness/schedules`、`PUT/DELETE /harness/schedules/{task_id}`、`POST /harness/schedules/{task_id}/run`
- 前端：`frontend/src/modules/automation/AutomationPage.vue`「自动化」页（`getSchedules/createSchedule/updateSchedule/deleteSchedule/runSchedule`）
### 行为
- 任务字段 `name/prompt/agent`（默认 `chat`）`intervalMinutes`（默认 60）`enabled`；间隔按整分钟计，取值 1 到 60×24×30。
- 更新是部分更新，未提交的字段保持原值；更新或删除不存在的任务返回 404。
- 立即执行复用执行队列提交一次运行，会话编号为 `schedule-{task_id}-{时间戳}`；没有可用 Worker 时返回 503 并带出失败原因。
- 调度线程每 60 秒扫描一次，只跑「已启用且距上次运行超过间隔」的任务；单个任务失败不影响其它任务，失败只记日志。
- 提交成功后任务上记录 `last_run_at` 与 `last_run_id`；线程是守护线程，登记回调时若线程已存活则直接复用，退出时 `stop_schedule_loop()` 停止线程并清空回调。
### 关键实现
- `python_backend/modules/execution/scheduler.py:register_runner/run_once/stop_schedule_loop` —— 线程注册、单轮执行与停止
- `python_backend/fastapi_app.py` 的 `lifespan` —— 启动时 `register_runner(create_schedule_runner(...))`，退出时 `stop_schedule_loop()`
- `python_backend/infrastructure/scheduled_store.py:mark_run` —— 记录上次运行时间与运行号

## 可观测查询与导出
### 入口
- `python_backend/api/routers/observability.py:create_observability_router` —— 运行、事件、指标、导出与趋势路由；数据来自执行库（`python_backend/infrastructure/queue.py:SqliteExecutionQueue` 的 `list_runs/get_run/get_events`）
- `GET /harness/observability/runs`、`GET /harness/observability/runs/{run_id}/events`、`GET /harness/observability/metrics`
- `GET /harness/observability/runs/{run_id}/export`、`GET /harness/observability/exports`、`GET /harness/observability/trends`
- 前端：`frontend/src/modules/harness/panels/TracesPanel.vue`「追踪与日志」分区（接口在 `frontend/src/modules/governance/api.js`：`getHarnessObservabilityRuns/getHarnessObservabilityMetrics/getObservabilityExports/getObservabilityTrends/harnessTraceExportUrl`）
### 行为
- 运行列表 `limit` 取值 1–200，返回 `items` 与 `total`；事件查询支持 `after/level/tool/hasError/since/until/type` 过滤，运行不存在时返回空列表而不是 404。
- 指标按 `queued/running/completed/failed/cancelled` 分类统计运行数，并统计错误事件数、`tool_start` 次数与最近 10 次运行。
- 单次运行导出为 JSON 附件，文件名由运行号净化后拼 `-trace.json`。
- 跨运行导出支持 `format=json|csv`，其它取值返回 400；CSV 列固定为 `run_id/event_id/created_at/type/level/tool/status/summary`，响应头带 `X-Harness-Total` 与 `X-Harness-Truncated`。
- 趋势按 `hour` 或 `day` 分桶，其它取值返回 400；只返回有数据的桶，新的在前，最多 `limit` 个。
- 导出与趋势以只读方式直接打开执行库：文件不存在时返回空结果，读取异常返回 503；`from/to` 时间参数必须是 ISO 格式，否则 400。
### 关键实现
- `python_backend/api/routers/observability.py:_open_readonly` —— 只读连接与缺失兜底；同文件 `_event_row/_summary` —— 事件行归一化与摘要截断
- `python_backend/modules/execution/store.py:event_level/event_tool` —— 事件级别与工具名提取

## 代码地图资源
### 入口
- `python_backend/api/routers/code_map.py:create_code_map_router` —— 代码地图静态资源路由
- `GET /code-map` —— 可用性探测；`GET /code-map/{asset_path}` —— 资源读取
- 前端：`frontend/src/modules/artifacts/CodeMapPage.vue`（壳层「代码地图」页），`frontend/src/modules/artifacts/api.js:getCodeMapStatus`
### 行为
- 只提供两个静态资源：`hotline.html`（`text/html`）与 `vendor/mermaid.min.js`（`application/javascript`）。
- `GET /code-map` 返回 `available`：两个文件都存在才为 true，缺一即为 false。
- 资源路径必须落在地图目录内且只能命中白名单里的名字，其它路径、目录穿越与指向目录外的符号链接一律 404。
- 资源响应带 `Cache-Control: no-cache` 与 `X-Content-Type-Options: nosniff`。
### 关键实现
- `python_backend/api/routers/code_map.py:asset_file` —— 白名单 + 目录内解析；目录由 `data/code-map/hotline` 提供（`fastapi_app.py` 装配时传入），路由只读取、不生成内容

## 数据与存储
- 全部落在被 Git 忽略的 `data/` 目录，均为本机 SQLite：
  - `harness-registry.db`：`harness_tool`、`harness_model`（工具与模型登记）
  - `harness-bots.db`：`harness_bot`、`harness_bot_session`（机器人与会话绑定）
  - `harness-profile.db`：`harness_profile`（单行画像）
  - `harness-credentials.db`：`harness_model_credential`（单行模型凭据）
  - `harness-settings.db`：`harness_settings`（单行设置）
  - `harness-schedules.db`：`harness_scheduled_task`（定时任务）
- 执行库（`settings.execution_db_path`）里的 `execution_run`、`execution_event` 由可观测只读查询；静态资源目录为 `data/code-map/hotline/`。
- 凭据与模型密钥只存本机文件，接口只回显掩码，文档与日志不出现明文。

## 接口清单
| 方法 | 路径 | 用途 |,| --- | --- | --- |
| `GET, POST` | `/harness/tools` | 列出工具登记 / 登记工具 |
| `GET, PUT` | `/harness/tools/{tool_id}` | 读工具详情 / 更新（带 revision） |
| `POST` | `/harness/tools/{tool_id}/test` | 工具连通性测试 |
| `GET, POST` | `/harness/models` | 列出模型路由 / 登记模型路由 |
| `GET, PUT` | `/harness/models/{model_id}` | 读模型详情 / 更新（带 revision） |
| `POST` | `/harness/models/{model_id}/test` | 模型连通性测试 |
| `GET` | `/harness/models/{model_id}/fallback-chain` | 展开备用模型链 |
| `GET, POST` | `/harness/bots` | 列出机器人 / 新建机器人 |
| `GET, PUT, DELETE` | `/harness/bots/{bot_id}` | 读详情 / 更新（含开关）/ 删除（含会话绑定） |
| `POST` | `/harness/bots/{bot_id}/sessions` | 绑定会话到机器人 |
| `GET, POST` | `/harness/ci-workflow` | 读 CI 工作流状态 / 启停工作流（请求体 `{"enabled": true}`） |
| `GET, PUT` | `/harness/profile` | 读个人偏好 / 保存（部分更新） |
| `GET, PUT, DELETE` | `/harness/profile/credentials` | 读凭据（掩码）/ 保存 / 删除 |
| `POST` | `/harness/profile/credentials/test` | 模型凭据连通性测试 |
| `GET, PUT` | `/harness/settings` | 读 Harness 设置 / 保存 |
| `GET, POST` | `/harness/schedules` | 列出定时任务 / 新建 |
| `PUT, DELETE` | `/harness/schedules/{task_id}` | 更新（部分更新）/ 删除 |
| `POST` | `/harness/schedules/{task_id}/run` | 立即执行一次定时任务 |
| `GET` | `/harness/observability/runs` | 运行列表 |
| `GET` | `/harness/observability/runs/{run_id}/events` | 事件查询（多条件过滤） |
| `GET` | `/harness/observability/metrics` | 运行与事件指标 |
| `GET` | `/harness/observability/runs/{run_id}/export` | 单次运行轨迹导出（JSON） |
| `GET` | `/harness/observability/exports` | 跨运行事件导出（json/csv） |
| `GET` | `/harness/observability/trends` | 按小时/天分桶的趋势 |
| `GET` | `/code-map` | 代码地图可用性 |
| `GET` | `/code-map/{asset_path}` | 代码地图静态资源 |

## 边界与已知限制
- 工具登记只保存元数据；工具真正的调用走 MCP 路由或内置工具，不是控制台。
- 工具连通性测试只覆盖 MCP stdio、内置工具与机器人三种 `source`，其余 `source` 直接返回不支持。
- 模型连通性测试测的是当前生效的模型配置，不是登记项里的模型名；登记项与运行时的绑定靠 Agent 资源里的模型名匹配。
- 回退链的运行时生效路径是 `python_backend/llm.py:build_chat_model` 传入 `fallback_model_ids` 的场景。
- 机器人列表与详情接口返回体里含 `instruction` 字段，前端列表与详情不展示，只有编辑表单可改。
- `PUT /harness/settings` 的请求体带全部字段默认值，前端只提交部分字段时未提交项会被写回默认值。
- 定时任务只有固定间隔，没有 cron 表达式、时区与漏跑补跑；调度线程在网关进程内，网关停机期间到点的任务不补跑。
- 可观测导出与趋势直读执行库，库文件缺失返回空结果；导出条数受 `limit` 限制，超出部分由 `X-Harness-Truncated` 标记。
- 代码地图是静态文件目录，路由只读取不生成；地图文件由外部放入 `data/code-map/hotline`。
- 工具登记项的 `approval_policy` 与 Harness 设置里的 `approvalPolicy` 是两处独立数据，后者不覆盖前者。
