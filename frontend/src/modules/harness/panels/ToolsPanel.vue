<script setup>
import { inject } from 'vue'
import { HARNESS_SHELL, HARNESS_TOOLS } from '../context'
import { Plus, Wrench, X } from 'lucide-vue-next'

const ctxShell = inject(HARNESS_SHELL)
const ctxTools = inject(HARNESS_TOOLS)

const { activeSection } = ctxShell

const { callSelectedMcpTool, editingTool, harnessMcpServers, mcpCallArgs, mcpCallBusy, mcpCallError, mcpCallResult, mcpServersError, mcpToolPick, openToolDetails, openToolDialog, refreshToolData, saveTool, showToolDialog, testToolConnection, toolDraft, toolError, toolRows, toolSaving, toolSchemaText, toolTestBusy, toolTestResults, toolsConnected, toolsError } = ctxTools
</script>

<template>



        <section v-if="activeSection === 'tools'" class="resource-page">
          <p v-if="toolsError" role="alert">{{ toolsError }}</p>
          <section class="harness-panel resource-table-panel">
            <div class="harness-panel-heading"><div><h3>工具目录</h3><p>{{ toolRows.length }} 条记录 · {{ toolsConnected ? '已连接工具目录' : '未连接工具目录' }}</p></div><div class="harness-panel-actions"><button class="button button-subtle" @click="refreshToolData">刷新目录</button><button class="button button-primary" @click="openToolDialog"><Plus :size="14" />登记工具</button></div></div>
            <div v-if="toolRows.length" class="ui-table ui-cols-generic">
              <div class="ui-table-head"><span>工具 / 来源</span><span>范围</span><span>风险</span><span>登记状态</span><span></span></div>
              <div v-for="row in toolRows" :key="row.tool_id" class="ui-row"><span><strong>{{ row.name }}</strong><small>{{ row.source }}</small><small v-if="toolTestResults[row.tool_id]" :class="toolTestResults[row.tool_id].ok ? '' : 'stat-warn'">{{ toolTestResults[row.tool_id].ok ? '连接正常' : toolTestResults[row.tool_id].message }}</small></span><span>{{ row.scope }}</span><span>{{ row.risk }}</span><span>{{ row.status }}</span><span><button class="text-action" :disabled="toolTestBusy === row.tool_id || !toolsConnected" :title="toolsConnected ? '测试工具连接' : '未连接工具目录'" @click="testToolConnection(row)">{{ toolTestBusy === row.tool_id ? '测试中…' : '连接测试' }}</button><button class="text-action" @click="openToolDetails(row)">查看</button></span></div>
            </div>
            <div v-else class="ui-empty"><span>尚未登记工具</span><button class="text-action" @click="openToolDialog">登记第一个工具</button></div>
          </section>
          <section class="harness-panel resource-table-panel">
            <div class="harness-panel-heading"><div><h3>MCP 连接器</h3><p>{{ harnessMcpServers.length }} 个连接器 · {{ toolsConnected ? '已连接目录' : '未连接工具目录' }}</p></div></div>
            <p v-if="mcpServersError" role="alert">{{ mcpServersError }}</p>
            <div v-if="harnessMcpServers.length" class="ui-table ui-cols-mcp">
              <div class="ui-table-head"><span>连接器 / 来源</span><span>状态</span><span>已发现工具</span><span>工具编号</span></div>
              <div v-for="row in harnessMcpServers" :key="row.tool_id" class="ui-row"><span><strong>{{ row.name }}</strong><small>{{ row.source }}</small><small v-if="row.message" class="stat-warn">{{ row.message }}</small></span><span>{{ row.status || '未记录状态' }}</span><span>{{ (row.tools || []).length ? row.tools.join('、') : '未发现工具' }}</span><span>{{ row.tool_id }}</span></div>
            </div>
            <div v-if="harnessMcpServers.length" class="harness-detail-block"><strong>工具调用</strong><div class="harness-detail-actions"><select v-model="mcpToolPick"><option value="">选择工具</option><template v-for="row in harnessMcpServers" :key="`call-${row.tool_id}`"><option v-for="tool in row.tools || []" :key="tool" :value="`${row.tool_id}::${tool}`">{{ row.name }} · {{ tool }}</option></template></select><input v-model="mcpCallArgs" placeholder='调用参数 JSON，例如 {"query":"测试"}' /><button class="button button-subtle" type="button" :disabled="mcpCallBusy || !mcpToolPick" @click="callSelectedMcpTool">{{ mcpCallBusy ? '调用中…' : '调用工具' }}</button></div><p v-if="mcpCallError" role="alert">{{ mcpCallError }}</p><pre v-if="mcpCallResult" class="execution-text">{{ JSON.stringify(mcpCallResult, null, 2) }}</pre></div>
            <div v-else class="ui-empty"><span>暂无 MCP 连接器</span></div>
          </section>
        </section>
      <div v-if="showToolDialog" class="modal-backdrop" @click.self="!toolSaving && (showToolDialog = false)">
        <form class="dialog run-create-dialog" role="dialog" aria-modal="true" aria-labelledby="tool-editor-title" @submit.prevent="saveTool">
          <div class="dialog-heading"><div class="dialog-symbol"><Wrench :size="19" /></div><button class="icon-button" type="button" :disabled="toolSaving" aria-label="关闭工具配置" @click="showToolDialog = false"><X :size="18" /></button></div>
          <h2 id="tool-editor-title">{{ editingTool ? '工具详情与编辑' : '登记工具' }}</h2>
          <p v-if="editingTool">{{ editingTool.tool_id }} · 修订 {{ editingTool.revision }} · 更新时间 {{ editingTool.updated_at }}</p>
          <label class="run-create-field"><span>工具名称</span><input v-model="toolDraft.name" required maxlength="160" :disabled="toolSaving" /></label>
          <label class="run-create-field"><span>来源标识</span><input v-model="toolDraft.source" required maxlength="160" :disabled="toolSaving" /></label>
          <label class="run-create-field"><span>权限范围</span><input v-model="toolDraft.scope" required maxlength="500" :disabled="toolSaving" /></label>
          <label class="run-create-field"><span>风险等级</span><select v-model="toolDraft.risk" :disabled="toolSaving"><option value="low">低</option><option value="medium">中</option><option value="high">高</option></select></label>
          <label class="run-create-field"><span>审批策略</span><select v-model="toolDraft.approval_policy" :disabled="toolSaving"><option value="risk-based">按风险等级审批</option><option value="always">每次调用审批</option></select></label>
          <label class="run-create-field"><span>登记状态</span><input v-model="toolDraft.status" required maxlength="40" :disabled="toolSaving" /></label>
          <label class="run-create-field"><span>说明</span><textarea v-model="toolDraft.description" rows="2" maxlength="2000" :disabled="toolSaving"></textarea></label>
          <label class="run-create-field"><span>参数 Schema JSON</span><textarea v-model="toolSchemaText" rows="6" spellcheck="false" :disabled="toolSaving"></textarea></label>
          <p v-if="toolError" role="alert">{{ toolError }}</p>
          <div class="dialog-actions"><button class="secondary-button" type="button" :disabled="toolSaving" @click="showToolDialog = false">取消</button><button class="primary-button" type="submit" :disabled="toolSaving">{{ toolSaving ? '保存中…' : '保存登记配置' }}</button></div>
        </form>
      </div>



</template>
