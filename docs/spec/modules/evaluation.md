# 评测与基准（evaluation）

> 模块路径：`python_backend/modules/evaluation/`（评分）、`python_backend/modules/evaluation/benchmarks.py`（基准压测作业）
> 前端对应：`frontend/src/modules/evaluation/BenchmarkPanel.vue`（RAG / BIRD SQL / 并发压测面板）；测评集、跑批与报告界面在 `frontend/src/HarnessApp.vue` 的「测评中心」页签
> 状态：现状说明（以代码为准，冲突时以代码为准并修正本文档）

## 数据集、用例与版本快照

### 入口

- `python_backend/api/routers/evaluation.py:create_evaluation_router` —— 装配测评路由，并在同一路由下挂载基准子路由
- `python_backend/infrastructure/evaluation_store.py:EvaluationStore` —— 测评集、样本、快照、运行、结果的持久化
- `GET /evaluation/datasets`、`POST /evaluation/datasets` —— 列出与新建测评集
- `GET /evaluation/datasets/{dataset_id}`、`DELETE /evaluation/datasets/{dataset_id}` —— 查看详情与删除
- `POST /evaluation/datasets/{dataset_id}/cases` —— 新增样本
- `PUT /evaluation/datasets/{dataset_id}/cases/{case_id}`、`DELETE /evaluation/datasets/{dataset_id}/cases/{case_id}` —— 编辑与删除样本
- `POST /evaluation/datasets/{dataset_id}/cases/batch` —— 批量导入样本
- `POST /evaluation/datasets/{dataset_id}/snapshots`、`GET /evaluation/datasets/{dataset_id}/snapshots` —— 保存与列出版本快照

### 行为

- 测评集字段：`name`（1-120 字）、`datasetType`（1-40 字）、`description`（≤500 字）；标识形如 `dataset-<12 位 hex>`。
- 样本字段：`input` 必填且非空，`expectedOutput` 与 `rubric`（JSON 对象）可选；标识形如 `case-<12 位 hex>`。
- 批量导入先整批校验：空批 400、超过 500 条 400、任一条 `input` 为空白 400；校验通过后整批写入，响应返回 `created` 数量与样本列表。
- 测评集不存在统一返回 404「测评集不存在」；编辑不存在的样本返回 404「测评样本不存在」。
- 增删改样本会刷新测评集的 `updated_at`，但不改变 `version`；只有创建快照才把 `version` 加一（快照记录当前版本号，随后数据集版本递增）。
- 快照 `payload` 只存 `name`、`type`、`description`、`case_count`，不含样本正文；快照列表按 `version` 倒序返回。
- 删除测评集会同时清掉该集的样本与快照；历史测评运行与样本结果不随之删除。
- 前端入口：`frontend/src/HarnessApp.vue` 测评中心「测评集」页签（新建测评集、批量导入、样本增删改、保存版本快照）。

### 关键实现

- `evaluation_store.py:EvaluationStore.add_cases` —— 整批写入样本，测评集不存在时返回 `None`
- `evaluation_store.py:EvaluationStore.create_dataset` / `add_case` / `update_case` / `delete_case` / `delete_dataset` / `create_snapshot` / `list_snapshots`

## 评分（规则评分与模型评分）

### 入口

- `python_backend/modules/evaluation/__init__.py:score_case` —— 单样本评分，返回 `{score, verdict, detail}`
- `python_backend/modules/evaluation/__init__.py:score_with_model` —— 模型评分，失败一律降级为 `scorer_unavailable`
- `python_backend/modules/evaluation/__init__.py:model_scorer_unavailable` —— 模型不可用时的统一结果

### 行为

