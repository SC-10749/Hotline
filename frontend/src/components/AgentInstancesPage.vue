<script setup>
import { computed, ref } from 'vue'
import { Activity, AlertTriangle, Archive, Bot, CheckCircle2, ChevronRight, Clock3, Cloud, Database, Gauge, Layers3, Pause, Play, Plus, Search, ShieldCheck, SlidersHorizontal, Trash2, Wrench, X } from 'lucide-vue-next'

const emit = defineEmits(['back'])

const instances = ref([
  { id: 'research-agent', status: 'running', model: 'deepseek-v4.1', region: 'cn-hangzhou', sessions: 42, version: 'v47', updated: '12 分钟前', role: 'agent-research-47', owner: 'zhang.wei', description: '竞品与行业研究，长任务为主，允许子 Agent 委派做并行抓取。', concurrency: '42 / 32', visibility: '全部成员' },
  { id: 'codegen-agent', status: 'running', model: 'claude-3.5-sonnet', region: 'cn-hangzhou', sessions: 18, version: 'v12', updated: '34 分钟前', role: 'agent-codegen-12', owner: 'li.na', description: '代码生成与审查，绑定仓库工作空间。', concurrency: '18 / 32', visibility: '研发成员' },
  { id: 'ops-agent', status: 'degraded', model: 'deepseek-v4.1', region: 'cn-hangzhou', sessions: 9, version: 'v8', updated: '3 分钟前', role: 'agent-ops-08', owner: 'wang.qiang', description: '基础设施运维与告警处理。', concurrency: '9 / 24', visibility: '运维成员' },
  { id: 'data-agent', status: 'running', model: 'deepseek-v4.1', region: 'cn-hangzhou', sessions: 26, version: 'v5', updated: '1 小时前', role: 'agent-data-05', owner: 'chen.yu', description: '数据分析与报表生成。', concurrency: '26 / 32', visibility: '全部成员' },
  { id: 'writer-agent', status: 'running', model: 'deepseek-v4.1', region: 'cn-hangzhou', sessions: 31, version: 'v22', updated: '6 分钟前', role: 'agent-writer-22', owner: 'zhang.wei', description: '内容写作和多渠道发布。', concurrency: '31 / 32', visibility: '内容成员' },
  { id: 'support-agent', status: 'running', model: 'deepseek-v4.1-flash', region: 'cn-hangzhou', sessions: 52, version: 'v16', updated: '刚刚', role: 'agent-support-16', owner: 'li.na', description: '客服分流与知识库问答。', concurrency: '52 / 64', visibility: '客服成员' },
  { id: 'legacy-scraper', status: 'deleted', model: 'deepseek-v3.2', region: 'cn-hangzhou', sessions: 0, version: 'v9', updated: '5 天前', role: 'agent-legacy-09', owner: 'chen.yu', description: '旧版抓取实例，资源已释放。', concurrency: '0 / 16', visibility: '管理员' },
])

const statusLabels = { running: '运行中', stopped: '已停止', degraded: '异常', draft: '草稿', deleted: '已删除' }
const statusCounts = computed(() => Object.fromEntries(Object.keys(statusLabels).map((key) => [key, instances.value.filter((item) => item.status === key).length])))
const search = ref('')
const filter = ref('all')
const selectedId = ref('research-agent')
const detailTab = ref('overview')
const toast = ref('')
const selected = computed(() => instances.value.find((item) => item.id === selectedId.value) || instances.value[0])
const visibleInstances = computed(() => instances.value.filter((item) => (filter.value === 'all' || item.status === filter.value) && item.id.toLowerCase().includes(search.value.toLowerCase())))
const tabs = [
  ['overview', '概览'], ['capabilities', '能力装配'], ['versions', '版本'], ['health', '健康'], ['security', '隔离与安全'], ['scaling', '扩缩容'], ['usage', '用量与预算'],
]

