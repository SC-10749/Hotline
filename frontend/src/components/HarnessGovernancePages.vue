<script setup>
import { computed, ref, watch } from 'vue'
import { Activity, ArrowDownToLine, ArrowRight, Check, ChevronRight, CircleAlert, Clock3, Download, Filter, Plus, Search, ShieldCheck, Terminal, X } from 'lucide-vue-next'

const props = defineProps({ page: { type: String, required: true } })
const emit = defineEmits(['notify'])

const tabs = [
  { id: 'machines', label: 'machines', title: '机器与运行时', columns: ['节点', '类型', '系统', '状态', '槽位', '心跳'], metrics: [['7/8', '在线节点', '心跳 <10s'], ['18', '空闲槽位', '可接受新运行'], ['37%', 'CPU', '集群平均'], ['1', '故障', '4 个版本漂移']], records: [['runner-01', '远程机器', 'Ubuntu 22.04 · harness 2.4.1', '在线', '2/4', '3s'], ['runner-02', 'Docker 容器', 'Debian 12 · harness 2.4.1', '忙碌', '1/2', '1s'], ['gpu-01', 'GPU Worker', 'Ubuntu 22.04 · CUDA 12.4', '在线', '1/2', '2s'], ['k8s-pod-a', 'Kubernetes Pod', 'Alpine 3.19 · harness 2.4.0', '空闲', '8/8', '5s'], ['ci-runner-7', 'CI Runner', 'Ubuntu 20.04 · harness 2.3.8', '降级', '4/4', '41s'], ['edge-05', '远程机器', 'macOS 14.5 · harness 2.4.1', '排空中', '1/2', '2s'], ['local-dev', '本地机器', 'macOS 14.5 · harness 2.4.1', '在线', '1/1', '1s'], ['fc-worker-2', 'Serverless Worker', 'Firecracker · harness 2.3.6', '离线', '1/1', '8m']], tabs: ['资源目录', '运行关联', '变更记录'], footnote: '机器与运行时', insight: '隔离管允许做什么，这里管在哪做。调度单位是资源池；节点心跳和版本必须始终可见。', detail: ['类型', '系统', '槽位', '资源池', '运行时', '最近心跳'], values: ['远程机器', 'Ubuntu 22.04 · x86_64', '2 / 4 空闲', 'cpu-pool', 'harness 2.4.1', '3 秒前']},
  { id: 'approvals', label: 'approvals', title: '待审批', columns: ['请求', '运行', 'Agent', '工具', '风险', '等待', '状态', '策略'], metrics: [['5', '待审批', '按等待时长排序'], ['21m', '平均等待', 'SLA 30 分钟'], ['1', '已超时', '超时即拒绝'], ['4', '高风险', '需要会签']], records: [['apr_8f31', 'run_2b7d', 'release-bot', 'shell.exec', '4', '21m', '待审批', 'POL-TOOL-014'], ['apr_8e77', 'run_2b55', 'data-analyst', 'postgres.query', '3', '18m', '待审批', 'POL-DATA-003'], ['apr_8e02', 'run_2b41', 'frontend-dev', 'fs.write', '2', '9m', '待审批', 'POL-FS-002'], ['apr_8dd4', 'run_2b38', 'support-agent', 'http.fetch', '3', '26m', '待审批', 'POL-NET-001'], ['apr_8d19', 'run_2b21', 'ops-runner', 'k8s.apply', '4', '29m', '待审批', 'POL-INFRA-007'], ['apr_8c55', 'run_2b02', 'release-bot', 'npm.publish', '3', '22m', '已批准', 'POL-SUPPLY-002'], ['apr_8baa', 'run_29f7', 'data-analyst', 'fs.delete', '4', '37m', '已拒绝', 'POL-FS-005'], ['apr_8b21', 'run_29c4', 'support-agent', 'crm.update', '2', '31m', '已超时', 'POL-EXT-001'], ['apr_8a90', 'run_2990', 'ops-runner', 'shell.exec', '3', '8m', '已取消', 'POL-INFRA-002']], tabs: ['队列', '详情', '操作', '批量', '策略命中', '记录', '通知'], footnote: '待审批请求', insight: '队列按等待时长排序。批量批准仅适用于低风险请求；超时请求进入拒绝终态，运行改用其他方案。', detail: ['风险等级', 'Agent', '工作空间', '运行', '模型', '命中策略'], values: ['4 · 高风险', 'release-bot', 'ws-payments', 'run_2b7d', 'gpt-5-codex', 'POL-TOOL-014']},
  { id: 'governance', label: 'governance', title: '治理策略', columns: ['策略', '作用域', '优先级', '动作', '版本', '命中', '状态'], metrics: [['12', '策略总数', '覆盖工具、文件与网络'], ['11', '生效', '默认拒绝兜底'], ['35,439', '命中 / 24h', '所有已评估请求'], ['1', '策略冲突', '发布前需处理']], records: [['破坏性 git 操作 · POL-TOOL-014', 'ws-payments', 'P1', '需要审批', 'v7', '128', '生效'], ['出网白名单 · POL-NET-001', '全局', 'P1', '拒绝', 'v12', '2,407', '生效'], ['递归删除 · POL-FS-005', '全局', 'P1', '需要审批', 'v9', '64', '生效'], ['生产库写入 · POL-DATA-003', '全局', 'P2', '需要审批', 'v4', '41', '生效'], ['输出脱敏 · POL-OUT-002', '全局', 'P2', '脱敏后继续', 'v6', '1,820', '生效'], ['提示注入拦截 · POL-IN-001', '全局', 'P1', '拒绝', 'v3', '37', '生效'], ['模型使用限制 · POL-MODEL-002', 'high-security', 'P2', '降级执行', 'v2', '12', '生效'], ['运行时资源上限 · POL-RES-001', '全局', 'P3', '记录但继续', 'v5', '9,302', '生效'], ['工作区写入范围 · POL-FS-009', 'ws-web', 'P2', '允许', 'v1', '15,420', '生效'], ['生产配置写入 · POL-FS-002', '全局', 'P1', '需要审批', 'v9', '88', '生效'], ['工作区 shell 放行 · POL-TOOL-009', '全局', 'P1', '允许', 'v2', '6,120', '生效'], ['公开发布 · POL-SUP-002', '全局', 'P1', '需要审批', 'v5', '0', '停用']], tabs: ['目录', '类型矩阵', '匹配条件', '编辑器', '版本', '测试', '冲突', '灰度审核', '命中统计'], footnote: '策略目录', insight: '优先级决定求值顺序，不决定谁赢。第一个命中的策略就是最终决策；没有命中时默认拒绝。', detail: ['作用域', '优先级', '状态', '匹配条件', '动作', '最近发布'], values: ['ws-payments', 'P1 · 第 1 顺位求值', '生效 · v7', 'tool = shell.exec；args 含 --force', '需要审批', '2 小时前 · 灰度 10% → 100%']},
  { id: 'verification', label: 'eval', title: '验证与评估', columns: ['项目', 'Agent', '模型', '数据集', '版本', '得分', '最近'], metrics: [['87.4%', '总体通过率', '180 个样本'], ['94%', '工具调用', '正确性'], ['100%', '安全阻断', '策略覆盖'], ['74%', '注入抵抗', '需要改进']], records: [['发布流程回归', 'release-bot', 'gpt-5-codex', 'golden-release-v3', 'r42', '87.4%', '2 小时前'], ['数据分析问答', 'data-analyst', 'claude-sonnet-4.5', 'analytics-qa-v7', 'r18', '91.2%', '昨天'], ['客服工单处理', 'support-agent', 'gpt-5-mini', 'support-tickets-v12', 'r77', '78.6%', '今天 08:12'], ['前端改动正确性', 'frontend-dev', 'gpt-5-codex', 'web-patch-v4', 'r9', '94.1%', '3 天前'], ['提示注入红队', 'all', '混合', 'redteam-inject-v2', 'r5', '71.3%', '6 小时前']], tabs: ['项目', '数据集', '评估类型', '运行', '对比', '单样本', '评分方式', '回归门禁'], footnote: '评估项目', insight: '项目绑定 Agent 版本、模型、数据集和策略版本。任一项发生变化，历史分数就不能直接比较。', detail: ['Agent', '模型', '数据集', '通过 / 失败 / 跳过', '门禁', '基线'], values: ['release-bot', 'gpt-5-codex', 'golden-release-v3', '157 / 17 / 6', '总体 ≥85% · 通过', 'r41']},
  { id: 'lifecycle', label: 'lifecycle', title: '生命周期', columns: ['运行', 'Agent', '工作空间', '状态', '阶段', '检查点', '更新时间'], metrics: [['24', '活跃运行', '队列与执行中'], ['3', '后台运行', '跨会话持续'], ['2', '可恢复检查点', '快照已保存'], ['1', '等待交接', '目标 Agent 空闲时继续']], records: [['run_2b7d', 'release-bot', 'ws-payments', '执行中', 'step 14 · 工具调用', 'ck-8821', '09:41'], ['run_2b55', 'data-analyst', 'ws-analytics', '等待审批', 'step 8 · 等待策略', 'ck-8794', '09:38'], ['run_2b41', 'frontend-dev', 'ws-web', '可恢复', 'step 17 · 验证', 'ck-8701', '09:36'], ['run_2b21', 'ops-runner', 'ws-infra', '已完成', '终态 · 成功', '—', '09:18'], ['run_29f7', 'data-analyst', 'ws-payments', '已终止', '终态 · 超时', 'ck-8410', '昨天']], tabs: ['运行状态', '状态机', '终止条件', '后台运行', '检查点', '恢复', 'Handoff'], footnote: '运行生命周期', insight: '状态转换必须可解释、可恢复。终止条件在启动前确定，检查点记录当时的执行环境与策略版本。', detail: ['当前状态', '当前阶段', '终止条件', '检查点', '恢复策略', '最近转换'], values: ['执行中', 'step 14 · 工具调用', '预算 82% / 100%', 'ck-8821 · 09:41', '从最近检查点恢复', '09:41:12 · 工具调用 → 等待结果']},
  { id: 'artifacts', label: 'artifacts', title: '产物与存储', columns: ['文件', '类型', '大小', '来源运行', '版本', '状态'], metrics: [['12', '产物总数', '绑定来源运行'], ['13.68 GB', '存储用量', '当前工作空间'], ['34', '今日新增', '可按运行筛选'], ['1.39 GB', '待清理', '保留策略命中']], records: [['fix-orders-status.patch', '代码补丁', '18.4 MB', 'run_2b7d', 'v3', '正常'], ['weekly-report.md', '文档', '42.1 MB', 'run_2b55', 'v1', '正常'], ['failure-chart.png', '图片', '284.0 MB', 'run_2b55', 'v1', '正常'], ['build-2024-11-02.log', '日志', '1.21 GB', 'run_2b41', 'v1', '待清理'], ['report.json', '结构化 JSON', '6.2 MB', 'run_2b41', 'v2', '正常'], ['orders-sample.csv', 'CSV', '88.6 MB', 'run_2b55', 'v1', '正常'], ['test-report.html', '测试报告', '212.0 MB', 'run_2b02', 'v4', '正常'], ['model-raw.txt', '模型输出', '14.2 MB', 'run_2b21', 'v1', '受限'], ['ctx-2b7d-step14.bin', '上下文快照', '3.77 GB', 'run_2b7d', 'v1', '正常'], ['ck-8821.bin', '检查点', '7.25 GB', 'run_2b7d', 'v1', '正常'], ['legacy-export.csv', 'CSV', '640.0 MB', 'run_29a0', 'v1', '损坏'], ['screenshot-09-41.png', '截图', '186.0 MB', 'run_2b7d', 'v1', '待清理']], tabs: ['目录', '类型', '操作', '版本', '存储', '权限', '生命周期'], footnote: '产物目录', insight: '产物必须关联来源运行。状态、体积和校验结果都要清楚可见；全文内容检索交由追踪与日志处理。', detail: ['来源运行', '工作空间', '创建时间', '版本与权限', '校验和', '状态'], values: ['run_2b7d', 'ws-payments', '09:41', 'v3 · 继承空间', 'sha256:9f2a…c41d', '正常 · 校验通过']},
  { id: 'observability', label: 'observability', title: '追踪与日志', columns: ['时间', '事件', '类型', '持续时间', '状态', '运行'], metrics: [['1,284', '事件 / 24h', '全部运行'], ['96.8%', '成功率', '运行完成'], ['1.42s', '平均延迟', '模型与工具'], ['3', '异常', '需查看详情']], records: [['09:41:12.084', 'run.started', '运行', '—', '成功', 'run_2b7d'], ['09:41:13.012', 'agent.plan', 'Agent', '0.91s', '成功', 'run_2b7d'], ['09:41:14.220', 'model.request', '模型', '1.18s', '成功', 'run_2b7d'], ['09:41:18.730', 'tool.shell.exec', '工具', '4.51s', '待审批', 'run_2b7d'], ['09:41:18.744', 'policy.matched', '策略', '14ms', '成功', 'run_2b7d'], ['09:41:20.101', 'approval.wait', '审批', '21m', '等待中', 'run_2b7d'], ['09:38:41.902', 'artifact.write', '产物', '0.08s', '成功', 'run_2b55'], ['09:36:02.105', 'model.timeout', '异常', '30s', '失败', 'run_2b41']], tabs: ['事件时间线', 'Span 树', '运行详情', '模型调用', '工具调用', '日志搜索', '指标'], footnote: '事件时间线', insight: '完整保留父子 Span、策略命中和工具输入输出摘要。用 Trace ID 串起模型请求、审批等待和产物写入。', detail: ['Trace ID', '父 Span', '运行', 'Agent / 模型', '属性', '结果'], values: ['tr_2b7d_0912', 'sp_agent_turn_14', 'run_2b7d', 'release-bot · gpt-5-codex', 'POL-TOOL-014 · shell.exec', '等待审批 · 21m']},
]