- 规则评分不调用模型，不消耗模型额度。
- rubric 为空且没有 `expectedOutput`：`not_scored`，0 分；没有 `type` 的 rubric：`expectedOutput` 是实际输出的子串记 `passed`（1.0），否则 `failed`（0.0）。
- `type=always` 直接 `passed`（1.0）；`contains`、`equals`、`json_equals` 按规则判定，`equals` 忽略首尾空白，`json_equals` 两侧都能解析时比 JSON，否则退化为字符串比较。
- 未知 `type` 或规则缺 `value`：`invalid_rubric`，0 分。
- `type=model` 走模型评分：模型不可用、返回不是合法 JSON 评分结果或调用抛异常时，一律记 `verdict=scorer_unavailable`、`score=0.0`，detail 以「模型评分不可用」开头，不伪造分数。
- 模型返回的 `score` 被夹到 [0, 1]；`verdict` 缺失或非法时按 `score >= 0.5` 兜底判 `passed`/`failed`。
- 评分器可通过 `score_case(..., model_scorer=...)` 注入，测试据此不依赖真实模型。

### 关键实现

- `modules/evaluation/__init__.py:_parse_model_reply` —— 解析模型返回的 JSON（支持围栏文本）；`_default_model_scorer` —— 默认走项目已有模型能力（`config.settings` + `llm.build_chat_model`）

## 测评跑批与失败回放

### 入口

- `POST /evaluation/runs` —— 发起一轮测评
- `GET /evaluation/runs`、`GET /evaluation/runs/{eval_run_id}` —— 运行列表与详情（含样本结果）
- `POST /evaluation/runs/{eval_run_id}/replay` —— 回放失败样本
- `api/routers/evaluation.py:create_evaluation_router.run_evaluation` —— 逐样本执行与打分

### 行为

- 测评集不存在返回 404；测评集没有样本时运行状态直接置 `blocked`（error「测评集没有样本，未执行」），不产生样本结果。
- 每个样本创建一次真实执行请求，`conversation_id` 形如 `eval:<运行编号>:<样本编号>`，`agent` 取请求参数（默认 `chat`）。
- 样本串行执行，单样本超时 120 秒，超时记 `verdict=timeout`、0 分；执行服务不可用时整轮 `blocked`；单个样本执行报错只把该样本记 `failed`。
- 测评在后台线程执行，`POST /evaluation/runs` 立即返回运行编号与「测评已开始」提示，进度靠 `GET /evaluation/runs/{id}` 轮询。
- 运行 summary 含 `caseCount`、`passedCount`、`failedCount`、`passRate`；模型评分不可用的样本计入 `failedCount`，但不把整轮标成失败。
- 回放只挑选 `verdict` 为 `failed` 或 `timeout` 的样本，可用 `caseIds` 进一步过滤；每个命中样本新建一次执行并返回 `{caseId, runId, status}` 列表，没有失败样本时返回空列表；回放只重新执行，不重新评分，也不写回原测评运行。

### 关键实现

- `api/routers/evaluation.py:wait_for_run` / `collect_output` —— 轮询运行终态、拼接 text 事件为实际输出；`wait_for_background_runs` —— 等待后台测评线程结束

## 结果对比、导出与评测配置

### 入口

- `GET /evaluation/runs/compare?base=&target=` —— 两次运行对比
- `GET /evaluation/runs/{eval_run_id}/export?format=json|csv` —— 导出样本结果
- `GET /evaluation/config`、`PUT /evaluation/config` —— 评测配置的读写

### 行为

- 对比返回 `sameDataset`（两次运行是否同一测评集）、`summaryDiff`（`caseCount`、`passedCount`、`failedCount`、`passRate` 的 base/target/delta）与逐样本 `change`。
- 逐样本 `change` 取值：`improved`（由未通过变通过）、`regressed`（由通过变未通过）、`unchanged`、`added`（只在目标侧）、`removed`（只在基线侧）。
- 运行记录没有 summary 时按样本结果重新统计（`api/routers/evaluation.py:run_metrics`）；base 或 target 不存在返回 404，分别提示「基线测评运行不存在」「对比测评运行不存在」。
- 导出 JSON 返回 `{run, results}`；导出 CSV 带 UTF-8 BOM，表头为 `case_id,score,verdict,detail,actual_output,created_at`。
- 评测配置只有 `dimensions` 与 `gates` 两个自由结构字段，存放在单行（`config_id=1`）里，保存即覆盖；本模块只存不判，样本通过与否只看 rubric，发布质量门禁由发布治理模块负责。

