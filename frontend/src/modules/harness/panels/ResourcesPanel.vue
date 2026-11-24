<script setup>
import { inject } from 'vue'
import { HARNESS_SHELL, HARNESS_RESOURCES } from '../context'
import { harnessApprovalAuditUrl } from '../../governance/api.js'
import { ShieldCheck, X } from 'lucide-vue-next'

const ctxShell = inject(HARNESS_SHELL)
const ctxResources = inject(HARNESS_RESOURCES)

const { activeSection, props } = ctxShell
const { approvalBusy, approvalDetail, approvalNotifications, approvalRows, approvalSelection, decideApproval, decideApprovalBatch, formatWorkerSeen, loadApprovalNotifications, loadMachineErrors, machineBusy, machineErrorWorker, machineErrors, machineErrorsBusy, machineErrorsError, machineRows, notificationsBusy, notificationsError, openApprovalDetail, openRejectDialog, refreshResourceData, rejectDialog, rejectReason, resourceConnected, submitRejectApproval, toggleMachineDrain } = ctxResources
</script>

<template>



        <section v-if="['machines', 'approvals'].includes(activeSection)" class="resource-page">
          <div class="release-toolbar"><div><h2>{{ activeSection === 'machines' ? '机器与运行时' : '待审批' }}</h2></div><button class="button button-subtle" @click="refreshResourceData">刷新状态</button></div>
          <section class="harness-panel resource-table-panel"><div class="harness-panel-heading"><div><h3>{{ activeSection === 'machines' ? '运行时节点' : '审批队列' }}</h3></div><div v-if="activeSection === 'approvals'" class="harness-detail-actions"><button class="button button-subtle" type="button" :disabled="approvalBusy || !approvalSelection.length" @click="decideApprovalBatch('approved')">批量批准 ({{ approvalSelection.length }})</button><button class="button button-subtle" type="button" :disabled="approvalBusy || !approvalSelection.length" @click="decideApprovalBatch('rejected')">批量拒绝</button><a class="button button-subtle" :href="harnessApprovalAuditUrl(props.apiBase)" download>导出审计</a></div></div><div v-if="activeSection === 'machines' && machineRows.length" class="resource-table"><div class="resource-table-head workspace-cols"><span>Worker</span><span>进程</span><span>最近心跳</span><span>当前运行</span><span>容量</span><span>状态</span><span>错误</span></div><div v-for="row in machineRows" :key="row.worker_id" class="resource-row workspace-cols"><span><strong>{{ row.worker_id }}</strong></span><span>{{ row.process_id }}</span><span>{{ formatWorkerSeen(row.last_seen) }}</span><span>{{ row.current_run_id || '空闲' }}</span><span>{{ row.capacity ?? 1 }}</span><span>{{ row.state === 'draining' ? '排空中' : row.state === 'offline' ? '离线' : row.current_run_id ? '运行中' : '在线' }}</span><span><button class="text-action" :disabled="machineErrorsBusy" @click="loadMachineErrors(row.worker_id)">错误日志</button><button class="text-action" :disabled="machineBusy === row.worker_id" @click="toggleMachineDrain(row)">{{ machineBusy === row.worker_id ? '处理中…' : row.state === 'draining' ? '恢复' : '排空' }}</button></span></div></div><div v-else-if="activeSection === 'approvals' && approvalRows.length" class="resource-table"><div class="resource-table-head workspace-cols"><span>选择</span><span>请求</span><span>工具</span><span>运行</span><span>风险</span><span>决定</span></div><div v-for="row in approvalRows" :key="row.request_id" class="resource-row workspace-cols"><span><input type="checkbox" :value="row.request_id" v-model="approvalSelection" :disabled="row.status !== 'pending'" /></span><span><strong>{{ row.request_id }}</strong><small>{{ row.detail }}</small></span><span>{{ row.tool }}</span><span>{{ row.run_id }}</span><span>{{ row.risk }}</span><span><button v-if="row.status === 'pending'" class="text-action" :disabled="approvalBusy" @click="decideApproval(row, 'approved')">批准</button><button v-if="row.status === 'pending'" class="text-action" :disabled="approvalBusy" @click="openRejectDialog(row)">拒绝</button><span v-else>{{ row.status }}</span><button class="text-action" @click="openApprovalDetail(row)">详情</button></span></div></div><div v-else class="release-empty"><span>当前没有记录</span></div></section>
          <section v-if="activeSection === 'machines'" class="harness-panel resource-table-panel"><div class="harness-panel-heading"><div><h3>节点错误日志</h3><p>{{ machineErrorWorker ? machineErrorWorker + ' 的失败运行' : '选择节点查看失败运行与错误事件' }}</p></div></div><p v-if="machineErrorsError" role="alert">{{ machineErrorsError }}</p><div v-if="machineErrors.length" class="release-history-list"><template v-for="item in machineErrors" :key="item.run_id"><div class="release-history-row"><span>{{ item.finished_at || item.created_at || '—' }}</span><strong>{{ item.run_id }}</strong><span>{{ item.error }}</span><b>{{ item.status }}</b><code>{{ item.events.length }} 条错误事件</code></div><div v-if="item.events.length" class="resource-table"><div v-for="event in item.events" :key="event.event_id" class="resource-row"><span>{{ event.created_at }}</span><span>{{ event.tool || '—' }}</span><span>{{ event.content || '（无内容）' }}</span></div></div></template></div><div v-else class="release-empty"><span>{{ machineErrorWorker ? '该节点没有失败运行' : '尚未选择节点' }}</span></div></section>
          <section v-if="activeSection === 'approvals'" class="harness-panel resource-table-panel"><div class="harness-panel-heading"><div><h3>审批通知</h3><p>{{ approvalNotifications.length }} 条通知记录 · 审批决定后产生</p></div><button class="button button-subtle" :disabled="notificationsBusy" @click="loadApprovalNotifications">{{ notificationsBusy ? '读取中…' : '刷新通知' }}</button></div><p v-if="notificationsError" role="alert">{{ notificationsError }}</p><div v-if="approvalNotifications.length" class="resource-table"><div class="resource-table-head workspace-cols"><span>通知 / 时间</span><span>审批请求</span><span>事件</span><span>通道</span><span>状态</span></div><div v-for="row in approvalNotifications" :key="row.notification_id" class="resource-row workspace-cols"><span><strong>{{ row.notification_id }}</strong><small>{{ row.created_at }}</small></span><span>{{ row.request_id }}</span><span>{{ row.event }}</span><span>{{ row.channel }}</span><span>{{ row.status }}<small v-if="row.detail">{{ row.detail }}</small></span></div></div><div v-else class="release-empty"><span>暂无审批通知</span></div></section>
          <footer class="page-footer"><span><i class="footer-health demo-health"></i>{{ resourceConnected ? '已连接治理 API' : '未连接治理 API' }}</span></footer>
        </section>
      <div v-if="approvalDetail" class="modal-backdrop" @click.self="approvalDetail = null">
        <section class="dialog run-create-dialog" role="dialog" aria-modal="true" aria-labelledby="approval-detail-title">
          <div class="dialog-heading"><div class="dialog-symbol"><ShieldCheck :size="19" /></div><button class="icon-button" type="button" aria-label="关闭审批详情" @click="approvalDetail = null"><X :size="18" /></button></div>
          <h2 id="approval-detail-title">{{ approvalDetail.request_id }}</h2>
          <p>工具 {{ approvalDetail.tool }} · 风险 {{ approvalDetail.risk }} · 状态 {{ approvalDetail.status }}</p>
          <p>运行 {{ approvalDetail.run_id }} · 创建 {{ approvalDetail.created_at || '—' }} · 超时 {{ approvalDetail.expires_at || '—' }}</p>
          <p>{{ approvalDetail.detail || '无补充说明' }}</p>
          <p v-if="approvalDetail.decided_at">决定于 {{ approvalDetail.decided_at }} · 操作者 {{ approvalDetail.operator || '—' }} · 理由 {{ approvalDetail.reason || '—' }}</p>
          <div class="dialog-actions"><button class="secondary-button" type="button" @click="approvalDetail = null">关闭</button><button v-if="approvalDetail.status === 'pending'" class="primary-button" type="button" :disabled="approvalBusy" @click="decideApproval(approvalDetail, 'approved'); approvalDetail = null">批准</button><button v-if="approvalDetail.status === 'pending'" class="secondary-button" type="button" @click="openRejectDialog(approvalDetail); approvalDetail = null">拒绝</button></div>
        </section>
      </div>
      <div v-if="rejectDialog" class="modal-backdrop" @click.self="rejectDialog = null">
        <section class="dialog run-create-dialog" role="dialog" aria-modal="true" aria-labelledby="reject-approval-title">
          <div class="dialog-heading"><div class="dialog-symbol"><ShieldCheck :size="19" /></div><button class="icon-button" type="button" aria-label="关闭拒绝理由" @click="rejectDialog = null"><X :size="18" /></button></div>
          <h2 id="reject-approval-title">拒绝审批</h2>
          <p>{{ rejectDialog.request_id }} · {{ rejectDialog.tool }}</p>
          <label class="run-create-field"><span>拒绝理由</span><textarea v-model="rejectReason" rows="3" placeholder="说明拒绝原因，会写入审计记录"></textarea></label>
          <div class="dialog-actions"><button class="secondary-button" type="button" @click="rejectDialog = null">取消</button><button class="primary-button" type="button" @click="submitRejectApproval">确认拒绝</button></div>
        </section>
      </div>



</template>