const config = computed(() => tabs.find(item => item.id === props.page) || tabs[0])
const activeTab = ref('')
const query = ref('')
const status = ref('全部状态')
const selected = ref(0)
const leftFilter = ref('全部')
const details = {
  machines: { filters: ['全部', '在线', '忙碌', 'GPU', '异常'], queueTitle: '执行节点', secondary: '按资源池分布', columns: ['资源池', '节点', '槽位', '占用', '健康'], rows: [['cpu-pool', 'runner-01 / runner-02', '4/6', '2', '正常'], ['gpu-pool', 'gpu-01', '1/2', '1', '正常'], ['high-security', 'runner-01 / runner-05 / k8s-pod-a', '3/4', '1', '紧张'], ['browser-pool', 'edge-05 / local-dev', '2/3', '2', '紧张'], ['ci-pool', 'k8s-pod-a / ci-runner-7', '9/12', '4', '降级']], principles: ['心跳是唯一可信信号', '槽位才是调度单位', '版本必须可见'] },
  approvals: { filters: ['全部', '待审批', '已批准', '已拒绝', '已结束'], queueTitle: '审批队列', secondary: '四类请求的形状不一样', principles: ['低风险自动可批 · ≤2 级', '中风险需看内容 · 3 级', '高风险必须会签 · 4 级', '已超时的不能复活'] },
  governance: { filters: ['全部', '工具', '文件', '网络', '其他'], queueTitle: '策略目录', secondary: '策略生命周期 · 缺一步就是裸奔', principles: ['优先级是顺序不是权威', '默认拒绝是地基', '目录要显示版本', '停用的策略别删除'] },
  verification: { filters: ['全部', '达标', '待改进', '红队'], queueTitle: '评估项目', secondary: '九类评估的当前分布', columns: ['评估类型', '得分', '趋势'], rows: [['功能正确性', '92%', '↑ 4'], ['工具调用正确性', '94%', '↑ 2'], ['输出格式', '98%', '稳定'], ['安全策略', '100%', '稳定'], ['注入抵抗', '74%', '↓ 3'], ['敏感信息泄露', '96%', '↑ 1'], ['成本', '81%', '稳定'], ['延迟', '88%', '↑ 2'], ['稳定性', '85%', '↑ 1']], principles: ['项目 ≠ 测试套件', '分组看，不看总分', '九类要能单独失败'] },
  lifecycle: { filters: ['全部', '运行中', '等待', '终态'], queueTitle: '运行队列', secondary: '各状态的平均停留', columns: ['状态', '停留时间', '说明'], rows: [['执行中', '3m04s', '模型循环执行中'], ['等待审批', '21m', '等待决策'], ['初始化', '8.2s', '分配执行资源'], ['等待工具', '41s', '外部工具响应']], principles: ['状态机是算法，不是流程图', '终态不可出边', '等待态必须有 TTL', '恢复要经过恢复点'] },
  artifacts: { filters: ['全部', '代码/文档', '图片/截图', '数据/日志', '系统'], queueTitle: '产物目录', secondary: '按来源运行分组', columns: ['运行', 'Agent / 空间', '产物', '体积', '最近'], rows: [['run_2b7d', 'release-bot · ws-payments', '4', '11.22 GB', '09:41'], ['run_2b55', 'data-analyst · ws-analytics', '3', '414.7 MB', '09:38'], ['run_2b41', 'frontend-dev · ws-web', '2', '1.22 GB', '09:36'], ['run_2b02', 'release-bot · ws-payments', '1', '212.0 MB', '09:20'], ['run_2b21', 'ops-runner · ws-infra', '1', '14.2 MB', '09:18']], principles: ['产物必须绑运行', '状态要可见', '按来源筛选', '体积要显示'] },
  observability: { filters: ['全部', '运行', '模型', '工具', '策略', '异常'], queueTitle: '运行列表', secondary: 'Span 树 · 父子调用关系', columns: ['Span', '类型', '耗时', '状态'], rows: [['agent.turn', 'Agent', '1.84s', '成功'], ['  model.request', '模型', '1.18s', '成功'], ['  tool.shell.exec', '工具', '4.51s', '待审批'], ['  policy.matched', '策略', '14ms', '命中'], ['  artifact.write', '产物', '0.08s', '成功']], principles: ['事件要能关联运行', 'Span 保留父子关系', '日志可按 Trace 检索', '异常要有错误归因'] },
}
const pageDetails = computed(() => details[props.page] || details.machines)
const queueRows = computed(() => config.value.records.filter(row => {
  const matches = leftFilter.value === '全部' || (props.page === 'machines' && leftFilter.value === 'GPU' ? /GPU/.test(row.join(' ')) : leftFilter.value === '异常' ? /降级|离线|失败|损坏|待清理/.test(row.join(' ')) : row.includes(leftFilter.value) || (props.page === 'verification' && leftFilter.value === '达标' && Number.parseFloat(row[5]) >= 85) || (props.page === 'verification' && leftFilter.value === '待改进' && Number.parseFloat(row[5]) < 85) || (props.page === 'verification' && leftFilter.value === '红队' && /红队/.test(row[0])))
  return matches && row.join(' ').toLowerCase().includes(query.value.trim().toLowerCase())
}))
const records = computed(() => {
  const source = config.value.records
  if (activeTab.value === '运行关联') return source.filter(row => row.some(cell => /run_|RUN-|运行|step|Trace|审批/.test(cell)))
  if (activeTab.value === '变更记录') return source.filter(row => row.some(cell => /离线|降级|待|失败|损坏|已终止|受限/.test(cell)))
  return source
})
const filtered = computed(() => records.value.filter(row => {
  const text = row.join(' ').toLowerCase()
  const state = row.find(value => ['正常', '待清理', '损坏', '受限', '在线', '忙碌', '降级', '排空中', '离线', '空闲', '待审批', '已批准', '已拒绝', '已超时', '已取消', '生效', '停用', '执行中', '等待审批', '可恢复', '已完成', '已终止', '成功', '失败', '等待中'].includes(value))
  return text.includes(query.value.trim().toLowerCase()) && (status.value === '全部状态' || status.value === state)
}))
const selectedRow = computed(() => config.value.records[selected.value] || config.value.records[0])
const contextPercent = computed(() => ({ machines: 64, approvals: 70, governance: 82, verification: 87, lifecycle: 35, artifacts: 42, observability: 58 }[props.page] || 50))
const selectedQueueLabel = row => props.page === 'approvals' ? row[3] : props.page === 'observability' ? row[1] : props.page === 'verification' ? row[0] : row[0]
const selectedQueueMeta = row => props.page === 'approvals' ? `${row[5]} · ${row[2]} · ${row[0].slice(-4)}` : props.page === 'machines' ? `${row[1]} · ${row[4]} 空闲` : props.page === 'verification' ? `${row[5]} · ${row[3]}` : props.page === 'lifecycle' ? `${row[1]} · ${row[6]}` : props.page === 'artifacts' ? `${row[2]} · ${row[1]} · ${row[3]}` : props.page === 'observability' ? `${row[0]} · ${row[3]} · ${row[5]}` : `${row[2] || row[1]} · ${row[0]}`
const selectedQueueState = row => props.page === 'machines' ? row[3] : props.page === 'approvals' ? row[6] : props.page === 'governance' ? row[6] : props.page === 'verification' ? Number.parseFloat(row[5]) >= 85 ? '达标' : '待改进' : props.page === 'lifecycle' ? row[3] : props.page === 'artifacts' ? row[5] : row[4]
const displayNames = {
  approvals: '待审批', eval: '验证与评估', lifecycle: '生命周期', artifacts: '产物与存储', observability: '追踪与日志',
  Agent: '智能体', Run: '运行', 'Agent / 模型': '智能体 / 模型', 'Trace ID': '追踪编号', '父 Span': '上级调用片段', Span: '调用片段', 'Span 树': '调用关系', SLA: '时限',
  'release-bot': '发布助手', 'data-analyst': '数据分析助手', 'frontend-dev': '前端开发助手', 'support-agent': '客服助手', 'ops-runner': '运维助手', all: '全部智能体',
  'shell.exec': '命令执行', 'postgres.query': '数据库查询', 'fs.write': '写入文件', 'fs.delete': '删除文件', 'http.fetch': '网络请求', 'k8s.apply': '部署配置', 'npm.publish': '发布软件包', 'crm.update': '更新客户记录',
  'run.started': '运行已启动', 'agent.plan': '智能体制定计划', 'model.request': '模型请求', 'tool.shell.exec': '调用命令执行工具', 'policy.matched': '策略已匹配', 'approval.wait': '等待审批', 'artifact.write': '产物已写入', 'model.timeout': '模型请求超时',
  '执行中': '正在执行', '等待审批': '等待审批', '可恢复': '可以恢复', '已完成': '已完成', '已终止': '已停止',
}
function displayText(value) {
  if (displayNames[value]) return displayNames[value]
  if (value.includes(' · ')) return value.split(' · ').map(part => displayNames[part] || part).join(' · ')
  return value
}
watch(() => props.page, () => { activeTab.value = ''; query.value = ''; status.value = '全部状态'; leftFilter.value = '全部'; selected.value = 0 })
watch([activeTab, query, status, leftFilter], () => { selected.value = 0 })

