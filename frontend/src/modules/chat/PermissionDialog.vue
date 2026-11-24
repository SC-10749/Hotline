<script setup>
import { Check, ShieldCheck, X } from 'lucide-vue-next'

// 授权弹窗由 App.vue 持有：请求内容通过 props 传进来，确认与取消走 emit。
defineProps({
  request: { type: Object, default: null },
})

defineEmits(['confirm', 'cancel'])
</script>

<template>
<div class="modal-backdrop permission-backdrop workspace-dialog-theme" @click.self="$emit('cancel')">
  <section class="dialog permission-dialog" role="dialog" aria-modal="true" aria-labelledby="permission-title" aria-describedby="permission-copy">
    <div class="dialog-heading">
      <div class="dialog-symbol permission-symbol"><component :is="request.icon" :size="19" /></div>
      <button class="icon-button" type="button" aria-label="取消授权" @click="$emit('cancel')"><X :size="18" /></button>
    </div>
    <h2 id="permission-title">{{ request.title }}</h2>
    <p id="permission-copy">{{ request.description }}</p>
    <div class="permission-scope" aria-label="授权范围">
      <div v-for="item in request.scope" :key="item" class="permission-scope-row"><Check :size="15" /><span>{{ item }}</span></div>
    </div>
    <p class="permission-note"><ShieldCheck :size="15" /> 你可以随时取消，Hotline 只会执行这次明确授权的操作。</p>
    <div class="dialog-actions">
      <button class="secondary-button" type="button" @click="$emit('cancel')">取消</button>
      <button class="primary-button permission-confirm" type="button" @click="$emit('confirm')">{{ request.confirmLabel }}</button>
    </div>
  </section>
</div>
</template>
