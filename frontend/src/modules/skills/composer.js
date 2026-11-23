// 技能助手（TDD）阶段，底部对话框整块由技能接手：文案集中在这里，模板只管渲染。

const SKILL_COPY = {
  bar: '技能助手模式：底部这块区域已由技能接手，在这里回复即可',
  placeholder: '在这里回复技能助手…',
  hintLabel: '技能助手模式',
  hintKey: 'Enter',
}

/** 非技能模式返回 null，底部对话框保持普通聊天形态。 */
export function skillComposerCopy(mode) {
  return mode === 'skills' ? SKILL_COPY : null
}
