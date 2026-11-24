// 评测矩阵视图的纯函数：单元格文案、变化标签、运行勾选。

const VERDICT_LABELS = {
  passed: '通过',
  failed: '失败',
  flaky: '不稳定',
  timeout: '超时',
  skipped: '已跳过',
  not_scored: '未评分',
  invalid_rubric: '规则无效',
  scorer_unavailable: '评分器不可用',
}

const CHANGE_LABELS = {
  improved: '变好',
  regressed: '退化',
  unchanged: '持平',
  added: '新增',
  removed: '缺失',
}

export const MATRIX_RUN_LIMIT = 8

/** 单元格文案：判定 + 分数；没有判定就显示占位符。 */
export function matrixCellText(cell) {
  if (!cell || !cell.verdict) return '—'
  const label = VERDICT_LABELS[cell.verdict] || cell.verdict
  const score = Number(cell.score)
  if (!Number.isFinite(score)) return label
  return label + ' ' + score.toFixed(2)
}

/** 相对基线的变化标签。 */
export function matrixChangeLabel(change) {
  return CHANGE_LABELS[change] || ''
}

/** 勾选运行：已选则取消，否则追加；最多 8 个，基线（第一个）位置不动。 */
export function matrixRunSelection(current, runId) {
  const picked = Array.isArray(current) ? current.filter(Boolean) : []
  if (!runId) return picked
  if (picked.includes(runId)) return picked.filter((item) => item !== runId)
  if (picked.length >= MATRIX_RUN_LIMIT) return picked
  return [...picked, runId]
}