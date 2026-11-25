<script setup>
import { inject } from 'vue'
import { HARNESS_SHELL, HARNESS_AGENTS, HARNESS_SKILLS } from '../context'
import { Bot, Plus, X } from 'lucide-vue-next'

const ctxShell = inject(HARNESS_SHELL)
const ctxAgents = inject(HARNESS_AGENTS)
const ctxSkills = inject(HARNESS_SKILLS)

const { refreshActiveSection } = ctxShell
const { agentDiff, agentDiffBase, agentDiffBusy, agentDiffError, agentDiffTarget, agentDraft, agentError, agentPolicyText, agentRows, agentRuns, agentRunsBusy, agentRunsError, agentSaving, agentSkillBusy, agentSkillError, agentSkillInput, agentSkillPick, agentStatusBusy, agentVersions, agentVersionsBusy, agentsConnected, agentsError, bindAgentSkill, compareAgentVersions, editingAgent, formatDiffValue, openAgentDetails, openAgentDialog, pendingAgentSkillId, showAgentDialog, submitAgent, toggleAgentStatus, unbindAgentSkill } = ctxAgents
const { harnessSkills } = ctxSkills
</script>

<template>



        <section class="resource-page">
          <p v-if="agentsError" role="alert">{{ agentsError }}</p><section class="harness-panel resource-table-panel"><div class="harness-panel-heading"><div><h3>Agent 目录</h3><p>{{ agentRows.length }} 个 Agent · {{ agentsConnected ? '已连接资源目录' : '未连接资源目录' }}</p></div><div class="harness-panel-actions"><button class="button button-subtle" @click="refreshActiveSection">刷新目录</button><button class="button button-primary" @click="openAgentDialog"><Plus :size="14" />新建 Agent</button></div></div><div v-if="agentRows.length" class="ui-table ui-cols-generic"><div class="ui-table-head"><span>名称</span><span>版本</span><span>模型</span><span>启停</span><span>操作</span></div><div v-for="row in agentRows" :key="row.agent_id" class="ui-row"><span><strong>{{ row.name }}</strong><small>{{ row.description || '暂无描述' }} · {{ row.status || '未记录状态' }}</small></span><span>{{ row.version }}</span><span>{{ row.model }}</span><span><span class="ui-status" :class="row.enabled === true ? 'ok' : 'idle'">{{ row.enabled === true ? '启用' : row.enabled === false ? '停用' : '未记录' }}</span></span><span><button class="text-action" :disabled="agentStatusBusy === row.agent_id || !agentsConnected" :title="agentsConnected ? (row.enabled ? '停用该 Agent' : '启用该 Agent') : '未连接资源目录 API'" @click="toggleAgentStatus(row)">{{ agentStatusBusy === row.agent_id ? '处理中…' : row.enabled ? '停用' : '启用' }}</button><button class="text-action" @click="openAgentDetails(row)">查看</button></span></div></div><div v-else class="ui-empty"><span>{{ agentsConnected ? '还没有 Agent 记录' : '未连接资源目录 API' }}</span></div></section>
          <footer class="page-footer"><span><i class="footer-health" :class="agentsConnected ? 'live' : ''"></i>{{ agentsConnected ? '已连接资源目录' : '未连接资源目录 API' }}</span></footer>
        </section>
      <div v-if="showAgentDialog" class="modal-backdrop" @click.self="!agentSaving && (showAgentDialog = false)">
        <form class="dialog run-create-dialog" role="dialog" aria-modal="true" aria-labelledby="agent-create-title" @submit.prevent="submitAgent">
          <div class="dialog-heading"><div class="dialog-symbol"><Bot :size="19" /></div><button class="icon-button" type="button" aria-label="关闭 Agent 配置" :disabled="agentSaving" @click="showAgentDialog = false"><X :size="18" /></button></div>
          <h2 id="agent-create-title">{{ editingAgent ? 'Agent 详情与编辑' : '新建 Agent' }}</h2>
          <p v-if="editingAgent">{{ editingAgent.agent_id }} · 状态 {{ editingAgent.status }} · 修订 {{ editingAgent.revision }} · 更新时间 {{ editingAgent.updated_at }}</p>
          <label class="run-create-field"><span>名称</span><input v-model="agentDraft.name" required maxlength="120" :disabled="agentSaving" /></label>
          <label class="run-create-field"><span>版本标签</span><input v-model="agentDraft.version" required maxlength="40" :disabled="agentSaving" /></label>
          <label class="run-create-field"><span>模型路由</span><input v-model="agentDraft.model" required maxlength="120" :disabled="agentSaving" /></label>
          <label class="run-create-field"><span>说明</span><textarea v-model="agentDraft.description" rows="3" maxlength="500" :disabled="agentSaving"></textarea></label>
          <label class="run-create-field"><span>运行策略 JSON</span><textarea v-model="agentPolicyText" rows="5" spellcheck="false" :disabled="agentSaving"></textarea></label>
          <template v-if="editingAgent">
            <div class="harness-detail-block"><strong>版本历史</strong><p v-if="agentVersionsBusy" role="status">正在读取版本历史…</p><div v-else-if="agentVersions.length" class="harness-detail-rows"><div v-for="item in agentVersions" :key="item.version_id" class="harness-detail-row"><span><strong>{{ item.version }}</strong> · {{ item.enabled ? '启用' : '停用' }} · {{ item.created_at }}</span><code>{{ item.version_id }}</code></div></div><div v-else class="ui-empty"><span>暂无版本快照</span></div><div class="harness-detail-actions"><select v-model="agentDiffBase" :disabled="agentDiffBusy"><option value="">基准版本</option><option v-for="item in agentVersions" :key="item.version_id" :value="item.version_id">{{ item.version }} · {{ item.created_at }}</option></select><select v-model="agentDiffTarget" :disabled="agentDiffBusy"><option value="">对比版本</option><option v-for="item in agentVersions" :key="item.version_id" :value="item.version_id">{{ item.version }} · {{ item.created_at }}</option></select><button class="button button-subtle" type="button" :disabled="agentDiffBusy || !agentDiffBase || !agentDiffTarget" @click="compareAgentVersions">{{ agentDiffBusy ? '比较中…' : '对比版本' }}</button></div><p v-if="agentDiffError" role="alert">{{ agentDiffError }}</p><div v-if="agentDiff" class="harness-detail-rows"><div v-for="item in agentDiff.changed" :key="`changed-${item.field}`" class="harness-detail-row"><span>{{ item.field }}</span><span>{{ formatDiffValue(item.base) }} → {{ formatDiffValue(item.target) }}</span></div><div v-for="item in agentDiff.added" :key="`added-${item.field}-${item.value}`" class="harness-detail-row"><span>新增 {{ item.field }}</span><span>{{ formatDiffValue(item.value) }}</span></div><div v-for="item in agentDiff.removed" :key="`removed-${item.field}-${item.value}`" class="harness-detail-row"><span>移除 {{ item.field }}</span><span>{{ formatDiffValue(item.value) }}</span></div><div v-if="!agentDiff.changed.length && !agentDiff.added.length && !agentDiff.removed.length" class="ui-empty"><span>两个版本没有差异</span></div></div></div>
            <div class="harness-detail-block"><strong>绑定 Skill</strong><div class="harness-detail-rows"><div v-for="skillId in editingAgent.skills || []" :key="skillId" class="harness-detail-row"><code>{{ skillId }}</code><button class="text-action" type="button" :disabled="agentSkillBusy" @click="unbindAgentSkill(skillId)">解绑</button></div><div v-if="!(editingAgent.skills || []).length" class="ui-empty"><span>尚未绑定 Skill</span></div></div><div class="harness-detail-actions"><select v-model="agentSkillPick" :disabled="agentSkillBusy"><option value="">选择已安装 Skill</option><option v-for="item in harnessSkills" :key="item.id" :value="item.id">{{ item.name }} · {{ item.id }}</option></select><input v-model="agentSkillInput" placeholder="或手工输入 skillId" :disabled="agentSkillBusy" /><button class="button button-subtle" type="button" :disabled="agentSkillBusy || !pendingAgentSkillId" @click="bindAgentSkill">{{ agentSkillBusy ? '处理中…' : '绑定 Skill' }}</button></div><p v-if="agentSkillError" role="alert">{{ agentSkillError }}</p></div>
            <div class="harness-detail-block"><strong>关联运行</strong><p v-if="agentRunsBusy" role="status">正在读取关联运行…</p><div v-else-if="agentRuns.length" class="harness-detail-rows"><div v-for="item in agentRuns" :key="item.run_id" class="harness-detail-row"><span><strong>{{ item.run_id }}</strong> · {{ item.status }}</span><span>{{ item.query || '无任务' }} · {{ item.created_at || '—' }}</span></div></div><div v-else class="ui-empty"><span>暂无关联运行</span></div><p v-if="agentRunsError" role="alert">{{ agentRunsError }}</p></div>
          </template>
          <p v-if="agentError" role="alert">{{ agentError }}</p>
          <div class="dialog-actions"><button class="secondary-button" type="button" :disabled="agentSaving" @click="showAgentDialog = false">取消</button><button class="primary-button" type="submit" :disabled="agentSaving">{{ agentSaving ? '保存中…' : editingAgent ? '保存配置' : '创建 Agent' }}</button></div>
        </form>
      </div>

</template>
