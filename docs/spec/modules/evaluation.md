# 评测与基准（evaluation）

> 模块路径：`python_backend/modules/evaluation/`（评分）、`python_backend/modules/evaluation/analysis.py`（轨迹、门禁、出处）、`python_backend/modules/evaluation/benchmarks.py`（基准压测作业）
> 前端对应：`frontend/src/modules/evaluation/BenchmarkPanel.vue`（RAG / BIRD SQL / 并发压测面板）、`frontend/src/modules/evaluation/AgentEvalPanel.vue`（Agent 测评面板）；测评集、跑批与报告界面在 `frontend/src/modules/harness/panels/EvaluationsPanel.vue` 的「测评中心」页签
> 变更规格：[S-002](../../spec/2026-11-23-Agent测评增强.md)、[S-003](../../spec/2026-11-23-多轮评测与门禁CLI.md)、[S-004](../../spec/2026-11-23-并行跑批与预算护栏.md)、[S-005](../../spec/2026-11-23-语义评分与工具调用断言.md)、[S-006](../../spec/2026-11-23-评测矩阵视图.md)、[S-012](../../spec/2026-11-23-评测可读性.md)
> 状态：现状说明（以代码为准，冲突时以代码为准并修正本文档）

## 数据集、用例与版本快照

### 入口

- `python_backend/api/routers/evaluation.py:create_evaluation_router` —— 装配测评路由，并在同一路由下挂载基准子路由
- `python_backend/infrastructure/evaluation_store.py:EvaluationStore` —— 测评集、样本、快照、运行、结果的持久化
- `GET /evaluation/datasets`、`POST /evaluation/datasets` —— 列出与新建测评集；列表项带 `lastRun`（该测评集最近一次运行的 runId / status / agent / epochs / createdAt / passRate，没跑过时为 `null`，规格 S-007）
- `GET /evaluation/datasets/{dataset_id}`、`DELETE /evaluation/datasets/{dataset_id}` —— 查看详情与删除
- `POST /evaluation/datasets/{dataset_id}/cases` —— 新增样本
- `PUT /evaluation/datasets/{dataset_id}/cases/{case_id}`、`DELETE /evaluation/datasets/{dataset_id}/cases/{case_id}` —— 编辑与删除样本
- `POST /evaluation/datasets/{dataset_id}/cases/batch` —— 批量导入样本
- `POST /evaluation/datasets/{dataset_id}/snapshots`、`GET /evaluation/datasets/{dataset_id}/snapshots` —— 保存与列出版本快照

### 行为

- 测评集字段：`name`（1-120 字）、`datasetType`（1-40 字）、`description`（≤500 字）；标识形如 `dataset-<12 位 hex>`。
- 样本字段：`input` 必填且非空，`expectedOutput` 与 `rubric`（JSON 对象）可选；标识形如 `case-<12 位 hex>`。
- 样本另有两个可选字段（规格 S-003）：`turns`（数组，用户首轮之后的每一句话）、`userProfile`（字符串，模拟用户画像）；存库字段名是 `turns` 与 `user_profile`。
- 批量导入先整批校验：空批 400、超过 500 条 400、任一条 `input` 为空白 400；校验通过后整批写入，响应返回 `created` 数量与样本列表。
- 测评集不存在统一返回 404「测评集不存在」；编辑不存在的样本返回 404「测评样本不存在」。
- 增删改样本会刷新测评集的 `updated_at`，但不改变 `version`；只有创建快照才把 `version` 加一（快照记录当前版本号，随后数据集版本递增）。
- 快照 `payload` 存 `name`、`type`、`description`、`case_count`，并额外存 `cases`（快照时刻的样本正文：case_id、input_text、expected_output、rubric）与 `sha256`（对 cases 规范化 JSON 取 sha256）；快照列表按 `version` 倒序返回。
- 删除测评集会同时清掉该集的样本与快照；历史测评运行与样本结果不随之删除。
- 前端入口：`frontend/src/modules/harness/panels/EvaluationsPanel.vue` 测评中心「测评集」页签（新建测评集、批量导入、样本增删改、保存版本快照）。

