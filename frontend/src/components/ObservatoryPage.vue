<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import referenceHtml from './observatory-reference.html?raw'

const props = defineProps({
  themeAccent: { type: String, default: '#4f8cff' },
  themeAccentSoft: { type: String, default: 'rgba(79,140,255,.14)' },
  themeAccentLine: { type: String, default: 'rgba(79,140,255,.3)' },
})
const frame = ref(null)
const themedReference = computed(() => referenceHtml
  .replaceAll('run_', '运行-')
  .replaceAll('node-', '节点-')
  .replaceAll('lint', '代码检查')
  .replaceAll('v1.8', '版本 1.8')
  .replaceAll('--bg:#0a0d13', '--bg:#f5f6f4')
  .replaceAll('--bg-soft:#0e1219', '--bg-soft:#f7f8f6')
  .replaceAll('--card:#12161f', '--card:#ffffff')
  .replaceAll('--card-2:#171c27', '--card-2:#f8f9f7')
  .replaceAll('--card-3:#1c2230', '--card-3:#edf1f7')
  .replaceAll('--border:#232a37', '--border:#d4dce8')
  .replaceAll('--border-soft:#1c2330', '--border-soft:#dfe5ee')
  .replaceAll('--text:#e7ecf4', '--text:#222d40')
  .replaceAll('--text-dim:#93a0b4', '--text-dim:#4c5a70')
  .replaceAll('--text-faint:#5d6a7d', '--text-faint:#68768b')
  .replaceAll('--cyan:#22d3ee', '--cyan:#3d7c9b')
  .replaceAll('--green:#2dd4a7', '--green:#287a50')
  .replaceAll('--green-soft:rgba(45,212,167,.14)', '--green-soft:#e9f4ed')
  .replaceAll('--amber:#f5b945', '--amber:#a96918')
  .replaceAll('--amber-soft:rgba(245,185,69,.14)', '--amber-soft:#fff4e3')
  .replaceAll('--red:#f2565a', '--red:#c64f52')
  .replaceAll('--red-soft:rgba(242,86,90,.14)', '--red-soft:#fff0ed')
  .replaceAll('--violet:#a78bfa', '--violet:#7b5fc0')
  .replaceAll('--pink:#f472b6', '--pink:#bf5d94')
  .replaceAll('--orange:#fb923c', '--orange:#c56e2a')
  .replaceAll('--sky:#38bdf8', '--sky:#3d7c9b')
  .replaceAll('--shadow:0 8px 28px rgba(0,0,0,.35)', '--shadow:0 8px 28px rgba(34,45,64,.12)')
  .replaceAll('rgba(79,140,255,.08)', 'rgba(201,99,69,.04)')
  .replaceAll('rgba(34,211,238,.06)', 'rgba(76,90,112,.03)')
  .replaceAll('#4f8cff', props.themeAccent)
  .replaceAll('rgba(79,140,255,.14)', props.themeAccentSoft)
  .replaceAll('rgba(79,140,255,.3)', props.themeAccentLine)
  .replaceAll('#04121f', '#ffffff')
  .replaceAll('#3f7cf0', props.themeAccent))

function resizeFrame() {
  const element = frame.value
  if (!element) return
  try {
    const documentElement = element.contentDocument?.documentElement
    const body = element.contentDocument?.body
    const height = Math.max(documentElement?.scrollHeight || 0, body?.scrollHeight || 0, 760)
    element.style.height = `${height + 8}px`
  } catch {
    element.style.height = '2800px'
  }
}

function handleFrameLoad() {
  resizeFrame()
  window.setTimeout(resizeFrame, 250)
}

onMounted(() => {
  window.addEventListener('resize', resizeFrame)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeFrame)
})
</script>

<template>
  <section class="observatory-page" aria-label="智能体运行观测台">
    <iframe
      ref="frame"
      class="observatory-frame"
      title="运行总览"
      :srcdoc="themedReference"
      @load="handleFrameLoad"
    />
  </section>
</template>

<style scoped>
.observatory-page {
  width: 100%;
  min-width: 0;
  overflow: hidden;
  border-radius: 14px;
  background: var(--h-canvas, #f5f6f4);
}

.observatory-frame {
  display: block;
  width: 100%;
  min-height: 760px;
  height: 2800px;
  border: 0;
  background: var(--h-canvas, #f5f6f4);
}
</style>
