<script setup>
import { Check } from 'lucide-vue-next'

defineProps({
  panel: { type: Array, default: () => [] },
  selection: { type: Array, default: () => [] },
  sending: { type: Boolean, default: false },
})

defineEmits(['toggle', 'send'])
</script>

<template>
  <section v-if="panel.length" class="option-panel" aria-label="候选答案">
    <div class="option-panel-head">
      <strong>选一个或多个答案</strong>
      <span>点选项可多选，选好后点右侧发送</span>
      <button type="button" class="option-panel-send" :disabled="!selection.length || sending" @click="$emit('send')">发送所选<template v-if="selection.length">（{{ selection.length }}）</template></button>
    </div>
    <div v-for="group in panel" :key="group.question" class="option-group">
      <p class="option-group-question">{{ group.question }}</p>
      <button v-for="option in group.options" :key="option.key" type="button" class="option-item" :class="{ selected: selection.includes(option.key) }" :aria-pressed="selection.includes(option.key)" :disabled="sending" @click="$emit('toggle', option.key)">
        <span class="option-letter">{{ option.letter }}</span>
        <span class="option-label">{{ option.label }}</span>
        <Check v-if="selection.includes(option.key)" :size="14" />
      </button>
    </div>
  </section>
</template>
