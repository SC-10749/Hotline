<script setup>
import { inject } from 'vue'
import { HARNESS_MODELS, HARNESS_SHELL } from '../context'
import { Network, Plus, X } from 'lucide-vue-next'

const ctxShell = inject(HARNESS_SHELL)
const ctxModels = inject(HARNESS_MODELS)

const { activeSection } = ctxShell

const { editingModel, harnessModels, modelDraft, modelError, modelFallbackChain, modelRows, modelSaving, modelTestBusy, modelTestResults, modelsConnected, modelsError, openModelDetails, openModelDialog, refreshModelData, saveModel, showModelDialog, testModelConnection } = ctxModels
</script>

<template>



        <section v-if="activeSection === 'models'" class="resource-page">
          <div class="release-toolbar"><div><h2>模型路由</h2></div><button class="button button-primary" @click="openModelDialog"><Plus :size="14" />登记模型路由</button></div>
          <p v-if="modelsError" role="alert">{{ modelsError }}</p>
          <section class="harness-panel resource-table-panel">
            <div class="harness-panel-heading"><div><h3>模型路由目录</h3><p>{{ modelRows.length }} 条记录 · {{ modelsConnected ? '已连接目录' : '演示数据' }}</p></div><button class="button button-subtle" @click="refreshModelData">刷新目录</button></div>
            <div v-if="modelRows.length" class="resource-table wide-actions">
              <div class="resource-table-head"><span>模型 / 提供商</span><span>路由用途</span><span>备用模型</span><span>登记状态</span><span></span></div>
              <div v-for="row in modelRows" :key="row.model_id" class="resource-row"><span><strong>{{ row.name }}</strong><small>{{ row.provider || '未指定提供商' }}</small><small v-if="modelTestResults[row.model_id]" :class="modelTestResults[row.model_id].ok ? '' : 'stat-warn'">{{ modelTestResults[row.model_id].ok ? '连接正常' : modelTestResults[row.model_id].message }}</small></span><span>{{ row.route }}</span><span>{{ harnessModels.find(item => item.model_id === row.fallback_model_id)?.name || row.fallback_model_id || '无' }}</span><span>{{ row.status }}</span><span><button class="text-action" :disabled="modelTestBusy === row.model_id || !modelsConnected" :title="modelsConnected ? '测试模型路由连接' : '演示数据，未连接模型目录'" @click="testModelConnection(row)">{{ modelTestBusy === row.model_id ? '测试中…' : '连接测试' }}</button><button class="text-action" @click="openModelDetails(row)">查看</button></span></div>
            </div>
            <div v-else class="release-empty"><span>尚未登记模型路由</span><button class="text-action" @click="openModelDialog">登记第一个模型路由</button></div>
          </section>
        </section>
      <div v-if="showModelDialog" class="modal-backdrop" @click.self="!modelSaving && (showModelDialog = false)">
        <form class="dialog run-create-dialog" role="dialog" aria-modal="true" aria-labelledby="model-editor-title" @submit.prevent="saveModel">
          <div class="dialog-heading"><div class="dialog-symbol"><Network :size="19" /></div><button class="icon-button" type="button" :disabled="modelSaving" aria-label="关闭模型配置" @click="showModelDialog = false"><X :size="18" /></button></div>
          <h2 id="model-editor-title">{{ editingModel ? '模型路由详情与编辑' : '登记模型路由' }}</h2>
          <p v-if="editingModel">{{ editingModel.model_id }} · 修订 {{ editingModel.revision }} · 更新时间 {{ editingModel.updated_at }}</p>
          <div v-if="editingModel" class="harness-detail-block"><strong>回退链</strong><p v-if="!modelFallbackChain.length">该模型没有配置回退模型</p><div v-else class="harness-detail-rows"><div v-for="item in modelFallbackChain" :key="item.model_id" class="harness-detail-row"><span><strong>{{ item.name }}</strong> · {{ item.provider || '未指定提供商' }}</span><code>{{ item.model_id }}</code></div></div></div>
          <label class="run-create-field"><span>模型名称</span><input v-model="modelDraft.name" required maxlength="160" :disabled="modelSaving" /></label>
          <label class="run-create-field"><span>提供商标识</span><input v-model="modelDraft.provider" maxlength="160" :disabled="modelSaving" /></label>
          <label class="run-create-field"><span>路由用途</span><input v-model="modelDraft.route" required maxlength="160" :disabled="modelSaving" /></label>
          <label class="run-create-field"><span>备用模型</span><select v-model="modelDraft.fallback_model_id" :disabled="modelSaving"><option :value="null">无</option><option v-for="item in harnessModels.filter(row => row.model_id !== editingModel?.model_id)" :key="item.model_id" :value="item.model_id">{{ item.name }} · {{ item.model_id }}</option></select></label>
          <label class="run-create-field"><span>登记状态</span><input v-model="modelDraft.status" required maxlength="40" :disabled="modelSaving" /></label>
          <label class="run-create-field"><span>成本策略说明</span><textarea v-model="modelDraft.cost_policy" rows="4" maxlength="2000" :disabled="modelSaving"></textarea></label>
          <p v-if="modelError" role="alert">{{ modelError }}</p>
          <div class="dialog-actions"><button class="secondary-button" type="button" :disabled="modelSaving" @click="showModelDialog = false">取消</button><button class="primary-button" type="submit" :disabled="modelSaving">{{ modelSaving ? '保存中…' : '保存登记配置' }}</button></div>
        </form>
      </div>



</template>