### 关键实现

- `evaluation_store.py:EvaluationStore.add_cases` —— 整批写入样本，测评集不存在时返回 `None`
- `evaluation_store.py:EvaluationStore.create_dataset` / `add_case` / `update_case` / `delete_case` / `delete_dataset` / `create_snapshot` / `list_snapshots`

## 评分（规则评分与模型评分）

### 入口

- `python_backend/modules/evaluation/__init__.py:score_case` —— 单样本评分，返回 `{score, verdict, detail}`
- `python_backend/modules/evaluation/__init__.py:score_with_model` —— 模型评分，失败一律降级为 `scorer_unavailable`
- `python_backend/modules/evaluation/__init__.py:model_scorer_unavailable` —— 模型不可用时的统一结果
- `python_backend/modules/evaluation/semantics.py:SEMANTIC_METRICS` —— 内置语义指标模板库
- `GET /evaluation/semantic-metrics` —— 列出内置语义指标模板

### 行为

- 规则评分不调用模型，不消耗模型额度。
- rubric 为空且没有 `expectedOutput`：`not_scored`，0 分；没有 `type` 的 rubric：`expectedOutput` 是实际输出的子串记 `passed`（1.0），否则 `failed`（0.0）。
- `type=always` 直接 `passed`（1.0）；`contains`、`equals`、`json_equals` 按规则判定，`equals` 忽略首尾空白，`json_equals` 两侧都能解析时比 JSON，否则退化为字符串比较。
- 未知 `type` 或规则缺 `value`：`invalid_rubric`，0 分。
- `type=model` 走模型评分：模型不可用、返回不是合法 JSON 评分结果或调用抛异常时，一律记 `verdict=scorer_unavailable`、`score=0.0`，detail 以「模型评分不可用」开头，不伪造分数。
- 模型返回的 `score` 被夹到 [0, 1]；`verdict` 缺失或非法时按 `score >= 0.5` 兜底判 `passed`/`failed`。
- 评分器可通过 `score_case(..., model_scorer=...)` 注入，测试据此不依赖真实模型。
- `type=trace`（轨迹断言，规格 S-002）：`expect` 支持 `agent`、`minClarify`/`maxClarify`、`expectTools`、`forbidTools`、`maxToolErrors`、`minSteps`；`expect` 为空或含未知键记 `invalid_rubric`；轨迹不可用记 `not_scored`（不判失败也不判通过）；全部条件满足才 `passed`，否则 `failed` 且 detail 列出所有不满足的条件。
- `expect` 另有 `minTurns`/`maxTurns`（对话总轮数上下限，规格 S-003）。
- 轨迹断言新增参数级断言（规格 S-005）：`expectToolCalls`（数组，每项 `{tool, argsContain, argsMatch}`，工具名精确匹配，参数包含/相等逐项校验，失败时 detail 指明差在哪一项）与 `minToolCalls`（工具调用次数下限）。
- 轨迹摘要新增 `toolCalls`（每次工具调用一条 `{tool, args}`）：参数值只留前 40 字符，凭据类参数（键名含 token / secret / password / credential / apikey 等）整条丢弃。
- `type=semantic`（语义指标评分，规格 S-005）：`{"type":"semantic","metric":"topic_adherence","expect":{"topics":["…"]}}`。内置四个指标：`topic_adherence`（必填 `topics`）、`answer_relevance`（无必填）、`fact_consistency`（必填 `context`）、`trajectory_quality`（可选 `mustTools` / `maxSteps`，判分输入含轨迹摘要）。
  - 指标名不在模板库、或缺少该指标必填的 `expect` 参数，记 `invalid_rubric`；模型不可用或返回非法 JSON 记 `scorer_unavailable`，不伪造分数。
  - `trajectory_quality` 在轨迹不可用时记 `not_scored`，不猜。
  - `judgeModelId` 指向模型路由里登记的模型 id；找不到该 id 记 `invalid_rubric`，**不静默换回默认评委**。
  - 判分结果带 `metrics` 维度明细（`score` / `detail` / `judge` / `label`），随结果落库（`evaluation_result.metrics` 列），页面结果明细有「语义维度」列。
  - `multi` 里混用语义与轨迹子规则时，两侧结论各自独立，明细合并进同一个 `metrics`。