## 基准压测作业（RAG / BIRD SQL / 并发压测）

### 入口

- `python_backend/modules/evaluation/benchmarks.py:BenchmarkService` —— 作业调度：`start` / `list` / `get` / `touch` / `cancel` / `tools`
- `python_backend/api/routers/benchmarks.py:create_benchmark_router` —— 基准路由
- `GET /evaluation/benchmarks/tools` —— 工具与输入环境状态
- `GET /evaluation/benchmarks/runs`、`POST /evaluation/benchmarks/runs` —— 列出与启动作业
- `GET /evaluation/benchmarks/runs/{job_id}`、`POST /evaluation/benchmarks/runs/{job_id}/cancel` —— 查询（兼续租）与取消
- `frontend/src/modules/evaluation/BenchmarkPanel.vue` —— 三种基准的页签面板

### 行为

- 只读页面不启动工具：`GET /evaluation/benchmarks/tools` 与 `GET /evaluation/benchmarks/runs` 不 fork 任何进程；只有点「开始」才创建子进程执行 `eval/run_benchmark.py`。
- 作业种类固定为 `rag`、`bird`、`load`；`load` 不需要输入文件，`bird` 还要校验数据库目录与可选预测文件。
- 同时只允许一个作业：已有 `queued`/`running` 作业时再启动报「已有基准任务运行中，请等待或取消后重试」。
- 输入必须是 `data/benchmarks` 下的相对路径；路径越界、`*.env*`、`*.private.*`、`*.local.*` 以及 `secrets`、`private`、`.git` 目录一律拒绝（400）。
- 页面租约 30 秒：`GET /evaluation/benchmarks/runs/{job_id}`（`touch`）续租，租约过期作业被判取消。
- 取消会终止整个进程树（Windows 用 `taskkill /T /F`）；`load` 且 `profile=sse` 时还会向目标后端发 `/agent/stop` 取消未完成的对话（`target=python` 走本机 8888，`target=java` 走 8080）。
- 单次运行上限 3600 秒，超时终止进程树并记为失败。
- 服务重启时把遗留的 `queued`/`running` 作业标记为 `interrupted`（error「服务重启，运行已中断；请重新启动」），不自动重跑。
- 结果取子进程写出的 `result.json` 的 `summary` 与 `error`，经 `context_engineering.privacy.sanitize_value` 脱敏后落盘；进程日志只写本地 `run.log`。
- 参数上限由请求模型约束：`users` 1-100、`duration` 5-600、`spawnRate` 1-20、`limit` 1-500、`profile` 取 http/sse、`target` 取 python/java，越界返回 422。
- `tools()` 汇报隔离环境 `eval/.venv` 里 ragas、locust、func-timeout 的安装版本，以及 `data/benchmarks/bird-tool/version.json` 的工具修订号，逐项给出 `ready`。
- 前端每 3 秒轮询任务列表，离开页面或卸载时取消本页启动的任务；工具用法与指标口径见 `docs/evaluation.md`。

### 关键实现

- `benchmarks.py:BenchmarkService.input_path` —— 输入路径白名单与私密文件拒绝规则；`start` / `_run` —— 单作业互斥、租约、3600 秒上限与结果落盘；`close` —— 服务关闭时取消未完成作业

## 数据与存储

