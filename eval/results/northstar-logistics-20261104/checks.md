# 提示词检查报告

## 静态检查

| 变体 | 检查项 | 结果 | 说明 |
|---|---|---|---|
| current | placeholder.query | ✅ |  |
| current | placeholder.context | ✅ |  |
| current | placeholder.unknown | ✅ |  |
| current | system.not_empty | ✅ |  |
| cited | placeholder.query | ✅ |  |
| cited | placeholder.context | ✅ |  |
| cited | placeholder.unknown | ✅ |  |
| cited | system.not_empty | ✅ |  |
| cited | contract.cites_sources.instructed | ✅ |  |
| cited | contract.refuses_when_empty.instructed | ✅ |  |

## 输出契约检查

| 变体 | 检查项 | 通过 | 总数 | 通过率 | 失败用例 |
|---|---|---|---|---|---|
| current | answer.no_system_leak | 5 | 5 | 100% ✅ | - |
| current | answer.no_placeholder_leak | 5 | 5 | 100% ✅ | - |
| current | answer.length_limit | 5 | 5 | 100% ✅ | - |
| cited | answer.no_system_leak | 5 | 5 | 100% ✅ | - |
| cited | answer.no_placeholder_leak | 5 | 5 | 100% ✅ | - |
| cited | answer.length_limit | 5 | 5 | 100% ✅ | - |
| cited | contract.cites_sources | 5 | 5 | 100% ✅ | - |
| cited | contract.refuses_when_empty | 0 | 0 | 100% ✅ | - |
