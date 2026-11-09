const stageLabels = {
  understanding: '正在理解问题',
  query_rewrite: '正在改写问题',
  prompt_rewrite: '正在改写问题',
  rewrite: '正在改写问题',
  retrieval_route: '正在选择检索方式',
  retrieval_request: '正在检索所选文档',
  retrieval: '正在查找相关内容',
  text2sql: '正在整理文档查询',
  web_search: '正在搜索网络资料',
  research: '正在准备检索任务',
  ppt_plan: '正在整理演示内容',
  llm: '正在组织回答',
  clarify: '需要确认需求方向',
}

export function finishProgress(message, status = 'completed', now = Date.now()) {
  for (const entry of message.timeline) {
    if (entry.endedAt != null) continue
    entry.status = status
    entry.endedAt = now
  }
}

export function appendProgressEvent(message, event, now = Date.now()) {
  const { type, content } = event
  if (['step', 'progress', 'thinking'].includes(type)) {
    const stage = event.stage || 'understanding'
    const status = event.status || event.details?.status || (Number.isFinite(event.durationMs) ? 'completed' : 'running')
    const legacyStartup = type === 'thinking' && /^正在启动 .+ 智能体/.test(String(content || ''))
    const label = legacyStartup ? stageLabels.understanding : String(content || stageLabels[stage] || '正在处理')
    let entry = message.timeline.filter(item => item.type === 'step' && item.stage === stage
      && (status !== 'running' || item.endedAt == null)).at(-1)
    if (!entry) {
      for (const previous of message.timeline) {
        if (previous.type !== 'tool' && previous.endedAt == null) {
          previous.status = 'completed'
          previous.endedAt = now
        }
      }
      entry = { type: 'step', stage, t0: now }
      message.timeline.push(entry)
    }
    Object.assign(entry, { content: label, status })
    if (Array.isArray(event.details?.documents)) {
      entry.sources = event.details.documents.filter(item => typeof item === 'string').slice(0, 6).map(item => item.slice(0, 180))
    }
    if (status !== 'running') {
      entry.endedAt = now
      if (Number.isFinite(event.durationMs)) entry.t0 = now - Math.max(0, event.durationMs)
    }
    return true
  }
  if (!['tool_start', 'tool_end'].includes(type)) return false
  const toolName = event.toolName || '工具'
  const toolCallId = event.toolCallId || ''
  const args = event.arguments
  const skill = toolName === 'read_skill' && typeof args?.skill_id === 'string' ? args.skill_id : ''
  let entry = message.timeline.find(item => item.type === 'tool' && item.toolCallId === toolCallId
    && (toolCallId || item.toolName === toolName))
  if (!entry) {
    if (type === 'tool_start') {
      for (const previous of message.timeline) {
        if (previous.type !== 'tool' && previous.endedAt == null) {
          previous.status = 'completed'
          previous.endedAt = now
        }
      }
    }
    entry = { type: 'tool', toolName, toolCallId, t0: now,
      content: skill ? `正在读取技能「${skill}」` : `正在调用工具 ${toolName}` }
    message.timeline.push(entry)
  }
  if (type === 'tool_start') {
    if (entry.endedAt == null) entry.status = 'running'
  } else {
    entry.status = ['failed', 'cancelled'].includes(event.status) ? event.status : 'completed'
    entry.endedAt = now
    if (Number.isFinite(event.durationMs)) entry.t0 = now - Math.max(0, event.durationMs)
  }
  return true
}

export function progressLabel(message) {
  const running = message.timeline.filter(entry => entry.endedAt == null && entry.status === 'running').at(-1)
  if (running && !(running.stage === 'llm' && (message.content || message.pendingText))) return running.content
  return message.content || message.pendingText ? '正在生成回答' : '正在继续处理'
}

export function progressEntryLabel(entry) {
  const label = entry.content || entry.toolName || ''
  return entry.endedAt == null ? label : label.replace(/^正在/, '')
}
