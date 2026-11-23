# Vue 工作台主界面（chat-web）

> 模块路径：`frontend/src/`（主界面实现）｜ 后端流式入口：`python_backend/api/routers/execution.py`
> 前端对应：`frontend/src/App.vue`、`frontend/src/api.js`、`frontend/src/main.js`、`frontend/src/modules/requirement/`、`frontend/src/modules/skills/`、`frontend/src/modules/execution/`
> 状态：现状说明（以代码为准，冲突时以代码为准并修正本文档）

## 应用骨架、页面导航与助手模式条

### 入口

- `frontend/src/main.js` —— 挂载 `#app`，导入 `tokens.css`、`style.css`、`harness.css`、`chat.css`、`theme.css`
- `frontend/src/App.vue:modes` / `chooseMode` / `usePageState` —— 五种模式、模式切换与导航状态

### 行为

- 主导航栏 9 个入口：首页、自动化、插件、bot、文档库、Harness 工程、代码地图、导出历史聊天、用户设置；`activePage` 取值限定在白名单内，非法值回落默认页
- 五种模式 id 为 `chat`、`file`、`ppt`、`deep`、`skills`，模式条是 `role="tablist"`；发送中不可切换，切到非 `file` 模式会清空已选文件、上传文件编号与文档来源
- 路由映射：`skills` 恒定走 `/agent/skills/stream`；其余模式带 `fileId` 走 `/agent/file/stream`；否则按模式走 `chat`/`pptx`/`deep` 路由
- 会话卡片角标由 `modeBadges` 映射，未知 `agentType` 回落「对话助手」；顶层弹窗接管 `Esc` 与 `Tab`，`Ctrl/Cmd+K` 新建会话

### 关键实现

- `frontend/src/App.vue:onMounted` —— 绑定 `keydown`、`visibilitychange` 与输入区 `ResizeObserver`；导航状态存 `sessionStorage` 的 `hotline-navigation:*`

## 消息流与自动贴底

### 入口

- `frontend/src/App.vue:sendMessage` —— 推送用户消息与助手占位消息
- `frontend/src/App.vue:scrollToBottom` / `onUserScroll` —— 贴底与上滑判定

### 行为

- 发送即插入一条用户消息和一条空助手消息；助手消息带 `timeline`、`references`、`recommend`、`pendingText` 等字段
- 正文用 `marked` 渲染并经 `DOMPurify` 清洗，`highlight.js` 高亮 `pre code`
- 打字节奏：待输出不足 160 字符每帧 2 字符，160–400 每帧 4 字符，超过 400 每帧 6 字符
- 上滑到距底部 48px 以上时停止贴底，回到底部后恢复；输入区高度变化时通过 `--composer-height` 重新留白并贴底

### 关键实现

- `frontend/src/App.vue:watch([input, composer])` —— 量内容高度时临时关过渡，输入框高度在 26px–150px 自适应

## 会话列表、会话详情与 agentType 判定

### 入口

- `frontend/src/App.vue:refreshSessions` / `selectSession` / `deleteConversation`
- `GET /session/list`、`GET /session/{conversationId}`、`DELETE /session/{conversationId}`

### 行为

- 列表分「运行中」和「最近」两段，运行中只有当前发送中的会话，其余按标题小写包含过滤；标题取首条问题，超过 28 字截断
- 草稿会话（`isDraft`）只存在内存；详情的 `agentType` 取**最后一条**消息的助手类型并据此切模式条，标题仍取第一条
- 加载历史时重新抽出候选答案面板；服务端已无该会话（404）时从列表移除并提示，删除请求期间禁用按钮

### 关键实现

- `frontend/src/App.vue:selectSession` —— 组装历史消息并调用 `applyQuestionOptions`；`python_backend/fastapi_app.py:session_detail` —— 返回 `rows[-1].agentType`

## SSE 流式接入与事件处理

### 入口

