// SSE 分帧：把字节流切成一条条 data 载荷。
//
// 三处流式读取（对话、运行事件、并行子任务）都要解析同一套协议，
// 这里抽成纯函数，便于单测，也避免各处各写一遍分帧逻辑。

export function parseSseFrames() {
  let buffer = ''
  const state = {
    done: false,
    // 送入一段文本，返回本次能确定的完整 data 载荷。
    push(chunk) {
      buffer += String(chunk ?? '').replace(/\r\n/g, '\n')
      const frames = []
      let boundary = buffer.indexOf('\n\n')
      while (boundary >= 0) {
        const frame = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        const data = frame
          .split('\n')
          .filter(line => line.startsWith('data:'))
          .map(line => line.slice(5).trimStart())
          .join('\n')
        if (data && data !== '[DONE]') {
          frames.push(data)
        } else if (data === '[DONE]') {
          state.done = true
        }
        boundary = buffer.indexOf('\n\n')
      }
      return frames
    },
  }
  return state
}

// 读取一个 SSE 响应流；每收到一条载荷就调 onMessage。
export async function readSseStream(response, onMessage) {
  const frames = parseSseFrames()
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    for (const payload of frames.push(decoder.decode(value, { stream: true }))) {
      await onMessage(payload)
    }
    if (frames.done) break
  }
}
