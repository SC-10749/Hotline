# Python Skill 中心

Python 3.11+，仅使用标准库。由 Hotline 控制台启动短生命周期 Python 进程，SQLite 保存不可变技能版本和项目绑定；无需额外启动服务。数据位于根目录 `data/skill-center/catalog.db`，已排除 Git。

## 使用

1. 重启 Hotline 控制台（根目录 `pnpm --filter @hotline/cli dashboard`）。Windows 默认复用 dodo-agent 的 `.venv/Scripts/python.exe`，其他环境可用 `HOTLINE_PYTHON` 指定 Python 可执行文件。
2. 打开 **Skill 中心**，编写 `SKILL.md`，保存后点击“绑定此版本到 dodoagent”。保存新版本不会改变现有绑定；点击旧版本的绑定按钮可以回退。
3. 重启 dodoagent 以加载新的 Python 代码。在其技能智能体中输入 `$incident-summary 请根据以下材料复盘……`。每次技能请求读取平台当前绑定版本。也可用技能名、描述自动匹配。

dodoagent 默认访问 `http://127.0.0.1:4311/api/skills`，项目 ID 为 `projects/ai/dodo-agent`。远程运行或自定义端口时，在根目录私密配置中设置 `HOTLINE_SKILLS_URL` 与 `HOTLINE_PROJECT_ID`。将 URL 设为空可关闭平台技能接入。此接口沿用平台仅监听本机的访问边界，没有远程认证，不应直接开放公网。

## 研究样本

来源：[Anthropic 官方 skills 仓库](https://github.com/anthropics/skills)。`samples/sources.json` 记录固定提交号，完整子目录与许可证保存在 `samples/`。这些文件属于研究数据，不是本仓库开发的行为指令。

- frontend-design：短指令型技能。
- webapp-testing：测试流程及 Python 脚本。
- mcp-builder：协议开发及分层参考资料。
- skill-creator：技能编写、评估与迭代参考。

从仓库根目录执行（PowerShell）：

```powershell
# 样本已拉取；需要更新上游时执行，会重新解析 main 并保存提交号
& projects/ai/dodo-agent/.venv/Scripts/python.exe tools/skill-center/pull_samples.py
# 导入样本到平台，默认不绑定，不自动执行脚本
& projects/ai/dodo-agent/.venv/Scripts/python.exe tools/skill-center/import_samples.py
# 验证版本、回退、绑定隔离和 dodoagent HTTP 读取/提示加载
& projects/ai/dodo-agent/.venv/Scripts/python.exe tools/skill-center/test_center.py
```

## 接口与实现边界

平台 `GET /api/skills` 查看版本/绑定；`GET /api/skills?project=projects/ai/dodo-agent` 读取项目绑定。`POST /api/skills` 需要现有页面的 `X-Hotline-Token`，JSON 请求：

```json
{"action":"save","args":{"content":"---\nname: example\ndescription: Example skill\n---\nInstructions","resources":{}}}
```

```json
{"action":"bind","args":{"project":"projects/ai/dodo-agent","name":"example","version":"v1"}}
```

`version: null` 解除绑定。同一技能按 v1、v2、v3 递增；内容哈希覆盖 SKILL.md 和资源文本，用于去重，相同内容重复保存仍返回原版本；旧版哈希编号和绑定自动迁移；`source` 保存来源；保存幂等。资源使用相对路径到 UTF-8 文本的映射，原始二进制资产保留于样本目录。当前编辑器仅支持单行 name/description，不是完整 YAML 解析器。

当前运行方式是把绑定版本的技能正文加载到 dodoagent 的模型上下文；需要配置模型才能生成实际回答。尚不支持脚本沙箱、资源读取工具、依赖安装、自动评分或自动演化。界面所有版本标记为“未评测”，版本号也不代表效果质量。平台断开时记录警告，保留本地技能和现有降级行为。

后续自进化可在这些不可变版本上增加固定任务集、运行轨迹、评分与候选晋升流程。现在保存候选不会替换已绑定版本，可用于先人工对比再切换的实验。
