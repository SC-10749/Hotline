import { Activity, Archive, Bot, Cpu, Gauge, GitBranch, Layers3, ListChecks, Network, Settings2, ShieldCheck, Sparkles, Terminal, Wrench } from 'lucide-vue-next'

export const sections = [
  { label: '控制平面', items: [{ id: 'overview', label: '运行总览', icon: Activity }, { id: 'runs', label: '执行任务', icon: ListChecks }, { id: 'evaluations', label: '测评中心', icon: Gauge }, { id: 'agents', label: 'Agent 实例', icon: Bot }, { id: 'workspaces', label: '工作空间', icon: Layers3 }] },
  { label: '能力注册表', items: [{ id: 'tools', label: '工具与 MCP', icon: Wrench }, { id: 'skills', label: 'Skills', icon: Sparkles }, { id: 'models', label: '模型路由', icon: Network }] },
  { label: '运行治理', items: [{ id: 'machines', label: '机器与运行时', icon: Cpu }, { id: 'approvals', label: '待审批', icon: ShieldCheck }, { id: 'artifacts', label: '产物与存储', icon: Archive }, { id: 'observability', label: '追踪与日志', icon: Terminal }, { id: 'releases', label: '发布治理', icon: GitBranch }, { id: 'settings', label: 'Harness 设置', icon: Settings2 }] },
]