- `type=multi`（复合规则）：`{"type":"multi","mode":"all"|"any","rules":[...]}`，子规则可嵌套（深度上限 5），score 取子规则均值，`mode=all` 要全过、`mode=any` 任一过即可。
- `score_case` 新增 `trace` 形参，轨迹由跑批环节传入。

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
- 每个样本创建一次真实执行请求，`conversation_id` 形如 `eval:<运行编号>:<样本编号>:<重复轮次>`，`agent` 取请求参数（默认 `chat`）。
- `POST /evaluation/runs` 支持 `epochs`（1-10，默认 1）：同一样本重复执行多次，各轮 `conversation_id` 不同、互不串扰，仍串行执行。
- 跑批会收集每次执行的事件流并压成轨迹摘要（`counts`/`tools`/`tokens`/`latencyMs`），随结果一起落库，`trace` 类型的 rubric 据此判定。
- 多轮执行（规格 S-003）：样本给了 `turns` 就按脚本逐轮发话（首轮永远是 `input`）；给了 `userProfile` 且没有 `turns` 时由模型扮演用户继续对话，模拟器返回结束标记或空串即结束，最多 8 轮。多轮的每一轮共用同一个会话编号，结束后把各轮轨迹合并（计数相加、工具取并集），`trace.turns` 是总轮数、`trace.transcript` 是逐轮助手输出。
- 多轮样本的评分对象是最后一轮的助手输出。
- 澄清轮（助手被需求门闸拦下）没有正文文本，产出在 `clarify` 事件里；这类轮次在 `trace.transcript` 中还原为「【需要澄清】问题；方向1；方向2」。
- 样本串行执行，单样本超时 120 秒，超时记 `verdict=timeout`、0 分；执行服务不可用时整轮 `blocked`；单个样本执行报错只把该样本记 `failed`。
- 并行跑批（规格 S-004）：`POST /evaluation/runs` 支持 `concurrency`（1–16，默认 1）、`budgetTokens`、`budgetSeconds`、`budgetSamples`、`pricePerMTok`。并发单位是「样本 × epoch」，结果落库始终在主线程按任务顺序进行；单个样本抛异常不影响其它样本。执行仍受 Worker 容量限制，单 Worker 时并发只是流水线、不提速。
- 预算护栏（规格 S-004）：token / 样本数 / 时限三种上限任一触发即不再领取新任务，未执行的样本记 `verdict=skipped`、`failure_kind=budget_exhausted`；`summary` 增 `concurrency`、`budgetTokens`、`budgetSeconds`、`budgetSamples`、`tokensUsed`、`budgetExhausted`、`skippedCount`、`estimatedCostUsd`。`passRate` 分母排除被跳过的样本，`passAtK`/`flakyRate` 不统计它们。token 计量只覆盖产生 usage 事件的执行，澄清门闸提前返回的路径记 0 token。
- 测评在后台线程执行，`POST /evaluation/runs` 立即返回运行编号与「测评已开始」提示，进度靠 `GET /evaluation/runs/{id}` 轮询。
- 运行 summary 含 `caseCount`、`passedCount`、`failedCount`、`passRate`；模型评分不可用的样本计入 `failedCount`，但不把整轮标成失败。
- summary 另含稳定性与成本字段（规格 S-002）：`resultCount`（结果条数 = 样本数 × epochs）、`epochs`、`passAtK`（每样本全轮都过的比例）、`flakyRate`（同一样本各轮判定不一致的比例）、`avgLatencyMs`、`avgTokens`、`failureKinds`（失败分类计数）。epochs=1 时 `passRate` 与改造前一致。
- summary 另含 `avgTurns`（平均对话轮数，规格 S-003）。
- 每条结果带 `epoch`、`failure_kind`、`exec_run_id`、`trace`（轨迹摘要）、`metrics`（语义维度明细，规格 S-005）。
- `failure_kind` 按证据派生（规格 S-007）：`timeout`、`judge_unavailable`、`tool_error`、rubric 显式 `failureKind`，以及按 rubric 类型派生的 `missing_keyword`（contains）、`output_mismatch`（equals）、`json_mismatch`（json_equals）、`semantic_mismatch`（model / semantic）、`trace_assertion_failed`（trace）、`assertion_failed`（multi）；输出为空记 `empty_output`，执行抛异常记 `execution_error`，兜底才是 `unknown`。判定顺序见规格 S-007 第 4.2 节。
- 运行记录带 `provenance`：测评集编号与版本、样本数、助手类型、epochs、模型名、git commit、仓库 `skills/*/SKILL.md` 的 sha256 前 12 位。
- 回放只挑选 `verdict` 为 `failed` 或 `timeout` 的样本，可用 `caseIds` 进一步过滤；每个命中样本新建一次执行并返回 `{caseId, runId, status}` 列表，没有失败样本时返回空列表；回放只重新执行，不重新评分，也不写回原测评运行。

