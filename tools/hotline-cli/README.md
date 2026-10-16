# Hotline 本地控制台

维护目录：tools/hotline-cli。负责扫描项目、管理本次控制台创建的进程、提供本地页面；不安装项目依赖，不管理已有外部进程。

运行 `npm run dashboard`（本目录）或根目录 `npm run dev`，打开 http://127.0.0.1:4311。

## 契约

- GET /api/projects：返回项目元数据、清单错误和进程状态。
- GET /api/logs?id=项目路径：返回最近 64KB 日志。
- GET /api/readme?id=项目路径：返回项目说明、overview 摘要和 README.md 原文。只读取已发现项目目录内的 README。
- POST /api/start?id=项目路径：在项目目录执行 commands.start 或 commands.run；重复启动返回冲突。
- POST /api/stop?id=项目路径：终止控制台创建的项目进程树。
- 写请求须携带首页生成的 X-Hotline-Token；仅监听 127.0.0.1，校验 Host 和 Origin，不提供任意命令接口。
- 无数据库；状态和日志仅保存在内存，重启清空。启动后先显示“启动中”，页面 URL 与 healthChecks 中的地址均返回 HTTP 2xx 后才显示“已启动”和可点击链接；不自动跳转。可在启动中停止项目。

项目清单可配置 `url`（页面入口）、`healthChecks`（额外健康检查地址数组）与 `overview`。overview 包含 `techStack`、`features`、`startup` 字符串数组，以及 `services` 数组（每项为 name、requirement、description），用于卡片 Readme 弹窗。未整理摘要时展示语言及完整 README 原文。Readme 在项目未启动时也可查看，支持 Esc 关闭。

每张应用卡片右上角显示 `project.yaml` 中 `status` 对应的开发状态：`idea` 为规划中，`prototype` 为原型验证，`working` 为开发中，`completed` 或 `stable` 为开发完成，`archived` 为已归档；缺失或未知值显示未标注。筛选栏使用同一组状态。卡片下方单独显示已启动、已停止等运行状态，开发完成不等于服务正在运行。更新项目状态只需修改清单，例如 `status: completed`，不需要改变启动命令。

点击已启动项目的页面链接，在新标签页打开项目。左侧显示项目中心，以及标记“规划”的 Harness 工作台、Skill 中心、工具与 MCP 中心、评测中心、CI/CD 中心和运行观测菜单；点击规划菜单只显示计划说明，不接入实际功能。完整计划记录在仓库根目录 FUTURE_PLAN.md。不恢复项目分类菜单。

命令优先使用参数数组，例如 `run: [node, src/server.mjs]`；字符串通过系统 shell 执行，只能使用可信项目清单。数组不经 shell，不支持 shell 管道。

停止在 Windows 使用 taskkill /T /F；Unix 终止进程组。应以前台方式启动项目，不支持主动脱离进程树的守护服务。Ctrl+C 关闭控制台时清理其项目进程。

验证：npm run build；node --test tests/dashboard.test.mjs。无需新依赖，页面为原生 HTML/CSS/JS。
