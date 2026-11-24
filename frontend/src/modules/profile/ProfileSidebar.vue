<script setup>
import { inject } from 'vue'
import { KeyRound, Palette, Smile, UserRound } from 'lucide-vue-next'
import { APP_KEY } from '../app/keys'

const ctx = inject(APP_KEY)
</script>

<template>
  <nav class="profile-settings-nav" aria-label="个人设置">
    <button type="button" :class="{ active: ctx.profileSection === 'basics' }" @click="ctx.profileSection = 'basics'"><UserRound :size="17" />基础信息</button>
    <button type="button" :class="{ active: ctx.profileSection === 'api' }" @click="ctx.profileSection = 'api'"><KeyRound :size="17" />API Key</button>
    <button type="button" :class="{ active: ctx.profileSection === 'personalization' }" @click="ctx.profileSection = 'personalization'"><Palette :size="17" />个性化</button>
    <button type="button" :class="{ active: ctx.profileSection === 'pet' }" @click="ctx.profileSection = 'pet'"><Smile :size="17" />虚拟桌宠</button>
  </nav>
</template>
