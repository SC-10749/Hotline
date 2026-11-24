<script setup>
import { inject } from 'vue'
import { Activity, LoaderCircle, Settings2, X } from 'lucide-vue-next'
import { APP_KEY, SETTINGS_KEY } from '../app/keys'

const ctx = inject(APP_KEY)
const settings = inject(SETTINGS_KEY)

defineEmits(['close', 'save'])
</script>

<template>
  <div class="modal-backdrop" @click.self="$emit('close')">
    <section class="dialog settings-dialog" role="dialog" aria-modal="true" aria-labelledby="settings-title">
      <div class="dialog-heading"><div class="dialog-symbol"><Settings2 :size="19" /></div><button class="icon-button" type="button" aria-label="关闭设置" @click="$emit('close')"><X :size="18" /></button></div>
      <h2 id="settings-title">服务连接</h2><p>填写运行 Python 后端的地址。地址只保存在当前浏览器中。</p>
      <label class="field-label" for="api-base">API 地址</label><input id="api-base" v-model="settings.state.settingsDraft" class="text-field" placeholder="默认与页面同源，可填写其他后端地址" @keydown.enter="$emit('save')" />
      <div class="settings-current"><span class="connection-indicator" :class="ctx.connectionState"></span><span>{{ ctx.connectionState === 'online' ? '当前服务已连接' : ctx.connectionState === 'checking' ? '正在检查连接' : '当前服务不可用' }}</span><code>{{ ctx.backendUrl }}</code></div>
      <div class="dialog-actions"><button class="secondary-button" type="button" @click="$emit('close')">取消</button><button class="primary-button" type="button" :disabled="settings.state.busySettings" @click="$emit('save')"><LoaderCircle v-if="settings.state.busySettings" :size="15" class="spin" /><Activity v-else :size="15" />测试并保存</button></div>
    </section>
  </div>
</template>