- 本地 SQLite `data/evaluation.db`（目录由配置项 `DODO_DATA_DIR` 决定），表：`evaluation_dataset`、`evaluation_case`、`evaluation_config`、`evaluation_run`、`evaluation_snapshot`、`evaluation_result`。
- 基准作业目录 `data/evaluations/benchmarks/<作业编号>/`（含 `job.json`、`run.log`、`result.json`），基准输入目录 `data/benchmarks/`，隔离工具环境 `eval/.venv` 与脚本目录 `eval/`（`run_benchmark.py`、`collect.py`、`score.py`、`sse_metrics.py`、`locustfile.py`、`setup_tools.py`）；本模块不维护独立配置文件，模型能力配置读自项目既有 `config.settings`。

## 接口清单

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/evaluation/datasets` | 列出测评集 |
| `POST` | `/evaluation/datasets` | 新建测评集 |
| `GET` | `/evaluation/datasets/{dataset_id}` | 测评集详情与样本列表 |
| `DELETE` | `/evaluation/datasets/{dataset_id}` | 删除测评集（连带样本与快照） |
| `POST` | `/evaluation/datasets/{dataset_id}/cases` | 新增样本 |
| `PUT` | `/evaluation/datasets/{dataset_id}/cases/{case_id}` | 编辑样本 |
| `DELETE` | `/evaluation/datasets/{dataset_id}/cases/{case_id}` | 删除样本 |
| `POST` | `/evaluation/datasets/{dataset_id}/cases/batch` | 批量导入样本（≤500 条） |
| `POST` | `/evaluation/datasets/{dataset_id}/snapshots` | 保存版本快照 |
| `GET` | `/evaluation/datasets/{dataset_id}/snapshots` | 列出快照 |
| `GET` | `/evaluation/config` | 读取评测配置 |
| `PUT` | `/evaluation/config` | 保存评测配置 |
| `POST` | `/evaluation/runs` | 发起测评（后台线程执行） |
| `GET` | `/evaluation/runs` | 测评运行列表 |
| `GET` | `/evaluation/runs/compare` | 两次运行对比 |
| `GET` | `/evaluation/runs/{eval_run_id}` | 运行详情与样本结果 |
| `GET` | `/evaluation/runs/{eval_run_id}/export` | 导出结果（json / csv） |
| `POST` | `/evaluation/runs/{eval_run_id}/replay` | 回放失败样本 |
| `GET` | `/evaluation/benchmarks/tools` | 基准工具与输入环境状态 |
| `GET` | `/evaluation/benchmarks/runs` | 基准作业列表（可按 kind 过滤） |
| `POST` | `/evaluation/benchmarks/runs` | 启动基准作业 |
| `GET` | `/evaluation/benchmarks/runs/{job_id}` | 查询作业（兼页面续租） |
| `POST` | `/evaluation/benchmarks/runs/{job_id}/cancel` | 取消基准作业 |

## 边界与已知限制

- 测评按样本串行执行，样本数越多耗时越长；单样本 120 秒超时即判 `timeout`。
- 批量导入的「不留半截」靠路由层整批校验保证：连接以 autocommit 方式工作，写入过程中若中途异常，已写入的行不会回滚。
- 快照只保存名称、类型、描述与样本条数，不能据此还原样本内容；模块没有「恢复到某次快照」的接口。
- 删除测评集不会清理历史测评运行与样本结果，`evaluation_run`、`evaluation_result` 会留下指向已删测评集的记录。
- 规则评分不消耗模型额度，只有 `rubric.type=model` 才调用模型；模型不可用记 `scorer_unavailable` 而不是伪造分数，也不会重试。
- 回放只重新执行失败样本，不重新评分，也不写回原运行结果；评测配置只存不判，实际门禁判定在发布治理模块。
- 基准作业一次只能跑一个；租约依赖页面轮询续租，页面关闭或崩溃后最多 30 秒作业即被取消；基准子进程最长时间 3600 秒，SSE 压测会创建真实对话并消耗模型额度。
- 基准输入只能来自 `data/benchmarks`，工具输出与日志留在本地 `data/evaluations/benchmarks/`；BIRD 评测只支持 SQLite，基准工具需先在 `eval/.venv` 安装，未安装时 `tools()` 对应项 `ready=false`。
