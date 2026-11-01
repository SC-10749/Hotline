<script setup>
import { computed, ref } from 'vue'
import { Activity as ActivityIcon, Archive, ArrowRight, Brain, Check, CircleAlert, Clock3, Database, GitBranch, Layers3, LockKeyhole, RefreshCw, ShieldCheck, Sparkles, Workflow, X } from 'lucide-vue-next'

const modes = [
  { id: 'memory', label: '记忆库' },
  { id: 'state', label: '状态库' },
]

const memoryFilters = [
  { id: 'all', label: '全部', count: 10 },
  { id: 'work', label: '工作', count: 1 },
  { id: 'episodic', label: '情节', count: 2 },
  { id: 'semantic', label: '语义', count: 2 },
  { id: 'procedural', label: '程序', count: 1 },
  { id: 'user', label: '用户', count: 2 },
  { id: 'project', label: '项目', count: 2 },
]

const memories = ref([
  { id: 'mem-01', title: '偏好中文回复', category: 'user', categoryLabel: '用户', source: '用户显式', strength: 0.95, date: '10-02', scope: '用户', detail: '跨会话保留用户的语言偏好，影响默认输出语言。', status: '长期' },
  { id: 'mem-02', title: '提交前必须跑端到端测试', category: 'project', categoryLabel: '项目', source: '项目文件', strength: 0.92, date: '09-28', scope: '客服运营', detail: '项目协作约定：提交变更前必须运行完整流程验证。', status: '长期' },
  { id: 'mem-03', title: '登录页面报错 500 的原因', category: 'semantic', categoryLabel: '语义', source: '系统归纳', strength: 0.88, date: '10-01', scope: '客服运营', detail: '间歇性服务器错误与浏览器凭据刷新竞态相关，已由回归记录确认。', status: '长期' },
  { id: 'mem-04', title: '排查服务器错误的步骤', category: 'procedural', categoryLabel: '程序', source: '技能整理', strength: 0.84, date: '09-20', scope: '客服运营', detail: '先复现问题，再检查凭据刷新流程，最后运行并发回归用例。', status: '长期' },
  { id: 'mem-05', title: '故障事件 2311 复盘', category: 'episodic', categoryLabel: '情节', source: '系统归纳', strength: 0.79, date: '10-01', scope: '客服运营', detail: '一次已完成的故障复盘，保留决策与结果供后续参考。', status: '长期' },
  { id: 'mem-06', title: '旧项目地址', category: 'user', categoryLabel: '用户', source: '用户提供', strength: 0.22, date: '2023-11', scope: '用户', detail: '历史地址很久未被使用，建议移入低频存储。', status: '陈旧' },
  { id: 'mem-07', title: '不引入新依赖', category: 'project', categoryLabel: '项目', source: '项目文件', strength: 0.90, date: '09-15', scope: 'support-ops', detail: '当前项目优先使用已有依赖，新增依赖需要明确理由。', status: '长期' },
  { id: 'mem-08', title: '会话缓存默认保留 30 分钟', category: 'semantic', categoryLabel: '语义', source: '文档整理', strength: 0.72, date: '09-22', scope: '客服运营', detail: '会话缓存的默认有效时间为 30 分钟。', status: '长期' },
  { id: 'mem-09', title: '本轮临时约束', category: 'work', categoryLabel: '工作', source: '当前运行', strength: 0.40, date: '现在', scope: 'RUN-2048', detail: '本轮任务临时约束，仅在当前运行上下文中保留。', status: '工作' },
  { id: 'mem-10', title: '上次会话结论', category: 'episodic', categoryLabel: '情节', source: '隐式抽取', strength: 0.66, date: '10-02', scope: 'support-ops', detail: '上次会话确认 cookie 不是主要故障来源。', status: '长期' },
])

