// 推荐项交接：后端给结构化项时切到技能助手并带上技能名，普通字符串按原样发送。

/** 推荐项显示文案：结构化项用 label，普通字符串原样显示。 */
export function recommendationLabel(item) {
  if (item && typeof item === 'object') return String(item.label || '')
  return String(item || '')
}

/** 结构化推荐项 → 技能助手交接信息；普通推荐项返回 null。 */
export function handoffFor(item) {
  if (!item || typeof item !== 'object' || !item.skill) return null
  return { mode: 'skills', skill: item.skill, query: String(item.label || '') }
}
