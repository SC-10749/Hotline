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

当前运行方式是把绑定版本的技能正文加载到 dodoagent 的模型上下文；需要配置模型才能生成实际回答。平台暂不执行技能包脚本或安装依赖。平台断开时记录警告，保留本地技能和现有降级行为。

## Skill 自进化

平台提供本地、可审计的自进化闭环：评测用例按 `train`、`selection`、`test` 三段保存；`evolve` 只接受最多 8 条 `add/delete/replace` patch，自动执行静态、动态、回归、增益和安全门禁。通过后候选以 `staged` 保存，不会自动改变线上绑定；再用 `promote` 灰度绑定，或用 `rollback` 恢复上一版本。

示例请求：

```json
{"action":"eval_case","args":{"caseId":"incident-1","split":"selection","case":{"required":["输出影响"],"forbidden":["泄露密钥"]}}}
```

```json
{"action":"evolve","args":{"name":"example","baseVersion":"v1","patches":[{"op":"add","text":"输出前检查敏感信息。"}]}}
```

`evaluate` 可单独查看评分，`promote` 接受 `project`、`name`、`version` 和 `percentage`，`rollback` 按项目和技能恢复上一绑定版本。每次演化都会在 SQLite 中保存 patch、门禁结果和新旧分数，便于人工审查和回滚。`evolve` 接收外部 bounded patch，`auto_evolve` 则在配置模型后自动生成 patch。

### 自动反思、沙箱与灰度

配置 `SKILL_EVOLUTION_BASE_URL`、`SKILL_EVOLUTION_API_KEY`、`SKILL_EVOLUTION_MODEL` 后，`auto_evolve` 会把 train 失败用例交给独立模型，只接收 bounded patch；配置 `SKILL_JUDGE_BASE_URL`、`SKILL_JUDGE_API_KEY`、`SKILL_JUDGE_MODEL` 后，`judge` 可对执行输出做独立评分。`run_case` 只接受字符串数组命令，使用临时工作目录、无 shell、限时和最小环境执行，并把 `required/forbidden` verifier 结果写回响应。

`promote` 会保存候选和旧版本，运行时传入 `requestId` 时按稳定哈希命中灰度比例；`metric` 记录错误率等指标，达到 `SKILL_ROLLOUT_ERROR_THRESHOLD` 且样本数达到 `SKILL_ROLLOUT_MIN_SAMPLES` 时自动回滚。控制台的 **Skill 自进化** 页面可直接提交 patch、查看门禁结果和 staged 状态。
