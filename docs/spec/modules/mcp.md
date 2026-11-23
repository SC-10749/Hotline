# MCP 工具接入（mcp）

> 模块路径：`python_backend/modules/mcp/`（连接器实现）＋ `python_backend/api/routers/mcp.py`（HTTP 路由）＋ `python_backend/infrastructure/registry_store.py`（登记存储）
> 前端对应：`frontend/src/modules/mcp/` 只有 `.gitkeep` 占位，无独立前端模块；实际调用在 `frontend/src/api.js`（`getHarnessMcpServers`、`callMcpTool`）与 `frontend/src/HarnessApp.vue` 的「工具与 MCP」面板
> 状态：最小 stdio 型 MCP 连接器（自研 JSON-RPC over stdio，不引入 MCP SDK）；支持 initialize 探测、tools/list 工具发现、tools/call 工具调用；HTTP 路由只提供服务器清单与工具调用，审批链不经过本路由

## stdio 会话启动与收尾

### 入口
- `python_backend/modules/mcp/__init__.py:_StdioSession` —— 一次 stdio 会话（进程启动、请求发送、按 id 匹配响应、进程收尾）
- `python_backend/modules/mcp/__init__.py:_normalize_config` —— 校验并归一化连接配置
- `python_backend/modules/mcp/__init__.py:_terminate` —— 结束探测进程

### 行为
- 配置形状为 `{command, args, env}`：`command` 必须是非空字符串；`args` 必须是字符串数组；`env` 必须是对象。任一项不合规抛 `McpError`，消息分别是「MCP 配置格式不正确」「MCP 配置缺少 command」「MCP 配置的 args 必须是字符串数组」「MCP 配置的 env 必须是对象」。
- `env` 以 `{**os.environ, **env_patch}` 合成：子进程继承宿主全部环境变量，`env_patch` 只做覆盖，键值统一转字符串。
- 进程以 `stdin=PIPE`、`stdout=PIPE`、`stderr=DEVNULL`、`text=True`、`encoding='utf-8'`、`bufsize=1` 启动；stderr 内容被丢弃，不回传也不入库。
- 独立守护线程读 stdout，按行推入队列；读到流末尾时向队列推入 `None` 哨兵。
- 收尾顺序固定为「先结束进程、再关管道」：`terminate()` 后 `wait(timeout=2)`，失败则 `kill()` 后再 `wait(timeout=2)`，最后关闭 stdin/stdout。管道在进程结束前关闭会让读线程卡在 readline。
- 会话以 `with` 使用，`__exit__` 必调 `close()`，正常返回与抛异常两条路径都收尾，不留残留进程。

### 关键实现
- `python_backend/modules/mcp/__init__.py:_StdioSession.__enter__` —— 启动进程并拉起读线程
- `python_backend/modules/mcp/__init__.py:_StdioSession.__exit__` —— 统一收尾
- `python_backend/modules/mcp/__init__.py:_terminate` —— terminate/kill 两级兜底

## initialize 探测与超时

### 入口
- `python_backend/modules/mcp/__init__.py:probe_stdio_server` —— 一次 initialize 探测
- `python_backend/api/routers/registry.py:test_tool` —— `source` 以 `mcp:` 开头时走探测
- `POST /harness/tools/{tool_id}/test` —— 登记项连接测试

### 行为
- 探测在独立会话里发一次 `initialize`，协议版本固定 `PROTOCOL_VERSION = '2024-11-05'`，`capabilities` 为空对象，`clientInfo` 为 `{name: 'harness-agent', version: '1.0'}`。
- 超时上限 `PROBE_TIMEOUT_SECONDS = 10.0` 秒；超时消息为「MCP 服务器在 N 秒内没有响应」。
- 进程提前结束（读到哨兵）报「MCP 服务器没有返回响应」；输出不是合法 JSON-RPC 报「MCP 服务器返回的不是 JSON-RPC 响应」（两类消息都已在探测与调用链路上共用）。
- 服务端回了带 `error` 的响应时统一报「MCP 服务器拒绝了 initialize 请求」，不转述服务端原文。
- 成功返回 `{'ok': True, 'message': '连接正常', 'details': {...}}`；`details` 只保留 `protocolVersion` 与 `serverInfo.name`（键名 `serverName`），其余字段丢弃。
- 任何异常都被收敛成 `{'ok': False, 'message': ...}`，不抛到调用方。