function showToast(message) {
  toast.value = message
  window.setTimeout(() => { toast.value = '' }, 2200)
}

function setStatus(status) {
  if (!selected.value) return
  selected.value.status = status
  showToast(`${selected.value.id} 已${statusLabels[status]}`)
}

function createInstance() {
  const id = `new-agent-${instances.value.length + 1}`
  instances.value.unshift({ id, status: 'draft', model: 'deepseek-v4.1', region: 'cn-hangzhou', sessions: 0, version: 'v1', updated: '刚刚', role: `agent-${id}`, owner: '当前用户', description: '待配置的智能体实例。', concurrency: '0 / 16', visibility: '管理员' })
  selectedId.value = id
  filter.value = 'all'
  showToast('已创建实例草稿')
}
</script>

<template>
  <section class="instance-registry" aria-label="智能体实例注册表">
    <header class="instance-header">
      <div class="instance-brand"><span class="instance-brand-mark">A</span><div><h1>智能体实例</h1><p>Instance Registry · 实例即产品</p></div></div>
      <div class="instance-tenant"><span>租户</span><strong>生产 · acme-cn</strong><span class="instance-capacity">实例容量 <b>7 / 16</b></span><span>admin · 全部可见</span></div>
      <button class="instance-primary" type="button" @click="createInstance"><Plus :size="16" />新建实例</button>
      <button class="instance-close" type="button" aria-label="返回" title="返回" @click="emit('back')"><X :size="18" /></button>
    </header>

    <div class="instance-kpis">
      <button class="instance-kpi" type="button" @click="filter = 'running'"><span>活跃实例 <i>运行中</i></span><strong>{{ statusCounts.running }} <small>/ {{ instances.length }}</small></strong><em>0 已停止 · {{ statusCounts.degraded }} 异常 · {{ statusCounts.draft }} 草稿 · {{ statusCounts.deleted }} 已删除</em><Activity :size="22" /></button>
      <button class="instance-kpi" type="button"><span>活跃会话 <i>实时</i></span><strong>178 <small>个</small></strong><em>峰值 221 · 每实例槽位上限 32</em><Cloud :size="22" /></button>
      <button class="instance-kpi" type="button"><span>实例错误率 <i>1h</i></span><strong>0.44 <small>%</small></strong><em>1 个实例越过 1% 告警线</em><AlertTriangle :size="22" /></button>
      <button class="instance-kpi" type="button"><span>版本发布 <i>本周</i></span><strong>5 <small>次 · 1 回滚</small></strong><em>2 个灰度中 · 全部为不可变快照</em><Layers3 :size="22" /></button>
    </div>

    <div class="instance-workspace">
      <aside class="instance-list-panel">
        <div class="instance-panel-title"><h2>实例 <small>{{ instances.length }}</small></h2><button type="button" @click="createInstance"><Plus :size="15" />新建</button></div>
        <label class="instance-search"><Search :size="15" /><input v-model="search" placeholder="搜索实例, ID" /></label>
        <div class="instance-filter-tabs" role="tablist">
          <button v-for="item in [['all','全部'], ...Object.entries(statusLabels)]" :key="item[0]" type="button" :class="{ active: filter === item[0] }" @click="filter = item[0]"><span>{{ item[1] }}</span><b>{{ item[0] === 'all' ? instances.length : statusCounts[item[0]] }}</b></button>
        </div>
        <div class="instance-list">
          <button v-for="item in visibleInstances" :key="item.id" type="button" class="instance-row" :class="{ selected: item.id === selectedId }" @click="selectedId = item.id">
            <span class="instance-row-main"><strong>{{ item.id }}</strong><i :class="item.status">{{ statusLabels[item.status] }}</i></span>
            <span class="instance-row-meta">{{ item.model }} · {{ item.region }} · {{ item.sessions }} 会话</span><span class="instance-row-foot">{{ item.version }} <span>{{ item.updated }}</span></span>
          </button>
          <p v-if="!visibleInstances.length" class="instance-empty">没有匹配的实例</p>
        </div>
        <div class="instance-list-foot"><span>租户实例配额</span><strong>7 / 16</strong><small>运行 {{ statusCounts.running }} · 异常 {{ statusCounts.degraded }} · 停止 {{ statusCounts.stopped }} · 草稿 {{ statusCounts.draft }} · 删除 {{ statusCounts.deleted }}</small></div>
      </aside>

      <main class="instance-detail-panel">
        <header class="instance-detail-head"><div><h2>{{ selected.id }} <i :class="selected.status">{{ statusLabels[selected.status] }}</i></h2><p>{{ selected.model }} · {{ selected.region }} · {{ selected.version }} · {{ selected.role }}</p></div><div class="instance-detail-actions"><button v-if="selected.status === 'running'" type="button" @click="setStatus('stopped')"><Pause :size="14" />停止</button><button v-else type="button" @click="setStatus('running')"><Play :size="14" />启动</button><button type="button" @click="setStatus('draft')">保存草稿</button><button class="danger" type="button" @click="setStatus('deleted')"><Trash2 :size="14" />删除</button></div></header>
        <nav class="instance-detail-tabs" aria-label="实例详情"><button v-for="tab in tabs" :key="tab[0]" type="button" :class="{ active: detailTab === tab[0] }" @click="detailTab = tab[0]">{{ tab[1] }}</button></nav>

        <div v-if="detailTab === 'overview'" class="instance-detail-body">
          <section class="instance-state-note"><div><strong>生命周期状态机</strong><p>Activate 管注册准入 · Start/Stop 管底层基础设施 · Delete 软删保留 30 天</p></div><span><b>当前：{{ statusLabels[selected.status] }}</b><small>注册已激活 · 软删后可恢复</small></span></section>
          <section class="instance-section"><div class="instance-section-title"><h3>配置摘要</h3><span>随版本快照固化</span></div><div class="instance-info-grid"><div><small>模型</small><strong>{{ selected.model }}</strong><em>2026-02-11</em></div><div><small>端点版本</small><strong>{{ selected.version }}</strong></div><div><small>并发槽位</small><strong>{{ selected.concurrency }}</strong><em>超出 10 · 走排队</em></div><div><small>负责人</small><strong>{{ selected.owner }}</strong></div><div><small>创建时间</small><strong>2025-03-14 10:22</strong></div><div><small>可见性</small><strong>{{ selected.visibility }}</strong></div></div><div class="instance-description"><small>实例说明</small><p>{{ selected.description }}</p></div><div class="instance-meta-line"><span>实例 ID <b>agt_{{ selected.id.replaceAll('-', '_') }}</b></span><span>档位 <b>标准</b></span><span>最近更新 <b>{{ selected.updated }}</b></span></div></section>
          <section class="instance-section"><div class="instance-section-title"><h3>能力装配摘要</h3><span>详情见「能力装配」</span></div><div class="instance-capability-grid"><div><Wrench :size="15" /><span>工具 <b>4 个</b></span></div><div><Bot :size="15" /><span>技能 <b>2 个</b></span></div><div><Database :size="15" /><span>MCP 服务器 <b>2 个</b></span></div><div><Layers3 :size="15" /><span>子 Agent 委派 <b>2 个</b></span></div><div><Gauge :size="15" /><span>上下文预算 <b>60%</b></span></div><div><Archive :size="15" /><span>记忆作用域 <b>inst</b></span></div></div></section>
          <section class="instance-section"><div class="instance-section-title"><h3>最近会话</h3><span>按 session_id 隔离 · 粘性路由</span></div><div class="instance-table"><div class="instance-table-row instance-table-head"><span>会话</span><span>入口</span><span>版本</span><span>时长</span><span>状态</span><span>成本</span></div><div v-for="row in [['sess_8f3a2c','slack #research','v47','24m','成功','$1.28'],['sess_2b9d81','api /v1/runs','v47','11m','成功','$0.84'],['sess_77bdc0','cron 每日 09:00','v47','38m','等待审批','$2.07']]" :key="row[0]" class="instance-table-row"><span>{{ row[0] }}</span><span>{{ row[1] }}</span><span>{{ row[2] }}</span><span>{{ row[3] }}</span><span class="ok">{{ row[4] }}</span><span>{{ row[5] }}</span></div></div></section>
        </div>
        <div v-else class="instance-placeholder"><SlidersHorizontal :size="28" /><h3>{{ tabs.find((tab) => tab[0] === detailTab)?.[1] }}</h3><p>此配置视图已预留，当前使用实例快照数据展示。</p></div>
      </main>

      <aside class="instance-console"><div class="instance-console-head"><h2>实例控制台</h2><p>按当前状态可执行的动作</p></div><div class="instance-console-body"><div class="console-status"><span>生命周期</span><strong><i :class="selected.status"></i>{{ statusLabels[selected.status] }}</strong></div><button class="console-action" type="button" @click="setStatus(selected.status === 'running' ? 'stopped' : 'running')"><component :is="selected.status === 'running' ? Pause : Play" :size="16" /><span>{{ selected.status === 'running' ? 'Stop · 停止' : 'Start · 启动' }}<small>{{ selected.status === 'running' ? '释放基础设施，保留注册' : '启动当前版本实例' }}</small></span></button><button class="console-action" type="button" @click="setStatus('deleted')"><Trash2 :size="16" /><span>Delete · 软删除<small>30 天恢复窗口</small></span></button><button class="console-action disabled" type="button" disabled><Archive :size="16" /><span>Permanently delete<small>需先软删除</small></span></button><div class="console-divider"><span>端点与版本</span><b>单版本</b></div><div class="console-endpoint">agent.{{ selected.id }}.svc/v1 <strong>{{ selected.version }}</strong><em>100%</em></div><div class="console-buttons"><button type="button" @click="showToast('版本管理暂使用演示数据')">版本管理</button><button type="button" @click="showToast('已切换到上一版本')">回滚上一版</button></div><div class="console-checks"><div><CheckCircle2 :size="15" /><span>健康探针<small>live /health 200 · 1.8ms</small></span></div><div><ShieldCheck :size="15" /><span>鉴权<small>错误率 0.18% · 心跳 12s 前</small></span></div><div><Gauge :size="15" /><span>容量与隔离<small>auto 副本 4 / 6 · 空闲回收 15 分钟</small></span></div></div></div></aside>
    </div>

    <section class="instance-audit"><div class="instance-section-title"><h2>生命周期审计 <small>最近 8 条</small></h2><span>保留 90 天 · 不可篡改</span></div><div class="audit-table"><div class="audit-row audit-head"><span>时间</span><span>操作</span><span>实例</span><span>版本</span><span>操作人</span><span>结果</span></div><div v-for="row in [['今天 14:02','启动','ops-agent','v8','wang.qiang','成功'],['今天 11:48','部署','writer-agent','v22','zhang.wei','灰度 10%'],['今天 10:15','配置','support-agent','v16','li.na','成功'],['昨天 19:30','回滚','data-agent','v4 → v5','chen.yu','成功'],['昨天 16:22','停止','qa-agent','v3','sun.lei','成功']]" :key="row.join('-')" class="audit-row"><span>{{ row[0] }}</span><span>{{ row[1] }}</span><span>{{ row[2] }}</span><span>{{ row[3] }}</span><span>{{ row[4] }}</span><span class="ok">{{ row[5] }}</span></div></div></section>
    <Transition name="toast"><div v-if="toast" class="instance-toast" role="status"><CheckCircle2 :size="16" />{{ toast }}</div></Transition>
  </section>
</template>
