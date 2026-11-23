# 发布治理（release）

> 模块路径：`python_backend/api/routers/release.py`（HTTP 路由与门禁判定）、`python_backend/infrastructure/governance_store.py`（门禁 / 记录 / 观测 / 配置存储）、`python_backend/modules/skills/catalog.py`（灰度绑定、指标与回滚动作）
> 前端对应：无独立前端模块目录（`frontend/src/modules/release/` 不存在）；界面在 `frontend/src/HarnessApp.vue` 的「运行治理 / 发布治理」分区，接口封装在 `frontend/src/api.js`
> 状态：现状说明（以代码为准，冲突时以代码为准并修正本文档）

## 质量门禁与阈值配置

### 入口

- `POST /release/gate` —— `python_backend/api/routers/release.py:evaluate_gate`，跑一次门禁并落库。
- `GET /release/gate-thresholds` / `PUT /release/gate-thresholds` —— `release.py:get_gate_thresholds` / `release.py:save_gate_thresholds`，读写三项门禁阈值。
- `GET /release/config` / `PUT /release/config` —— `release.py:get_release_config` / `release.py:save_release_config`，读写三项发布策略。
- `release.py:gate_result` —— 门禁判定的唯一实现。

### 行为

- 门禁三项指标：`e2ePassRate` ≥ 阈值、`ragFaithfulness` ≥ 阈值、`highRiskErrors` ≤ 阈值；三项全过才 `passed=true`。
- 默认阈值（`infrastructure/governance_store.py:DEFAULT_RELEASE_CONFIG`）：`e2ePassRate=0.90`、`ragFaithfulness=0.85`、`highRiskErrors=0`。
- 阈值可改：`PUT /release/gate-thresholds` 保存后，下一次门禁判定立即用新阈值（`test_gate_thresholds_are_configurable`）。
- `evalRunId` 可选。传入时用 `evaluation_run_exists`（装配为 `EvaluationStore.get_run`）校验评测记录存在性，不存在则检查项 `evalRunId=false`，门禁不通过。
- 门禁结果写 `release_gate` 行，编号形如 `gate-{12位hex}`，保存 `checks`、`thresholds`、`eval_run_id`；`GET /release/gates` 可列出（limit 1~200）。
- 发布策略三项：`rolloutErrorThreshold`（默认 0.05）、`rolloutMinSamples`（默认 30）、`autoRollback`（默认 true）。
- 门禁阈值与发布策略共用 `release_config` 单行（`config_id=1`）的 JSON payload，保存时按「非 None 字段」合并进当前值；两个 GET 视图各自只返回自己那部分字段（`/release/config` 额外带 `updated_at`）。
- `gate_store` 未接入时，`PUT /release/config` 与 `PUT /release/gate-thresholds` 返回 HTTP 503「发布治理存储未接入」。

### 关键实现

- `release.py:gate_result`（阈值兜底、指标比较、`evalRunId` 存在性校验）与 `infrastructure/governance_store.py:GovernanceStore.get_release_config` / `save_release_config`（单行配置读写）。

## 晋级（promote）与灰度比例推进

### 入口

- `POST /release/promote` —— `release.py:promote`，带门禁证据进入灰度。
- `POST /release/rollouts/advance` —— `release.py:advance_rollout`，只推进灰度比例。
- `python_backend/modules/skills/catalog.py:Catalog.call` 的 `promote` 分支 —— 真正写灰度行与绑定。

### 行为

- `promote` 必须带 `gate` 且门禁通过，否则 HTTP 412「发布前质量门禁未通过」；**校验失败时不写任何发布记录**（`test_promote_without_passing_gate_is_rejected`）。
- `gate` 可传 `gate_id`（此时以存储里的门禁记录为准）或直接传三项指标；两种写法都必须通过判定。
- 门禁带 `evalRunId` 时，晋级绑定的是一条**存在且已通过**的评测记录：晋级记录同时写入 `gate_id` 与 `eval_run_id`（`test_promote_writes_record_with_gate_evidence`）。
- `promote` 落到目录动作：写 `rollouts` 行（`project`、`name`、`candidate_version`、`previous_version`、`percentage`、`active=1`）并把 `bindings` 指到候选版本；`percentage` 由目录层夹取到 0~100。
- 同一版本重复推进时保留原 `previous_version` 作为回滚目标，避免回滚退化为空操作。
- `advance` 的比例**单调不减**：目标比例低于当前比例返回 HTTP 400「灰度比例不能低于当前比例 X%」（`test_advance_requires_monotonic_percentage`）。
- `advance` 未指定 `version` 时取当前灰度的 `candidate_version`；没有可推进版本返回 HTTP 400「没有可推进的灰度版本」。
- 灰度流量分配在目录动作 `runtime` 内：按 `requestId` 的 sha256 取桶 `% 100`，桶值 ≥ `percentage` 时该请求回落到 `previous_version`。