### 关键实现
- `python_backend/modules/mcp/__init__.py:_initialize_params` —— initialize 请求体
- `python_backend/modules/mcp/__init__.py:_StdioSession.call` —— 发送请求、按 id 匹配响应
- `python_backend/modules/mcp/__init__.py:_describe` —— 探测结果的字段裁剪

## 工具清单发现（tools/list）

### 入口
- `python_backend/modules/mcp/__init__.py:list_stdio_tools` —— 发现服务器提供的工具清单
- `GET /harness/mcp/servers` —— 服务器清单 + 每个服务器已发现的工具名

### 行为
- 同一会话内先 `initialize`、再 `tools/list`（参数为空对象），超时上限 `LIST_TIMEOUT_SECONDS = 10.0` 秒；路由层的服务器清单接口改用更短的 `DISCOVERY_TIMEOUT_SECONDS = 5.0`。
- 返回 `{'ok', 'message', 'tools'}`；成功时 message 为「发现 N 个工具」，失败时 `tools` 为空数组。
- 只保留 `name` 为字符串的条目，输出统一为 `{name, description, inputSchema}`；`description` 缺失取空串，`inputSchema` 缺失取空对象。
- 服务器先发通知或无关 id 的消息时，读取循环跳过这些消息继续等本请求的响应，只有 id 匹配才取 `result`；`GET /harness/mcp/servers` 对每个已登记服务器各启一次发现，条目的 `tools` 是工具名数组，发现失败时 `tools` 为空、`message` 写失败原因（成功时为空串）。

### 关键实现
- `python_backend/modules/mcp/__init__.py:_StdioSession.call` —— 跳过通知与不匹配 id 的消息
- `python_backend/api/routers/mcp.py:list_mcp_servers` —— 服务器清单组装

## 工具调用与错误分类（tools/call）

### 入口
- `python_backend/modules/mcp/__init__.py:call_stdio_tool` —— 调用服务器上的一个工具
- `POST /harness/mcp/servers/{tool_id}/tools/{tool_name}/call` —— HTTP 工具调用

### 行为
- 调用在同一会话内先 `initialize`、再 `tools/call`，请求参数为 `{name, arguments}`；超时上限 `CALL_TIMEOUT_SECONDS = 30.0` 秒。
- 返回 `{'ok', 'message', 'content', 'isError'}`：服务端 `isError` 为真时 `ok=False`、message 为「工具返回错误」，否则 `ok=True`、message 为「调用成功」。
- `content` 归一化为数组：缺失取空数组，非数组则包成单元素数组。
- 错误分类：工具名为空或非字符串 → 「工具名称不能为空」；参数非对象 → 「工具参数必须是 JSON 对象」；会话类失败沿用探测的消息；返回体不是对象 → 「MCP 服务器返回的不是 JSON-RPC 响应」。HTTP 层状态码：服务器不存在或登记项不是 MCP 服务器 → 404，工具名不在发现清单 → 404，参数校验不通过 → 400，发现阶段失败 → 502（detail 取失败消息）。

### 关键实现
- `python_backend/modules/mcp/__init__.py:call_stdio_tool` —— 调用与结果归一化
- `python_backend/api/routers/mcp.py:call_mcp_tool` —— 路由层的发现 → 校验 → 调用顺序

## 参数必须是对象