### 关键实现

- `api/routers/evaluation.py:wait_for_run` / `collect_output` —— 轮询运行终态、拼接 text 事件为实际输出；`wait_for_background_runs` —— 等待后台测评线程结束

## 结果对比、导出与评测配置

### 入口

- `GET /evaluation/runs/compare?base=&target=` —— 两次运行对比
- `GET /evaluation/runs/matrix?runs=a,b,c` —— 多 run × 样本并排矩阵（规格 S-006）
- `GET /evaluation/runs/{eval_run_id}/export?format=json|csv` —— 导出样本结果
- `GET /evaluation/config`、`PUT /evaluation/config` —— 评测配置的读写
- `GET /evaluation/runs/{eval_run_id}/trace?caseId=&epoch=` —— 取某样本某轮的轨迹（摘要 + 事件时间线，最多 500 条事件）
- `POST /evaluation/gates/check` —— 按 `evaluation_config.gates` 检查一轮测评的汇总指标

### 行为

- 评测矩阵（规格 S-006）：`GET /evaluation/runs/matrix?runs=<逗号分隔的 2-8 个运行编号>`，顺序即列顺序、**第一个是基线**。返回 `runs[]`（每列的 `passRate` 与 `coverage`）、`rows[]`（行是各运行样本编号的并集）、`summary`（按运行编号索引）。
  - 每格 `cells[]` 含 `verdict`、`score`、`graded`、`epochs`、`passedEpochs`、`failureKind`、`metrics` 与相对基线的 `change`（`unchanged` / `improved` / `regressed` / `added` / `removed`）。
  - 多轮结果合并成格：全过记 `passed`，有对有错记 `flaky`，分数取各轮均分；`metrics` 按指标名合并。
  - 同题择优：`rows[].best` 指向得分最高的运行（同分取列顺序靠前）。
  - 可评覆盖率 `coverage` = 已判分样本数 / 该 run 的样本数，只有 `passed` / `failed` / `flaky` 计入；`timeout` / `invalid_rubric` / `scorer_unavailable` / `not_scored` / `skipped` 不计入。
  - 少于 2 个或多于 8 个运行返回 400；运行不存在返回 404 并指明编号。矩阵是只读视图，不改写任何运行与结果数据。