### 关键实现

- `release.py:promote` / `advance_rollout`（门禁把关、比例单调校验、晋级记录）与 `skills/catalog.py:Catalog.call`（`promote` 写 `rollouts`/`bindings`，`runtime` 做流量分桶）。

## 指标观测与自动回滚

### 入口

- `POST /release/rollouts/observe` —— `release.py:observe` → `release.py:observe_rollout`，手动观察一次灰度。
- `POST /release/metrics` —— `release.py:record_metric`，上报一条线上指标。
- `release.py:observe_active_rollouts` —— 后台定时任务，对所有 `active` 灰度各观察一次。
- `release.py:run_release_observation_once` —— 手动跑一轮观察（测试与后台线程共用）。

### 行为

- 观测对象按 `project` + `name`（可选 `version`）匹配 `rollouts` 行；找不到返回 HTTP 404「灰度发布不存在：项目/技能」。
- 错误率 = 该灰度 `metric='error_rate'` 的全部指标行 `value` 的平均值；样本数 = 这些行的条数。
- 样本数 < `rolloutMinSamples` → 不回滚，detail 含「样本不足」（`test_observation_with_not_enough_samples_does_not_rollback`）。
- 错误率 ≥ `rolloutErrorThreshold` 且 `autoRollback=true` → 调用目录 `rollback`，并留一条 `auto_rollback` 记录（`test_observation_over_threshold_triggers_auto_rollback_with_details`）。
- `autoRollback=false` → 不回滚，detail 含「未开启自动回滚」，但观测仍入库（`test_observation_without_auto_rollback_records_but_keeps_rollout`）。
- 每次观测写 `release_observation` 行：版本、比例、错误率、样本数、阈值、是否自动回滚、说明文本。
- 定时观察：路由创建时登记观察回调，间隔取环境变量 `HARNESS_ROLLOUT_OBSERVE_INTERVAL`（默认 60 秒，下限 15 秒）；单个灰度失败只记日志，不影响其它灰度；应用退出时由 `fastapi_app.py` 的 lifespan 调用 `stop_release_observation` 收线程。
- `POST /release/metrics` 走目录 `metric` 动作；若返回 `autoRolledBack=true`，路由补写一条 `auto_rollback` 记录，并附当时的错误率、样本数与阈值快照（`test_auto_rollback_record_keeps_error_snapshot`）。

### 关键实现

- `release.py:error_stats` / `observe_rollout`（错误率统计、阈值判定、自动回滚、观测落库）与 `release.py:_observation_loop`（后台观察线程）；`skills/catalog.py:Catalog.call` 的 `metric` 分支另有目录侧自动回滚判定。

## 发布记录与回滚留痕

### 入口

- `GET /release/records` —— `release.py:list_records`，发布/推进/回滚/自动回滚的审计流水。
- `POST /release/rollback` —— `release.py:rollback`，手动回滚到上一稳定版本。
- `GET /release/observations` —— `release.py:list_observations`，灰度观测流水（可按 `project` 过滤）。
- `GET /release/gates` —— `release.py:list_gates`，门禁记录。

### 行为

- 记录动作取值：`promote`（发布）、`advance`（推进灰度）、`rollback`（手动回滚）、`auto_rollback`（自动回滚）。
- 记录字段：`project`、`name`、`version`、`action`、`percentage`、`gate_id`、`eval_run_id`、`detail`、`actor`，自动回滚另带 `error_rate`、`sample_count`、`threshold`。
- `actor` 缺省 `harness-operator`，请求体传 `operator` 覆盖。
- `detail` 约定：发布 = 门禁 `checks` 的 JSON；推进 = 「灰度比例从 X% 推进到 Y%」；手动回滚 = 「回滚到上一稳定版本」；自动回滚 = 含错误率、阈值与样本数的说明。
- `GET /release/records` 会按 `gate_id` 关联门禁记录，把 `checks`、`thresholds`、`eval_run_id` 补到每条记录上。
- 记录按创建时间倒序返回，`limit` 取值 1~200。
- 手动回滚：目录动作要求灰度行存在 `previous_version`，否则抛「没有可回滚版本」→ HTTP 400；回滚后 `bindings` 指回旧版本、`rollouts.active=0`。

### 关键实现

- `infrastructure/governance_store.py:GovernanceStore.save_record` / `list_records` / `save_observation` / `list_observations`，以及 `skills/catalog.py:Catalog.call` 的 `rollback` 分支（回滚目标版本与灰度状态）。

## 发布总览与控制台视图

### 入口

- `GET /release/summary` —— `release.py:release_summary`，一次返回灰度、自进化运行与指标。
- `GET /release/rollouts` / `GET /release/runs` / `GET /release/metrics` —— `release.py:list_rollouts` / `list_release_runs` / `list_metrics`。
- `frontend/src/HarnessApp.vue` 的 `releases` 分区 —— 「运行治理 / 发布治理」界面。