const states = ref([
  { id: 'state-01', title: '修复 /login 间歇 500', categoryLabel: '任务', source: 'RUN-2048', value: '进行中', detail: '当前任务目标，驱动执行流程。', status: '活动' },
  { id: 'state-02', title: '当前阶段', categoryLabel: '阶段', source: '系统自动写入', value: '执行中', detail: '当前运行阶段由调度器自动维护。', status: '活动' },
  { id: 'state-03', title: '已尝试次数', categoryLabel: '重试', source: '系统自动写入', value: '2', detail: '本轮已完成的尝试次数。', status: '活动' },
  { id: 'state-04', title: '恢复位置', categoryLabel: '位置', source: '系统自动写入', value: '会话文件第 210 行', detail: '当前执行位置，决定下一步从哪里恢复。', status: '活动' },
  { id: 'state-05', title: '重试等待时间', categoryLabel: '节流', source: '系统自动写入', value: '8 秒', detail: '下一次重试前的等待时间。', status: '活动' },
  { id: 'state-06', title: '最近检查点', categoryLabel: '检查点', source: '系统自动写入', value: '检查点 24', detail: '最近一次可恢复快照标识。', status: '活动' },
  { id: 'state-07', title: '是否需要审批', categoryLabel: '审批', source: '系统自动写入', value: '不需要', detail: '当前步骤不需要外部副作用审批。', status: '活动' },
  { id: 'state-08', title: '工作空间', categoryLabel: '工作区', source: '系统自动写入', value: '客服运营 / 主分支', detail: '执行任务绑定的工作空间和分支。', status: '活动' },
  { id: 'state-09', title: '最近错误类型', categoryLabel: '错误', source: '系统自动写入', value: '凭据刷新冲突', detail: '最近一次错误分类。', status: '活动' },
])

const views = [
  { id: 'boundary', label: '边界', icon: GitBranch },
  { id: 'write', label: '记忆·分类写入', icon: Brain },
  { id: 'retrieve', label: '记忆·检索更新', icon: RefreshCw },
  { id: 'inject', label: '记忆·注入安全', icon: ShieldCheck },
  { id: 'manage', label: '记忆·管理', icon: Archive },
  { id: 'structure', label: '状态·结构', icon: Database },
  { id: 'lifecycle', label: '状态·生命周期', icon: Workflow },
  { id: 'checkpoint', label: '状态·检查点', icon: Layers3 },
  { id: 'concurrency', label: '状态·并发传递', icon: LockKeyhole },
  { id: 'visual', label: '状态·可视化', icon: Sparkles },
  { id: 'maturity', label: '成熟度', icon: CircleAlert },
]

const mode = ref('memory')
const filter = ref('all')
const selectedId = ref('mem-01')
const activeView = ref('boundary')
const toast = ref('')
const migrated = ref(false)
const decayArchived = ref(false)
const boundaryResult = ref(null)

const visibleRecords = computed(() => mode.value === 'memory'
  ? memories.value.filter(item => filter.value === 'all' || item.category === filter.value)
  : states.value)
const selectedRecord = computed(() => visibleRecords.value.find(item => item.id === selectedId.value) || visibleRecords.value[0])

function notify(message) {
  toast.value = message
  window.clearTimeout(notify.timer)
  notify.timer = window.setTimeout(() => { toast.value = '' }, 2500)
}
function selectMode(nextMode) {
  mode.value = nextMode
  filter.value = 'all'
  selectedId.value = nextMode === 'memory' ? 'mem-01' : 'state-01'
  boundaryResult.value = null
}
function selectFilter(nextFilter) {
  filter.value = nextFilter
  if (!visibleRecords.value.some(item => item.id === selectedId.value)) selectedId.value = visibleRecords.value[0]?.id
}
function migrateRecords() {
  migrated.value = true
  notify('2 处错放已标记为待迁移（演示）')
}
function archiveStale() {
  decayArchived.value = true
  notify('陈旧记忆已归档到冷存储（演示）')
}
function judgeBoundary(item) {
  boundaryResult.value = item
}
function formatStrength(value) {
  return value.toFixed(2)
}
</script>

