// 需求分析助手把候选答案写进正文；这里把它们抽出来，供输入框上方的选择面板使用。

// 问题行：以问号收尾；可有「1.」序号，末尾允许带「（可多选）」这类补充说明。
const QUESTION_LINE = /^(?:\s*\d+[.、)）]\s*)?(.+[？?])(\s*[（(][^）)]*[）)])?\s*$/
// 候选行：项目符号，或模型自己写的 A. / B、/ C) 编号。
const BULLET_LINE = /^\s*[-*+•·]\s+(.+?)\s*$/
const LETTER_LINE = /^\s*([A-Z])[.、)）]\s*(.+?)\s*$/
const MAX_OPTION_LENGTH = 60
const LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('')

/**
 * 把「问题 + 其下候选答案」拆开：返回去掉候选答案的正文，以及按问题分组的候选答案。
 * 只有成组出现（至少两个候选）的才会被抽走，普通列表原样保留。
 */
export function extractQuestionOptions(text) {
  const lines = String(text || '').split('\n')
  const groups = []
  const removed = new Set()
  let current = null
  lines.forEach((line, index) => {
    const lettered = line.match(LETTER_LINE)
    const bullet = line.match(BULLET_LINE)
    if (lettered || bullet) {
      // 候选行只有紧跟在问题下面才算候选，否则就是普通列表。
      if (current) {
        const raw = (lettered ? lettered[2] : bullet[1]).trim()
        // 模型常写成「- A. 客户提了需求」，字母前缀要从正文里剥掉。
        const nested = lettered ? null : raw.match(LETTER_LINE)
        current.options.push({
          label: (nested ? nested[2] : raw).trim(),
          letter: lettered ? lettered[1] : (nested ? nested[1] : undefined),
          index,
        })
      } else {
        current = null
      }
      return
    }
    const question = line.match(QUESTION_LINE)
    if (question) {
      current = { question: question[1].trim(), options: [] }
      groups.push(current)
      return
    }
    if (line.trim()) current = null
  })
  const usable = groups.filter(group => group.options.length >= 2
    && group.options.every(item => item.label && item.label.length <= MAX_OPTION_LENGTH))
  usable.forEach(group => group.options.forEach(item => removed.add(item.index)))
  return {
    text: lines.filter((_, index) => !removed.has(index)).join('\n').replace(/\n{3,}/g, '\n\n').trim(),
    groups: usable.map(group => ({
      question: group.question,
      options: group.options.map(item => ({ label: item.label, letter: item.letter })),
    })),
  }
}

/** 每个问题的候选从 A 开始编号（模型自己写了字母就用它的），并给每个选项一个稳定 key。 */
export function buildOptionPanel(groups) {
  return (groups || []).map((group, groupIndex) => ({
    question: group.question,
    options: (group.options || []).map((option, optionIndex) => ({
      key: `${groupIndex}:${optionIndex}`,
      letter: option.letter || LETTERS[optionIndex] || String(optionIndex + 1),
      label: option.label,
    })),
  }))
}

/** 把选中的候选拼成给技能助手的追问内容。 */
export function composeOptionAnswer(panel, selectedKeys) {
  const lines = []
  ;(panel || []).forEach(group => {
    group.options
      .filter(option => (selectedKeys || []).includes(option.key))
      .forEach(option => lines.push(`${group.question}——${option.letter}. ${option.label}`))
  })
  return lines.join('\n')
}