### 行为

- `summary` 的 `project` 缺省取应用配置 `DODO_SKILL_PROJECT`；`metrics` 列表在 `GET /release/metrics` 上按 `limit` 截断（1~500，默认 200）。
- 控制台分区包含：KPI（活动灰度数、最高灰度比例、发布记录数、线上指标数）、当前灰度表格、推进灰度表单、灰度观察记录、发布记录。
- 灰度表格每行可「推进灰度」「立即观察」「回滚」；表单里的「进入灰度」按钮在门禁结果不是通过态时禁用。
- 前端接口封装在 `frontend/src/api.js`：`getReleaseSummary`、`promoteRelease`、`evaluateReleaseGate`、`getReleaseGates`、`getReleaseRecords`、`advanceRollout`、`getReleaseConfig`、`saveReleaseConfig`、`getReleaseGateThresholds`、`saveReleaseGateThresholds`、`rollbackRelease`、`getReleaseObservations`、`observeReleaseRollout`。

### 关键实现

- `release.py:release_summary` / `list_rollouts` / `list_metrics`，以及 `frontend/src/HarnessApp.vue` 的 `releases` 分区模板与 `refreshReleaseData`、`checkReleaseGate`、`promoteCurrentRelease`、`advanceRolloutRow`、`observeRollout`、`rollbackReleaseByRow` 等处理函数。

## 数据与存储

- 治理库（SQLite）：`settings.data_dir / 'harness-governance.db'`。表：`release_gate`、`release_record`、`release_observation`、`release_config`（`config_id=1` 单行）。
- 技能目录库（SQLite）：`settings.skill_catalog_db`（环境变量 `DODO_SKILL_CATALOG_DB`）。表：`rollouts`、`metrics`、`bindings`、`versions`、`evolution_runs`。
- 评测库：`evaluation.db`，门禁的 `evalRunId` 通过 `EvaluationStore.get_run` 校验存在性。
- 相关配置项名称：`HARNESS_ROLLOUT_OBSERVE_INTERVAL`（后台观察间隔）、`SKILL_ROLLOUT_ERROR_THRESHOLD`、`SKILL_ROLLOUT_MIN_SAMPLES`（目录侧自动回滚判定）、`DODO_SKILL_PROJECT`（默认项目）。

## 接口清单

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/release/summary` | 灰度、自进化运行与指标总览 |
| GET | `/release/rollouts` | 当前灰度列表 |
| GET | `/release/runs` | 自进化运行列表 |
| GET | `/release/metrics` | 线上指标列表（limit 1~500） |
| POST | `/release/metrics` | 上报一条指标，回滚时补写记录 |
| GET | `/release/gates` | 门禁记录列表（limit 1~200） |
| GET | `/release/records` | 发布/推进/回滚/自动回滚记录 |
| GET | `/release/observations` | 灰度观测记录（可按 project 过滤） |
| GET | `/release/config` | 读发布策略（错误率阈值、最小样本、自动回滚开关） |
| PUT | `/release/config` | 写发布策略 |
| GET | `/release/gate-thresholds` | 读门禁阈值 |
| PUT | `/release/gate-thresholds` | 写门禁阈值 |
| POST | `/release/gate` | 跑一次质量门禁并落库 |
| POST | `/release/promote` | 凭门禁证据进入灰度 |
| POST | `/release/rollouts/advance` | 只推进灰度比例（单调不减） |
| POST | `/release/rollouts/observe` | 手动观察一次灰度，必要时自动回滚 |
| POST | `/release/rollback` | 手动回滚到上一稳定版本 |

## 边界与已知限制

- `promote` 的门禁可以内联传入三项指标，并不强制引用已存门禁记录；只有走 `gate_id` 的晋级记录才带完整门禁证据链。
- 门禁未提供 `evalRunId` 时，只按三项指标判定，不校验评测记录；`evalRunId` 存在但记录不存在时门禁不通过。
- 目录侧自动回滚用环境变量 `SKILL_ROLLOUT_ERROR_THRESHOLD` / `SKILL_ROLLOUT_MIN_SAMPLES`（默认 0.05 / 30），与 `/release/config` 的发布策略是两套独立阈值，互不影响。
- `POST /release/promote` 传入的 `rolloutErrorThreshold`、`rolloutMinSamples`、`autoRollback` 在目录 `promote` 动作里并未被使用。
- 比例单调性只在 `advance` 上校验；`promote` 允许把比例改回更小值（目录层只做 0~100 夹取）。
- 后台观察是进程内单线程（模块级登记），多进程部署时每个进程各观察一次。
- 错误率只统计 `error_rate` 指标，其它指标不参与回滚判定。
- 门禁阈值与发布策略存在同一行配置记录里，两个 GET 视图各取自己那部分字段。