- `frontend/src/App.vue:sendMessage` —— `fetch` 读取 `text/event-stream`
- `frontend/src/App.vue:appendStreamEvent` —— 事件分发到消息字段

### 行为

- 按空行切帧只取 `data:` 行；`[DONE]` 跳过，非法 JSON 忽略
- 处理 `text`、`reference`、`agent`、`recommend`、`clarify`、`error`、`complete`；`step/progress/thinking/tool_start/tool_end` 记入时间线
- `agent` 事件是「交接口令由后端认定」的唯一来源，据此切模式条与底部输入区形态；正文出现「下载文件 / Download」链接时抽出为 PPT 下载链接
- `clarify` 事件渲染成澄清卡片：选方向或写补充说明后带原问题重新提问，作答一次后卡片收起；失败事件写入时间线并展开，`complete` 收起时间线

### 关键实现

- `frontend/src/App.vue:answerClarify` —— 澄清作答拼装；`frontend/src/modules/execution/progress.js:appendProgressEvent` —— 阶段与工具调用条目

## 需求助手交接与候选答案面板

### 入口

- `frontend/src/modules/requirement/handoff.js:handoffFor` / `recommendationLabel` —— 推荐项文案与交接
- `frontend/src/modules/requirement/question-options.js:extractQuestionOptions` / `buildOptionPanel` / `composeOptionAnswer`
- `frontend/src/modules/requirement/OptionPanel.vue` —— 面板组件

### 行为

- 推荐项是结构化对象 `{label, skill}` 时，`handoffFor` 返回 `{mode:'skills', skill, query:label}`，前端切技能助手并把标签原样发出；普通字符串推荐项原样显示、原样发送，不切模式
- 需求正文不靠前端传递：候选答案由前端从助手正文抽出，正文只留问题；解析规则是以问号结尾的行为问题，其下的项目符号行或 `A.`/`B、`/`C)` 编号行为候选
- 只有成组出现（至少两条）且单条不超过 60 字的问题组会被抽走，普通列表原样留在正文；每组从 `A` 重新编号，选项 key 为「组号:选项号」
- 选项可跨题多选；「发送所选」拼成 `<问题>——<字母>. <候选>` 多行文本，切技能助手后发出；面板只跟随最新一轮回答，用户发消息即清空

### 关键实现

- `frontend/src/App.vue:sendRecommendation` / `toggleOption` / `sendSelectedOptions` —— 点击推荐项、切换选项与发送；`python_backend/modules/skills/handoff.py:normalize_recommendations` —— 旧会话字符串推荐项升级成结构化项

## 技能助手接管底部输入区

### 入口

- `frontend/src/modules/skills/composer.js:skillComposerCopy`
- `frontend/src/App.vue:skillCopy` —— 模板取值

### 行为

- `activeMode === 'skills'` 时底部整块由技能接手：顶部出现 `.skill-bar` 标识，输入框占位改为「在这里回复技能助手…」
- 候选答案面板与输入框仍留在底部同一块区域，不另起输入框；模式条保留，便于切回普通对话
- 其他模式形态不变，`skillComposerCopy` 返回 `null`；容器 `.composer-area` 背景透明，只有输入框与候选面板自带底色

### 关键实现

- `frontend/src/modules/skills/composer.js:SKILL_COPY` —— 技能助手文案集中在此；`frontend/src/chat.css` —— `.composer-area`、`.skill-bar` 样式

## 并行派发面板与运行详情接入

### 入口

- `frontend/src/modules/execution/ParallelPanel.vue` —— 并行派发面板
- `frontend/src/modules/execution/useRunEvents.js:useRunEvents` / `ExecutionRunDetails.vue`

### 行为

