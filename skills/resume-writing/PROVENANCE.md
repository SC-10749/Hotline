# 来源与许可（Provenance）

本目录的 `references/` 是从 GitHub 开源项目下载的**原文**，未做删改；`SKILL.md` 是本仓库基于这些原文提炼的中文执行规范。

| 项 | 内容 |
| --- | --- |
| 上游仓库 | https://github.com/paramchoudhary/ResumeSkills |
| 星数 | 3.3k（抓取时点见 PROVENANCE.json 的 fetched_at） |
| 分支 | main |
| 引入的子技能 | resume-bullet-writer、tech-resume-optimizer、resume-ats-optimizer、resume-quantifier |
| 落地路径 | `references/{bullet-writer,tech-resume-optimizer,ats-optimizer,quantifier}.md` |

## 刷新上游

`python skills/resume-writing/fetch_upstream.py`

脚本会重新下载这 4 份原文、记录每个文件的 sha256 与字节数、重新抓取星数，并覆写 `PROVENANCE.json`。上游改动后重跑即可，不要手工改 `references/` 里的原文。

## 使用约定

- 上游原文只作参考与引用，不作为本仓库产品逻辑；本仓库的执行口径以 `SKILL.md` 为准。
- 上游内容若包含示例数据（如示例人名、示例指标），一律不要写进真实简历。
- 保留上游出处链接，便于追溯与致谢；如上游仓库更换许可或下架，停止引用并按 `SKILL.md` 自行维护。