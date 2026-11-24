// 评测可读性：运行标签、相对时间、测评集卡片、失败分类标签。

const AGENT_LABELS = {
  chat: '对话助手',
  skills: '技能助手',
  requirement: '需求助手',
}

const RUN_STATUS_LABELS = {
  running: '运行中',
  queued: '排队中',
  completed: '已完成',
  failed: '未通过',
  blocked: '已阻塞',
}

export const FAILURE_LABELS = {
  wrong_intent: '意图判断错误',
  missing_capability: '能力缺失',
  tool_error: '工具报错',
  timeout: '超时',
  judge_unavailable: '评审模型不可用',
  policy_violation: '策略违规',
  budget_exhausted: '预算用尽',
  missing_keyword: '缺少关键词',
  output_mismatch: '输出不一致',
  json_mismatch: 'JSON 不一致',
  semantic_mismatch: '语义不达标',
  trace_assertion_failed: '轨迹断言不满足',
  assertion_failed: '断言不满足',
  empty_output: '无输出',
  execution_error: '执行异常',
  invalid_rubric: '规则无效',
  not_scored: '未评分',
  unknown: '未知原因',
}

/** 失败分类的中文标签。 */
export function failureKindLabel(kind) {
  return FAILURE_LABELS[kind] || kind || ''
}

/** 时间戳既可能是 SQLite 的 'YYYY-MM-DD HH:MM:SS'，也可能是 ISO 串。 */
export function parseTimestamp(value) {
  if (!value) return null
  const text = String(value).trim()
  const normalized = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(text)
    ? text.replace(' ', 'T') + 'Z'
    : text
  const stamp = Date.parse(normalized)
  return Number.isFinite(stamp) ? stamp : null
}

/** 相对时间：刚刚 / N 分钟前 / N 小时前 / N 天前。 */
export function relativeTime(value, now = Date.now()) {
  const stamp = parseTimestamp(value)
  if (stamp === null) return '—'
  const seconds = Math.max(0, Math.round((now - stamp) / 1000))
  if (seconds < 60) return '刚刚'
  if (seconds < 3600) return `${Math.round(seconds / 60)} 分钟前`
  if (seconds < 86400) return `${Math.round(seconds / 3600)} 小时前`
  return `${Math.round(seconds / 86400)} 天前`
}

function percentText(value) {
  const num = Number(value)
  if (value === null || value === undefined || !Number.isFinite(num)) return '—'
  return `${(num <= 1 ? num * 100 : num).toFixed(1)}%`
}

/** 运行下拉与矩阵勾选项的标签：助手 · 测评集 · 通过率 · 轮数 · 时间。 */
export function runOptionLabel(run, datasetName = '', now = Date.now()) {
  if (!run) return ''
  const parts = [AGENT_LABELS[run.agent] || run.agent || '未知助手']
  parts.push(datasetName || run.eval_run_id || '')
  const rate = run.summary?.passRate
  if (rate === null || rate === undefined) parts.push(RUN_STATUS_LABELS[run.status] || run.status || '未知状态')
  else parts.push(`通过率 ${percentText(rate)}`)
  const epochs = Number(run.epochs)
  if (Number.isFinite(epochs) && epochs > 1) parts.push(`${epochs} 轮`)
  const time = relativeTime(run.created_at, now)
  if (time !== '—') parts.push(time)
  return parts.filter(Boolean).join(' · ')
}

/** 测评集卡片：真实通过率、状态与最近运行时间。 */
export function datasetCardView(dataset, lastRun, now = Date.now()) {
  if (!lastRun) {
    return { pass: '—', state: '未运行', updated: relativeTime(dataset?.updated_at, now) }
  }
  const rate = lastRun.passRate
  const pass = rate === null || rate === undefined ? '—' : percentText(rate)
  const status = lastRun.status
  let state = '未运行'
  if (status === 'running' || status === 'queued') state = '运行中'
  else if (status === 'completed') state = rate === null || rate === undefined ? '已完成' : (Number(rate) < 1 ? '需关注' : '已完成')
  else if (status === 'failed') state = '未通过'
  else if (status === 'blocked') state = '已阻塞'
  return { pass, state, updated: relativeTime(lastRun.createdAt, now) }
}
