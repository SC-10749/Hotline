import { FileText, FlaskConical, FolderOpen, MessageCircle, Puzzle, Search, Sparkles } from 'lucide-vue-next'

// 助手模式：顶部模式条与欢迎页提示共用这一份定义。
export const modes = [
  { id: 'chat', label: '对话助手', icon: MessageCircle, description: '日常问答与创作' },
  { id: 'file', label: '文件问答', icon: FolderOpen, description: '基于上传内容提问' },
  { id: 'ppt', label: 'PPT 生成', icon: FileText, description: '整理主题并生成演示文稿' },
  { id: 'deep', label: '深度研究', icon: FlaskConical, description: '结合检索进行深入分析' },
  { id: 'skills', label: '技能助手', icon: Puzzle, description: '调用已安装的技能处理任务' },
]

// 欢迎页的快捷提问。
export const quickPrompts = [
  { icon: Sparkles, text: '介绍一下你自己' },
  { icon: Search, text: '帮我分析一个问题' },
  { icon: FileText, text: '帮我整理一份汇报大纲' },
]
