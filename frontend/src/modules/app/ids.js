// 会话与任务的本地 id：时间戳 + 随机串，和后端 id 无关。
export function makeId() {
  return `chat_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`
}