### 入口
- `python_backend/modules/execution/tools.py:validate_tool_arguments` —— 按登记的 `input_schema` 校验参数
- `python_backend/api/routers/mcp.py:call_mcp_tool` —— 路由调用点

### 行为
- 连接器层先判形状：`arguments` 为 `None` 按空对象处理；不是字典直接返回「工具参数必须是 JSON 对象」，不发起会话。
- 路由层再按发现到的 `inputSchema` 校验：schema 不是 `type: 'object'` 时跳过校验；缺必填项报「工具参数校验失败：缺少必填参数 X」；类型不符报「工具参数校验失败：参数 X 应为 Y 类型」。
- 类型检查覆盖 string、number、integer、boolean、object、array；integer 不接受布尔，number 不接受布尔。
- 校验失败不发起对 MCP 服务器的调用，路由转成 HTTP 400，detail 为校验消息。

### 关键实现
- `python_backend/modules/execution/tools.py:validate_tool_arguments` —— 必填项与类型校验
- `python_backend/api/routers/mcp.py:_mcp_config` —— 从 `input_schema.mcp` 取连接配置

## 错误信息脱敏

### 入口
- `python_backend/modules/mcp/__init__.py:McpError` —— MCP 交互失败的异常类型

### 行为
- 错误消息只描述「哪一步失败」，不包含命令、参数、环境变量值或本机路径：启动失败统一为「无法启动 MCP 服务器」，与具体命令无关。
- 未知命令、缺失脚本等场景不把命令行拼进消息；模块的 `McpError` 文档串明确该约定。
- `GET /harness/mcp/servers` 与 `POST .../call` 的响应体不回显 `command`、`args`、`env` 或本机路径；连接配置只从登记项读出、不外发。
- 探测与调用失败时对调用方只暴露 `ok=False` 与脱敏后的 message。

### 关键实现
- `python_backend/modules/mcp/__init__.py:_StdioSession.__enter__` —— 启动异常统一转 `McpError`
- `python_backend/modules/mcp/__init__.py:probe_stdio_server` —— 异常收敛为脱敏 message

## 工具登记与审批链衔接

### 入口
- `python_backend/infrastructure/registry_store.py:list_mcp_servers` —— 列出登记了 MCP 连接配置的工具
- `python_backend/infrastructure/registry_store.py:create_tool` —— 登记工具
- `python_backend/modules/execution/tools.py:prepare_tool_call` —— 工具执行前的统一入口（白名单 + 参数校验 + 审批）
- `python_backend/modules/execution/tools.py:enforce_approval` —— 按登记策略阻塞等待人工审批

### 行为
- MCP 服务器即「登记了连接配置的工具」：连接配置放在登记项的 `input_schema.mcp` 里（形状 `{command, args, env}`），`input_schema` 同时承载工具入参 schema；登记项的 `source` 用 `mcp:` 前缀标记连接方式（如 `mcp:local`）。
- `list_mcp_servers` 只返回 `input_schema.mcp` 是对象的登记项，字段为 `tool_id`、`name`、`source`、`status`。
- 审批链的通用规则（来自 `prepare_tool_call`）：先查本次运行的工具白名单（不在名单内直接拒绝），再按登记的 `input_schema` 校验参数，最后按登记项的 `approval_policy` 与 `risk` 决定是否阻塞等待审批。
- 审批策略判定：`approval_policy` 为 `always` 时必审；`risk-based` 只有 `risk='high'` 才审；策略非 always/required 则不审。没有 run 上下文（`run_id` 为空）时不阻塞；`HARNESS_APPROVAL_ENFORCE` 置 0 时整段审批跳过。
- 审批请求详情只写参数名与类型摘要，不写参数值；超时或被拒时抛 ValueError，消息分别为「等待工具审批超时（N 秒），未执行该工具」「工具审批被拒绝，未执行该工具」「工具审批已过期，未执行该工具」。
- 本模块的 HTTP 路由只调用 `validate_tool_arguments` 做参数校验，不走 `prepare_tool_call`：MCP 工具经由 `/harness/mcp/servers/.../call` 调用时，运行级白名单与人工审批策略都不生效，审批链目前只作用在 Agent 工具调用路径上。