- 对比返回 `sameDataset`（两次运行是否同一测评集）、`summaryDiff`（`caseCount`、`passedCount`、`failedCount`、`passRate` 的 base/target/delta）与逐样本 `change`。
- 逐样本 `change` 取值：`improved`（由未通过变通过）、`regressed`（由通过变未通过）、`unchanged`、`added`（只在目标侧）、`removed`（只在基线侧）。
- 运行记录没有 summary 时按样本结果重新统计（`api/routers/evaluation.py:run_metrics`）；base 或 target 不存在返回 404，分别提示「基线测评运行不存在」「对比测评运行不存在」。
- 导出 JSON 返回 `{run, results}`；导出 CSV 带 UTF-8 BOM，表头为 `case_id,score,verdict,detail,actual_output,created_at,epoch,failure_kind,latency_ms,tokens`。
- 评测配置只有 `dimensions` 与 `gates` 两个自由结构字段，存放在单行（`config_id=1`）里，保存即覆盖；样本通过与否只看 rubric。
- `POST /evaluation/gates/check` 按 `gates` 判定（规格 S-002）：每项形如 `{"label","metric","op","value"}`，`metric` 取 `passRate`/`passAtK`/`flakyRate`/`avgLatencyMs`/`avgTokens`/`avgTurns`/`failedCount`/`caseCount`/`passedCount`/`resultCount`，`op` 取 `>=`/`<=`/`>`/`<`/`==`；**指标在 summary 里缺失时该条判未通过**（不当作 0）；指标不在白名单（`modules/evaluation/analysis.py:GATE_METRICS`）时同样判未通过；传入 `base` 时同时返回基线的实际值。页面「评测配置」的下拉选项与白名单一致。
- 发布质量门禁仍由发布治理模块负责，与本模块的评测自检门禁是两套东西。
- 评测自检门禁也能在命令行跑（规格 S-003）：`python -m python_backend.eval_gate --target <运行编号> [--base <基线运行编号>]`，门禁不通过时退出码为 1，判定逻辑与接口完全一致。

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
| `GET` | `/evaluation/semantic-metrics` | 列出内置语义指标模板 |
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
| `GET` | `/evaluation/runs/matrix` | 多 run × 样本并排矩阵 |
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
- 快照保存名称、类型、描述、样本条数与样本正文（含 sha256），可以据此还原当时的样本内容；模块仍没有「恢复到某次快照」的接口。
- 删除测评集不会清理历史测评运行与样本结果，`evaluation_run`、`evaluation_result` 会留下指向已删测评集的记录。
- 规则评分不消耗模型额度，只有 `rubric.type=model` 或 `rubric.type=semantic` 才调用模型；模型不可用记 `scorer_unavailable` 而不是伪造分数，也不会重试。
- 语义评分有噪声：同一份答案两次打分可能差 0.1 以内，比较时看均值差；语义评分跑在真实 Worker 上会消耗模型额度，建议配合 S-004 的预算护栏。
- 回放只重新执行失败样本，不重新评分，也不写回原运行结果；评测自检门禁走 `POST /evaluation/gates/check`，发布质量门禁仍由发布治理模块负责。
- 轨迹断言只能验证事件流里能看到的东西（澄清次数、工具名、工具错误数、步骤数、助手类型）；看不到语义是否正确的失败原因归 `unknown`，不做自动猜测。
- 基准作业一次只能跑一个；租约依赖页面轮询续租，页面关闭或崩溃后最多 30 秒作业即被取消；基准子进程最长时间 3600 秒，SSE 压测会创建真实对话并消耗模型额度。
- 基准输入只能来自 `data/benchmarks`，工具输出与日志留在本地 `data/evaluations/benchmarks/`；BIRD 评测只支持 SQLite，基准工具需先在 `eval/.venv` 安装，未安装时 `tools()` 对应项 `ready=false`。