function action(label) { emit('notify', `${label}为本地演示操作，接入运行控制 API 后可用`) }
</script>

<template>
  <section class="governance-workbench" :class="`page-${page}`">
    <header class="gc-header">
      <div class="gc-header-top">
        <div class="gc-brand"><span class="gc-mark">{{ config.title.slice(0, 2) }}</span><div><h1>{{ config.title }}</h1><p>{{ displayText(config.label) }} · {{ config.tabs.map(displayText).join(' / ') }}</p></div></div>
        <p class="gc-edgetip">{{ config.insight }}</p>
      </div>
      <div class="gc-metrics"><div v-for="metric in config.metrics" :key="metric[1]" class="gc-metric"><strong>{{ metric[0] }}</strong><span><i aria-hidden="true"></i>{{ metric[1] }}</span></div></div>
    </header>
    <div class="gc-workspace">
      <aside class="gc-queue">
        <div class="gc-filter-list"><button v-for="filterItem in pageDetails.filters" :key="filterItem" :class="{ active: leftFilter === filterItem }" @click="leftFilter = filterItem">{{ filterItem }}</button></div>
        <div class="gc-queue-scroll"><button v-for="(row, index) in queueRows" :key="row[0]" class="gc-queue-item" :class="{ selected: selectedRow?.[0] === row[0], warn: /待|异常|离线|失败|损坏/.test(selectedQueueState(row)) }" @click="selected = config.records.indexOf(row)"><span class="gc-queue-dot"></span><span class="gc-queue-copy"><strong>{{ displayText(selectedQueueLabel(row)) }}</strong><small>{{ displayText(selectedQueueMeta(row)) }}</small></span><span class="gc-queue-state">{{ displayText(selectedQueueState(row)) }}</span></button></div>
        <footer class="gc-queue-footer"><span>{{ queueRows.length }} / {{ config.records.length }} 条</span><span>{{ props.page === 'approvals' ? 'SLA 30m' : props.page === 'machines' ? '自动发现 开' : '演示数据' }}</span><button @click="action('推进时间')">{{ props.page === 'approvals' ? '模拟时间流逝 +10 分钟' : props.page === 'machines' ? '关闭自动发现' : '刷新当前列表' }}</button></footer>
      </aside>
      <main class="gc-main">
        <nav class="gc-tabs" aria-label="页面视图"><button v-for="tab in config.tabs" :key="tab" :class="{ active: (activeTab || config.tabs[0]) === tab }" @click="activeTab = tab">{{ tab }}</button></nav>
        <div class="gc-main-scroll">
          <div class="gc-panel gc-primary-panel">
            <header class="gc-panel-heading"><div><h2>{{ activeTab || config.tabs[0] }} · {{ pageDetails.queueTitle }}</h2><span>{{ filtered.length }} 条记录 · {{ props.page === 'approvals' ? '按等待时长降序 · SLA 30 分钟' : '选择记录查看详情' }}</span></div><div class="gc-panel-tools"><label><Search :size="13" /><input v-model="query" :placeholder="`搜索${config.title}`" /></label><button title="导出当前记录" @click="action('导出当前记录')"><ArrowDownToLine :size="14" /></button></div></header>
            <div class="gc-table-scroll"><div class="gc-table" :style="{ '--gc-cols': config.columns.length }"><div class="gc-table-head"><span v-for="column in config.columns" :key="column">{{ displayText(column) }}</span></div><button v-for="(row, index) in filtered" :key="row[0]" class="gc-row" :class="{ selected: selectedRow?.[0] === row[0] }" @click="selected = config.records.indexOf(row)"><span v-for="(cell, cellIndex) in row" :key="`${cell}-${cellIndex}`" :class="{ emphasis: cellIndex === 0, state: ['在线', '忙碌', '降级', '排空中', '离线', '待审批', '已批准', '已拒绝', '已超时', '已取消', '生效', '停用', '执行中', '等待审批', '可恢复', '已完成', '已终止', '正常', '待清理', '损坏', '受限', '成功', '失败', '等待中'].includes(cell), warning: /待|降级|离线|损坏|受限|失败/.test(cell) }">{{ displayText(cell) }}</span></button></div></div>
            <div class="gc-callout"><span>i</span><p>{{ config.insight }}</p></div>
          </div>
          <section v-if="props.page === 'approvals'" class="gc-panel gc-secondary"><header class="gc-panel-heading"><div><h2>{{ pageDetails.secondary }}</h2><span>处理方式不能一样</span></div></header><div class="gc-risk-grid"><div v-for="item in pageDetails.principles" :key="item"><strong>{{ item.split(' · ')[0] }}</strong><span>{{ item.split(' · ')[1] }}</span></div></div></section>
          <section v-else class="gc-panel gc-secondary"><header class="gc-panel-heading"><div><h2>{{ pageDetails.secondary }}</h2><span>当前视图 · 本地演示数据</span></div></header>
            <div v-if="pageDetails.columns" class="gc-secondary-table"><div class="gc-secondary-head"><span v-for="column in pageDetails.columns" :key="column">{{ column }}</span></div><div v-for="row in pageDetails.rows" :key="row[0]" class="gc-secondary-row"><span v-for="cell in row" :key="cell">{{ cell }}</span></div></div>
            <div v-else-if="props.page === 'governance'" class="gc-lifecycle-strip"><div v-for="(step, index) in ['草稿', '测试', '灰度', '发布', '回滚']" :key="step"><b>{{ String(index + 1).padStart(2, '0') }}</b><strong>{{ step }}</strong><small>{{ ['可改不生效', '拿真请求试算', '按作用域放量', '全量生效', '回到上一版'][index] }}</small><ChevronRight v-if="index < 4" :size="13" /></div></div>
            <div v-else-if="props.page === 'lifecycle'" class="gc-state-cells"><div v-for="stateName in ['创建', '等待资源', '排队', '初始化', '执行中', '等待审批', '等待工具', '暂停', '恢复中', '已成功', '已失败', '已超时', '已取消']" :key="stateName" :class="{ current: stateName === '执行中' }"><span>{{ stateName }}</span><small>{{ stateName === '执行中' ? '当前 · step 14' : '合法转换状态' }}</small></div></div>
            <div v-else-if="props.page === 'verification'" class="gc-principles"><span v-for="item in pageDetails.principles" :key="item"><ShieldCheck :size="13" />{{ item }}</span></div>
            <div v-else-if="props.page === 'artifacts'" class="gc-principles"><span v-for="item in pageDetails.principles" :key="item"><ShieldCheck :size="13" />{{ item }}</span></div>
            <div v-else-if="props.page === 'observability'" class="gc-principles"><span v-for="item in pageDetails.principles" :key="item"><Terminal :size="13" />{{ item }}</span></div>
            <div v-else class="gc-principles"><span v-for="item in pageDetails.principles" :key="item"><ShieldCheck :size="13" />{{ item }}</span></div>
          </section>
          <section class="gc-panel gc-principles-panel"><header class="gc-panel-heading"><div><h2>三条判断</h2><span>这一屏之外，真正要盯的</span></div></header><div class="gc-principles"><span v-for="item in pageDetails.principles" :key="item"><b>{{ item.split(' · ')[0] }}</b><small>{{ item.split(' · ')[1] || config.insight }}</small></span></div></section>
          <footer class="gc-related"><span>相关</span><button v-for="link in ['执行隔离', '待审批', '治理策略', '生命周期', '追踪与日志']" :key="link" @click="action(`打开${link}`)" >{{ link }}<X :size="10" /></button><button class="gc-return" @click="action('返回入口')">返回入口</button></footer>
        </div>
      </main>
      <aside class="gc-inspector">
        <header class="gc-inspector-heading"><strong>{{ props.page === 'approvals' ? '请求上下文' : props.page === 'observability' ? '运行详情' : `${config.title}详情` }}</strong><small>{{ selectedRow?.[0] }}</small></header>
        <section class="gc-inspector-card gc-progress-card"><div class="gc-ring" :style="{ '--progress': `${contextPercent}%` }"><strong>{{ contextPercent }}%</strong></div><div><b>{{ selectedQueueLabel(selectedRow) }}</b><small>{{ selectedQueueMeta(selectedRow) }}</small></div><span class="gc-state-pill">{{ selectedQueueState(selectedRow) }}</span></section>
        <section class="gc-inspector-card"><h3>{{ props.page === 'approvals' ? '风险与归属' : '运行上下文' }}</h3><div v-for="(label, index) in config.columns" :key="label" class="gc-inspector-field"><span>{{ displayText(label) }}</span><b>{{ displayText(selectedRow?.[index] || '—') }}</b></div></section>
        <section class="gc-inspector-card"><h3>状态时间线</h3><div v-for="(event, index) in (props.page === 'approvals' ? ['创建请求', '通知已送达', '等待审批中'] : props.page === 'lifecycle' ? ['创建', '排队 → 初始化', '执行中'] : ['记录创建', '状态更新', '最近活动'])" :key="event" class="gc-event"><i :class="{ current: index === 2 }"></i><span><b>{{ event }}</b><small>{{ index === 0 ? '09:37 · 请求已创建' : index === 1 ? '09:38 · 关联策略命中' : '当前 · 最近心跳正常' }}</small></span></div></section>
        <section class="gc-inspector-card"><h3>跳转</h3><div class="gc-jump-actions"><button @click="action('查看运行')">运行</button><button @click="action('查看追踪记录')">追踪记录</button><button @click="action('查看智能体')">智能体</button><button @click="action('复制编号')">复制编号</button></div><p>{{ config.insight }}</p></section>
        <footer class="gc-inspector-note"><ShieldCheck :size="14" /><span>本地演示数据 · 尚未连接运行控制 API</span></footer>
      </aside>
    </div>
  </section>
</template>