### 关键实现
- `python_backend/infrastructure/registry_store.py:list_mcp_servers` —— 以 `input_schema.mcp` 判定 MCP 服务器
- `python_backend/modules/execution/tools.py:prepare_tool_call` —— 白名单 → 校验 → 审批三段顺序
- `python_backend/modules/execution/tools.py:_summarize_arguments` —— 审批详情只留键名与类型

## 数据与存储

- 登记项落在 `harness_tool` 表（SQLite，库文件 `harness-registry.db`，位于配置的 data 目录下），字段含 `tool_id`、`name`、`source`、`scope`、`risk`、`status`、`description`、`input_schema`（JSON 文本）、`approval_policy`、`revision`。
- MCP 连接配置不是独立表，而是作为 `input_schema` JSON 里的 `mcp` 键存放，与工具入参 schema 同一份 JSON。
- 本模块自身无独立持久化：会话、请求 id、响应队列全部在进程内存中，随会话结束回收；工具调用的结果不落库，HTTP 响应体只包含 `ok`、`content`、`isError`、`message`。
- 审批记录写在治理库（`harness-governance.db`），由治理模块持有，本模块只发起与等待。

## 接口清单

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/harness/mcp/servers` | 列出已登记的 MCP 服务器，并逐个探测其已发现的工具名 |
| `POST` | `/harness/mcp/servers/{tool_id}/tools/{tool_name}/call` | 调用某个 MCP 服务器上的指定工具（请求体 `{"arguments": {...}}`） |
| `POST` | `/harness/tools/{tool_id}/test` | 登记项连接测试；`source` 以 `mcp:` 开头时执行 initialize 探测 |
| `GET` | `/harness/tools` | 工具登记列表（含 MCP 登记项） |
| `POST` | `/harness/tools` | 登记工具（含 MCP 连接配置写入 `input_schema.mcp`） |
| `PUT` | `/harness/tools/{tool_id}` | 更新工具登记（含连接配置与审批策略） |

## 边界与已知限制

- 只支持 stdio 传输：没有 SSE、没有 HTTP/SSE 流式传输，也没有 TCP 通道。
- 只实现三个 MCP 方法：`initialize`、`tools/list`、`tools/call`；不涉及 resources、prompts、notifications、sampling，也不发 `notifications/initialized`。
- 不引入 MCP SDK，JSON-RPC 消息按行分隔自行解析；只支持 JSON 对象形式的 `result`。
- 每次探测、发现、调用都各起一个新进程，没有长连接会话：依赖跨调用保持状态的 MCP 服务器用不了；N 个已登记服务器会让清单接口起 N 个进程。
- 协议版本硬编码为 `2024-11-05`，不与服务端协商，也不读取服务端声明的版本做校验。
- 只回读 `serverInfo.name` 与 `protocolVersion`，服务端的 capabilities、资源、提示词一律丢弃。
- 路由层的工具调用不经过 `prepare_tool_call`：运行级工具白名单与人工审批策略对这条路径不生效（审批链只在 Agent 工具调用路径上生效）。
- 登记项里的 `command` 与 `args` 由登记方决定，连接器不做可执行路径白名单校验，也不限制 `env` 里能放什么键；`env` 以宿主环境为底叠加，宿主环境里的凭据会一并传给子进程，这些值不出现在任何响应或错误消息中。
- stderr 被丢弃：MCP 服务器的诊断输出无法从本模块取回，排障只能靠返回值。
- 前端 `frontend/src/modules/mcp/` 只有占位文件，MCP 界面由 `frontend/src/HarnessApp.vue` 的「工具与 MCP」面板承担，与其它能力模块的前端组织方式不一致。