- 并行派发面板挂在 Harness 控制面「执行任务」区，由 `showParallelPanel` 控制收起与展开
- 派发时填会话标识、助手类型、工作区和多个子任务，一次最多 16 个（后端校验），每个子任务占一个 slot；事件走合并流单连接接收，卡片按 `runId` 分流，展示文本、错误与隔离目录
- 运行详情按标签页展示输入与结果、Trace、提交信息、上下文快照、运行产物，Trace 可导出 JSON；`useRunEvents` 先读 `/execution/runs/{id}/events?after=cursor` 再用 EventSource 续接 `/execution/runs/{id}/stream`，游标按 `event_id` 递增

### 关键实现

- `frontend/src/modules/execution/useRunEvents.js:useRunEvents` —— 游标与世代号防旧流串入；`frontend/src/HarnessApp.vue:showParallelPanel` —— 挂载位置

## 历史会话导出

### 入口

- `frontend/src/App.vue:exportChatHistory` —— 导出全部聊天
- `GET /session/list`（分页取全量）、`GET /session/{conversationId}`

### 行为

- 按每批 8 个会话并发拉详情，汇总成一个 JSON 文件；结构为 `{format:'dodo-chat-history', version:1, exportedAt, conversations[]}`，每条含 `conversationId`、`title`、`agentType`、`createTime` 与 `messages[]`（question、answer、thinking、reference、recommend、fileId、createTime）
- 通过 Blob 与临时链接在浏览器本地生成并下载，文件名 `dodo-chat-history-<日期>.json`，不写服务端；导出期间按钮禁用并显示加载态

### 关键实现

- `frontend/src/api.js:getAllSessions` —— 分页拉全量；`frontend/src/App.vue:exportChatHistory` —— 批量取详情并生成本地文件

## 数据与存储

- 会话与消息持久化在后端 `ai_session` 表（`python_backend/modules/storage/relational.py`），前端不落库；草稿会话只存在于浏览器内存
- `sessionStorage`：`hotline-navigation:page`、`hotline-navigation:chat-mode` 等导航状态；`localStorage`：`dodo-api-base`（后端服务地址）、`hotline-pet-enabled`、`hotline-pet`；导出文件只落在浏览器下载目录

## 接口清单

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/agent/chat/stream` | 对话助手流式回答 |
| `GET` | `/agent/file/stream` | 文件问答流式回答 |
| `GET` | `/agent/pptx/stream` | PPT 生成流式回答 |
| `GET` | `/agent/deep/stream` | 深度研究流式回答 |
| `GET` | `/agent/skills/stream` | 技能助手流式回答 |
| `GET` | `/agent/stop` | 停止当前会话的执行 |
| `GET` | `/session/list` | 会话列表（分页） |
| `GET` | `/session/{conversationId}` | 会话详情（含最后一条 agentType） |
| `DELETE` | `/session/{conversationId}` | 删除会话 |
| `POST` | `/file/upload` | 上传对话附件 |
| `GET` | `/health` | 服务连通性检查 |
| `POST` | `/execution/runs/parallel` | 派发并行子任务 |
| `GET` | `/execution/parallel/stream` | 子任务合并事件流 |
| `GET` | `/execution/runs/{runId}/events` | 按游标读取运行事件 |
| `GET` | `/execution/runs/{runId}/stream` | 运行事件续接流 |
| `GET` | `/harness/workspaces` | 工作区列表（工作区面板与并行派发共用） |

## 边界与已知限制

- 只起网关未起执行 Worker 时，`/agent/*/stream` 返回 503，前端表现为一条错误时间线
- 候选抽取依赖模型输出格式：候选不足两条或单条超过 60 字时不会进入面板；打字节奏是显示模拟，正文内容与后端下发量一致
- 同一会话的第二个子任务会被后端任务锁拒绝；导出一次性读取全量会话，会话数量多时耗时随之增长
- 工作区导入只按路径与大小过滤（跳过私密与依赖路径，单文件上限 50 MB），不校验文件内容
- 右侧「变更」面板的变更列表是前端静态数据（`frontend/src/App.vue:changedFiles`），不代表真实仓库差异；PPT 下载链接依赖后端在正文中给出下载路径，前端只做抽取与拼链接