<template>
  <section class="memory-state-page">
    <header class="memory-page-heading">
      <div><h1>记忆与状态</h1><p>区分信息留存与流程进度 · 边界 / 写入 / 检索 / 更新 / 注入 / 检查点 / 并发</p></div>
      <div class="memory-heading-actions"><span class="memory-rule"><Brain :size="14" />记忆 ≠ 状态</span><button class="memory-primary" @click="notify('记忆与状态同步检查已完成（演示）')"><RefreshCw :size="14" />检查同步</button></div>
    </header>

    <div class="memory-kpis">
      <div><span>记忆条目</span><strong>10 <small>/ 128</small></strong><em>7% 容量</em></div>
      <div><span>状态字段</span><strong>9</strong><em>当前运行结构</em></div>
      <div><span>陈旧待衰减</span><strong class="warning">{{ decayArchived ? 0 : 1 }}</strong><em>{{ decayArchived ? '已归档' : 'strength &lt; 0.3' }}</em></div>
      <div><span>检查点</span><strong>6 <small>· 10.8MB</small></strong><em>可恢复快照</em></div>
      <div><span>错放风险</span><strong class="danger">{{ migrated ? 0 : 2 }}</strong><em>{{ migrated ? '已标记迁移' : '待处理' }}</em></div>
    </div>

    <div class="memory-workbench">
      <aside class="memory-record-panel">
        <div class="memory-panel-heading"><div><h2>记忆与状态库</h2><span>{{ mode === 'memory' ? '跨会话可复用内容' : '驱动当前流程的结构化字段' }}</span></div><Database :size="15" /></div>
        <div class="memory-mode-tabs" role="tablist"><button v-for="item in modes" :key="item.id" :class="{ active: mode === item.id }" @click="selectMode(item.id)">{{ item.label }}<span>{{ item.id === 'memory' ? 10 : 9 }}</span></button></div>
        <div v-if="mode === 'memory'" class="memory-filter-list"><button v-for="item in memoryFilters" :key="item.id" :class="{ active: filter === item.id }" @click="selectFilter(item.id)">{{ item.label }}<span>{{ item.count }}</span></button></div>
        <div class="memory-record-list" role="listbox" :aria-label="mode === 'memory' ? '记忆条目' : '状态字段'">
          <button v-for="record in visibleRecords" :key="record.id" class="memory-record-row" :class="{ selected: selectedRecord?.id === record.id, stale: record.status === '陈旧' }" @click="selectedId = record.id">
            <span class="record-row-top"><strong>{{ record.title }}</strong><em v-if="mode === 'memory'">{{ formatStrength(record.strength) }}</em><em v-else>{{ record.value }}</em></span>
            <span class="record-row-meta"><span>{{ record.categoryLabel }}</span><i></i><span>{{ record.source }}</span><i></i><span>{{ record.date || record.status }}</span></span>
          </button>
        </div>
        <footer class="memory-record-footer"><span>{{ mode === 'memory' ? '长期 9 · 陈旧 1' : '活动 9 · 自动写入' }}</span><button @click="notify('已按强度排序（演示）')">按强度排序</button></footer>
      </aside>

      <main class="memory-center-panel">
        <nav class="memory-view-tabs" aria-label="记忆与状态视图"><button v-for="view in views" :key="view.id" :class="{ active: activeView === view.id }" @click="activeView = view.id"><component :is="view.icon" :size="13" />{{ view.label }}</button></nav>
        <div v-if="activeView === 'boundary'" class="memory-view-content">
          <div class="boundary-grid">
            <section class="memory-subpanel"><header><div><h2>记忆 Memory</h2><span>跨会话复用的知识与偏好</span></div><Brain :size="16" /></header><div class="boundary-list"><div><span>生命周期</span><b>长 · 跨会话</b></div><div><span>作用方式</span><b>注入上下文，影响模型判断</b></div><div><span>主体</span><b>知识、事实、偏好</b></div><div><span>典型载体</span><b>文本、向量、实体表</b></div><div><span>写入者</span><b>模型主动写 + 用户写</b></div><div><span>典型错误</span><b>把运行进度写成记忆</b></div></div></section>
            <section class="memory-subpanel"><header><div><h2>状态 State</h2><span>驱动当前程序流程的数据</span></div><Workflow :size="16" /></header><div class="boundary-list"><div><span>生命周期</span><b>短 · 随任务或会话结束</b></div><div><span>作用方式</span><b>结构化读写，驱动程序流程</b></div><div><span>主体</span><b>进度、位置、中间结果</b></div><div><span>典型载体</span><b>schema、检查点、运行记录</b></div><div><span>写入者</span><b>系统自动写</b></div><div><span>典型错误</span><b>把用户偏好塞进状态字段</b></div></div></section>
          </div>
          <p class="boundary-caption">记忆回答「这个用户 / 项目是什么样的」，状态回答「现在走到哪了」。</p>
          <div class="risk-grid"><section class="memory-subpanel"><header><div><h2>错放风险</h2><span>检测到 {{ migrated ? 0 : 2 }} 处边界错误</span></div><CircleAlert :size="16" /></header><div class="risk-row"><div><strong>把运行进度写成记忆</strong><code>记住（“正在执行第 3 步，任务：修复登录错误”）</code></div><span :class="{ fixed: migrated }">{{ migrated ? '已标记迁移' : '错放 · 未修' }}</span></div><div class="risk-row"><div><strong>把用户偏好塞进状态字段</strong><code>用户偏好中文回复：是</code></div><span :class="{ fixed: migrated }">{{ migrated ? '已标记迁移' : '错放 · 未修' }}</span></div><button class="memory-secondary" @click="migrateRecords"><ArrowRight :size="14" />一键迁移到正确的库</button></section><section class="memory-subpanel judge-panel"><header><div><h2>边界判断器</h2><span>点击片段判断应归记忆还是状态</span></div><GitBranch :size="16" /></header><button v-for="item in ['用户要求中文回复','当前第 3 步 · 会话文件第 210 行','上次会话确认凭据问题并非主因','第 2 次重试 · 等待 8 秒']" :key="item" class="judge-item" @click="judgeBoundary(item)"><span>{{ item }}</span><ArrowRight :size="13" /></button><div v-if="boundaryResult" class="judge-result"><strong>{{ boundaryResult }}</strong><span>{{ /用户|上次/.test(boundaryResult) ? '记忆 · 会话结束后仍有复用价值' : '状态 · 会让程序下一步不同' }}</span></div><p class="judge-note">会话结束后还需要吗？需要则归为记忆。它会改变程序下一步吗？会则归为状态。</p></section></div>
          <section class="memory-subpanel snapshot-panel"><header><div><h2>当前装配快照</h2><span>上半段注入模型，下半段驱动流程</span></div><span class="snapshot-total">412 tok</span></header><div class="snapshot-grid"><div><span>mem:user</span><b>偏好中文回复 · 0.95</b><small>120 tok</small></div><div><span>mem:project</span><b>提交前跑 e2e · 0.92</b><small>96 tok</small></div><div><span>mem:semantic</span><b>login 500 根因 · 0.88</b><small>88 tok</small></div><div class="state-snapshot"><span>state:task</span><b>修复 /login 间歇 500</b><small>48 tok</small></div><div class="state-snapshot"><span>state:stage</span><b>acting · attempt=2</b><small>24 tok</small></div><div class="state-snapshot"><span>state:cursor</span><b>session.ts:210</b><small>20 tok</small></div></div></section>
        </div>
        <div v-else class="memory-view-content generic-memory-view"><div class="memory-view-intro"><component :is="views.find(item => item.id === activeView)?.icon || Brain" :size="20" /><div><h2>{{ views.find(item => item.id === activeView)?.label }}</h2><p>此视图展示记忆与状态在当前控制面中的结构化操作、边界与运行证据。</p></div></div><div class="memory-generic-grid"><div v-for="item in (mode === 'memory' ? memories.slice(0, 4) : states.slice(0, 4))" :key="item.id" class="memory-generic-row"><strong>{{ item.title }}</strong><span>{{ item.detail }}</span><b>{{ item.strength ? formatStrength(item.strength) : item.value }}</b></div></div><button class="memory-secondary" @click="notify(`${views.find(item => item.id === activeView)?.label}检查已完成（演示）`)"><Check :size="14" />运行当前检查</button></div>
      </main>

      <aside class="memory-inspector"><section class="inspector-card"><header><div><h2>记忆库容量</h2><span>10 条 · 目标上限 140</span></div><Database :size="15" /></header><div class="inspector-meter"><i style="width: 7%"></i></div><div class="inspector-line"><span>占用</span><b>7%</b></div><div class="inspector-line"><span>陈旧项</span><b class="warning">{{ decayArchived ? 0 : 1 }} · 10%</b></div><p>陈旧低于 0.2 时归档冷存储。</p><button v-if="!decayArchived" class="inspector-action" @click="archiveStale"><Archive :size="13" />归档陈旧记忆</button></section><section class="inspector-card"><header><div><h2>注入预算</h2><span>5 条 · ≈ 878 tok</span></div><Layers3 :size="15" /></header><div class="inspector-meter"><i class="budget-meter" style="width: 53%"></i></div><div class="inspector-line"><span>预算使用</span><b>8%</b></div><p>阈值 15%，超过后应做分层与摘要。</p></section><section class="inspector-card"><header><div><h2>检查点</h2><span>6 个 · 10.8 MB</span></div><Clock3 :size="15" /></header><div class="checkpoint-lines"><span><b>ck-24</b> 当前可恢复</span><span><b>ck-23</b> 14:01:40</span><span><b>ck-22</b> 13:58:02</span></div></section><section class="inspector-card event-card"><header><div><h2>最近事件</h2><span>本地演示事件流</span></div><ActivityIcon /></header><div class="event-lines"><div><b>状态原子写入</b><span>stage=acting · attempt=2</span><small>14:02:11</small></div><div><b>记忆命中 3 条</b><span>注入 1,240 tok</span><small>14:01:40</small></div><div><b>陈旧记忆 1 条</b><span>strength&lt;0.3 建议降权</span><small>13:58:02</small></div></div></section><button class="memory-migrate-button" @click="migrateRecords"><ArrowRight :size="14" />一键迁移到正确的库</button></aside>
    </div>
    <div v-if="selectedRecord" class="memory-selection-strip"><span><strong>{{ mode === 'memory' ? '当前记忆' : '当前状态' }}</strong> {{ selectedRecord.title }}</span><span>{{ selectedRecord.detail }}</span><button aria-label="关闭当前选择" title="关闭当前选择" @click="selectedId = null"><X :size="14" /></button></div>
    <div v-if="toast" class="memory-toast"><Check :size="15" />{{ toast }}</div>
  </section>
</template>

.memory-state-page .snapshot-grid .state-snapshot{border-left:1px solid var(--ms-accent-line);border-color:var(--ms-accent-line);background:var(--ms-accent-soft)}
<style scoped>
.memory-state-page{--ms-bg:var(--h-canvas,#f4f5f7);--ms-surface:var(--h-surface,#fff);--ms-subtle:var(--h-subtle,#f8f9fb);--ms-line:var(--h-line,#dfe3e8);--ms-soft:var(--h-line-soft,#edf0f3);--ms-text:var(--h-text,#202631);--ms-secondary:var(--h-secondary,#566170);--ms-muted:var(--h-muted,#87909d);--ms-accent:var(--h-accent,#c96345);--ms-accent-soft:var(--h-accent-soft,#fbede8);--ms-accent-line:var(--h-accent-line,#e5b5a5);width:100%;color:var(--ms-text);font-family:inherit}.memory-page-heading{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:12px}.memory-page-heading h1{margin:0;font-size:22px;letter-spacing:0}.memory-page-heading p{margin:5px 0 0;color:var(--ms-muted);font-size:11px}.memory-heading-actions{display:flex;align-items:center;gap:8px}.memory-rule{display:flex;align-items:center;gap:6px;min-height:32px;padding:0 9px;border:1px solid var(--ms-line);border-radius:6px;background:var(--ms-surface);color:var(--ms-secondary);font-size:10px}.memory-primary,.memory-secondary,.inspector-action,.memory-migrate-button{display:inline-flex;align-items:center;justify-content:center;gap:6px;border:1px solid var(--ms-accent);border-radius:6px;background:var(--ms-accent);color:#fff;font:inherit;font-size:10px;cursor:pointer}.memory-primary{min-height:32px;padding:0 10px}.memory-kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;margin-bottom:10px}.memory-kpis>div,.memory-subpanel,.inspector-card{min-width:0;border:1px solid var(--ms-line);border-radius:7px;background:var(--ms-surface);box-shadow:none}.memory-kpis>div{padding:10px 11px}.memory-kpis span,.memory-kpis em{display:block;color:var(--ms-muted);font-size:9px;font-style:normal}.memory-kpis strong{display:block;margin-top:5px;font-size:22px;line-height:1.05}.memory-kpis strong small{font-size:11px;color:var(--ms-muted);font-weight:500}.memory-kpis em{margin-top:5px}.warning{color:#b56b10!important}.danger{color:#bd5145!important}.memory-workbench{display:grid;grid-template-columns:245px minmax(0,1fr) 230px;gap:10px;align-items:start}.memory-record-panel,.memory-center-panel,.memory-inspector{min-width:0}.memory-record-panel{border:1px solid var(--ms-line);border-radius:7px;background:var(--ms-surface);overflow:hidden}.memory-panel-heading,.inspector-card header,.memory-subpanel header{display:flex;justify-content:space-between;align-items:center;gap:8px}.memory-panel-heading{min-height:50px;padding:0 12px;border-bottom:1px solid var(--ms-soft)}.memory-panel-heading h2,.memory-subpanel h2,.inspector-card h2{margin:0;font-size:12px}.memory-panel-heading span,.memory-subpanel header span,.inspector-card header span{display:block;margin-top:3px;color:var(--ms-muted);font-size:9px}.memory-mode-tabs{display:grid;grid-template-columns:1fr 1fr;gap:3px;margin:8px;padding:3px;border:1px solid var(--ms-soft);border-radius:6px;background:var(--ms-subtle)}.memory-mode-tabs button,.memory-filter-list button{border:0;background:transparent;color:var(--ms-secondary);font:inherit;font-size:10px;cursor:pointer}.memory-mode-tabs button{padding:7px 5px;border-radius:4px}.memory-mode-tabs button.active,.memory-filter-list button.active{background:var(--ms-accent-soft);color:var(--ms-accent)}.memory-mode-tabs span,.memory-filter-list span{margin-left:4px;color:var(--ms-muted);font-variant-numeric:tabular-nums}.memory-filter-list{display:flex;gap:3px;padding:0 8px 8px;overflow-x:auto}.memory-filter-list button{padding:5px 6px;white-space:nowrap;border-radius:4px}.memory-record-list{height:430px;padding:0 7px 7px;overflow:auto}.memory-record-row{display:block;width:100%;margin-bottom:4px;padding:8px;border:1px solid transparent;border-radius:5px;background:transparent;text-align:left;color:inherit;cursor:pointer}.memory-record-row:hover{background:var(--ms-subtle)}.memory-record-row.selected{border-color:var(--ms-accent-line);background:var(--ms-accent-soft)}.memory-record-row.stale{opacity:.78}.record-row-top{display:flex;justify-content:space-between;gap:5px}.record-row-top strong{min-width:0;overflow:hidden;font-size:10px;text-overflow:ellipsis;white-space:nowrap}.record-row-top em{color:var(--ms-accent);font-size:9px;font-style:normal;font-variant-numeric:tabular-nums}.record-row-meta{display:flex;gap:5px;margin-top:5px;color:var(--ms-muted);font-size:8px;white-space:nowrap}.record-row-meta i{width:2px;height:2px;margin-top:4px;border-radius:50%;background:var(--ms-muted)}.memory-record-footer{display:flex;justify-content:space-between;gap:6px;padding:9px 10px;border-top:1px solid var(--ms-soft);color:var(--ms-muted);font-size:9px}.memory-record-footer button{border:0;background:transparent;color:var(--ms-accent);font:inherit;font-size:9px;cursor:pointer}.memory-view-tabs{display:flex;gap:10px;min-width:0;min-height:44px;margin-bottom:8px;padding:0 12px;border:0;border-bottom:1px solid var(--ms-line);border-radius:0;background:var(--ms-surface);overflow-x:auto;scrollbar-width:none}.memory-view-tabs button{position:relative;display:flex;flex:0 0 auto;min-height:43px;align-items:center;gap:4px;padding:0;border:0;border-radius:0;background:transparent;color:var(--ms-secondary);font:inherit;font-size:10px;white-space:nowrap;cursor:pointer}.memory-view-tabs button.active{background:transparent;color:var(--ms-accent-strong)}.memory-view-tabs button.active::after{position:absolute;right:0;bottom:-1px;left:0;height:2px;background:var(--ms-accent);content:""}.memory-view-content{min-width:0}.boundary-grid,.risk-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.memory-subpanel{padding:11px}.memory-subpanel header{padding-bottom:9px;border-bottom:1px solid var(--ms-soft)}.memory-subpanel header svg{color:var(--ms-accent)}.boundary-list{display:grid;gap:0}.boundary-list>div{display:grid;grid-template-columns:88px minmax(0,1fr);gap:8px;padding:7px 0;border-bottom:1px solid var(--ms-soft);font-size:9px}.boundary-list>div:last-child{border-bottom:0}.boundary-list span{color:var(--ms-muted)}.boundary-list b{font-weight:600;color:var(--ms-secondary)}.boundary-caption{margin:8px 0;color:var(--ms-accent);font-size:11px;text-align:center}.risk-grid{margin-top:8px}.risk-row{display:flex;justify-content:space-between;gap:8px;padding:10px 0;border-bottom:1px solid var(--ms-soft)}.risk-row>div{min-width:0}.risk-row strong{display:block;font-size:10px}.risk-row code{display:block;margin-top:5px;overflow-wrap:anywhere;color:var(--ms-muted);font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:9px}.risk-row>span{flex:0 0 auto;align-self:flex-start;padding:3px 5px;border-radius:4px;background:#fff0ed;color:#bd5145;font-size:8px}.risk-row>span.fixed{background:#edf8f1;color:#298254}.memory-secondary{margin-top:9px;padding:7px 9px;border-color:var(--ms-line);background:var(--ms-surface);color:var(--ms-accent);font-size:10px}.judge-panel{min-width:0}.judge-item{display:flex;justify-content:space-between;gap:8px;width:100%;padding:9px 0;border:0;border-bottom:1px solid var(--ms-soft);background:transparent;color:var(--ms-secondary);font:inherit;font-size:9px;text-align:left;cursor:pointer}.judge-item:hover{color:var(--ms-accent)}.judge-result{display:grid;gap:3px;margin-top:9px;padding:8px;border:1px solid var(--ms-accent-line);border-radius:5px;background:var(--ms-accent-soft);font-size:9px}.judge-result span{color:var(--ms-accent)}.judge-note{margin:9px 0 0;color:var(--ms-muted);font-size:9px;line-height:1.5}.snapshot-panel{margin-top:8px}.snapshot-total{color:var(--ms-accent)!important;font-variant-numeric:tabular-nums}.snapshot-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;margin-top:9px}.snapshot-grid>div{min-width:0;padding:8px;border:1px solid var(--ms-soft);border-radius:5px;background:var(--ms-subtle)}.snapshot-grid span,.snapshot-grid small{display:block;color:var(--ms-muted);font-size:8px}.snapshot-grid b{display:block;margin:4px 0;overflow-wrap:anywhere;color:var(--ms-secondary);font-size:9px}.snapshot-grid small{font-variant-numeric:tabular-nums}.snapshot-grid .state-snapshot{border-color:var(--ms-accent-line);background:var(--ms-accent-soft)}.memory-inspector{display:grid;gap:8px}.inspector-card{padding:10px}.inspector-card header{padding-bottom:8px;border-bottom:1px solid var(--ms-soft)}.inspector-card p{margin:9px 0 0;color:var(--ms-muted);font-size:9px;line-height:1.45}.inspector-meter{height:5px;margin-top:11px;border-radius:3px;background:var(--ms-soft);overflow:hidden}.inspector-meter i{display:block;height:100%;background:var(--ms-accent)}.inspector-meter i.budget-meter{background:#b56b10}.inspector-line{display:flex;justify-content:space-between;margin-top:7px;color:var(--ms-muted);font-size:9px}.inspector-line b{color:var(--ms-secondary)}.inspector-action{margin-top:9px;padding:6px 8px;border-color:var(--ms-line);background:var(--ms-surface);color:var(--ms-accent);font-size:9px}.checkpoint-lines{display:grid;gap:7px;margin-top:9px;color:var(--ms-muted);font-size:9px}.checkpoint-lines b{display:inline-block;width:45px;color:var(--ms-secondary)}.event-lines{display:grid;gap:8px;margin-top:9px}.event-lines>div{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:2px 7px;font-size:9px}.event-lines b{color:var(--ms-secondary)}.event-lines span{color:var(--ms-muted)}.event-lines small{grid-column:2;grid-row:1 / span 2;color:var(--ms-muted);font-size:8px}.memory-migrate-button{width:100%;min-height:32px}.generic-memory-view{display:grid;gap:8px}.memory-view-intro{display:flex;gap:10px;align-items:flex-start;padding:14px;border:1px solid var(--ms-line);border-radius:7px;background:var(--ms-surface)}.memory-view-intro svg{flex:0 0 auto;color:var(--ms-accent)}.memory-view-intro h2{margin:0;font-size:14px}.memory-view-intro p{margin:5px 0 0;color:var(--ms-muted);font-size:10px}.memory-generic-grid{display:grid;gap:6px;padding:11px;border:1px solid var(--ms-line);border-radius:7px;background:var(--ms-surface)}.memory-generic-row{display:grid;grid-template-columns:minmax(130px,.8fr) minmax(0,1fr) auto;gap:10px;padding:9px 0;border-bottom:1px solid var(--ms-soft);font-size:10px}.memory-generic-row:last-child{border-bottom:0}.memory-generic-row span{color:var(--ms-muted)}.memory-generic-row b{color:var(--ms-accent)}.memory-selection-strip{display:flex;gap:10px;align-items:center;margin-top:8px;padding:8px 10px;border:1px solid var(--ms-accent-line);border-radius:6px;background:var(--ms-accent-soft);color:var(--ms-secondary);font-size:9px}.memory-selection-strip span:nth-child(2){min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.memory-selection-strip button{margin-left:auto;border:0;background:transparent;color:var(--ms-secondary);cursor:pointer}.memory-toast{position:fixed;right:18px;bottom:18px;z-index:10;display:flex;align-items:center;gap:6px;padding:9px 11px;border:1px solid var(--ms-line);border-radius:6px;background:var(--ms-surface);box-shadow:0 5px 18px rgb(34 45 64 / 12%);font-size:10px}
@media (max-width:1220px){.memory-workbench{grid-template-columns:220px minmax(0,1fr)}.memory-inspector{grid-column:1 / -1;grid-template-columns:repeat(4,minmax(0,1fr))}.memory-migrate-button{align-self:stretch}.event-card{grid-column:auto}}
@media (max-width:900px){.memory-page-heading{flex-direction:column}.memory-heading-actions{width:100%}.memory-workbench{grid-template-columns:minmax(0,1fr)}.memory-record-panel{display:block}.memory-inspector{grid-column:auto;grid-template-columns:repeat(2,minmax(0,1fr))}.memory-center-panel{order:2}.memory-record-panel{order:1}.memory-inspector{order:3}.memory-record-list{height:300px}.snapshot-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:600px){.memory-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.memory-kpis>div:last-child{grid-column:1 / -1}.memory-heading-actions{align-items:stretch}.memory-rule{flex:1}.memory-primary{flex:0 0 auto}.boundary-grid,.risk-grid,.memory-inspector{grid-template-columns:minmax(0,1fr)}.snapshot-grid{grid-template-columns:minmax(0,1fr)}.memory-generic-row{grid-template-columns:minmax(0,1fr) auto}.memory-generic-row span{grid-column:1 / -1}.memory-selection-strip{align-items:flex-start;flex-wrap:wrap}.memory-selection-strip span:nth-child(2){flex-basis:100%}}
@media (prefers-reduced-motion:reduce){.memory-state-page *{transition:none!important}}
</style>
