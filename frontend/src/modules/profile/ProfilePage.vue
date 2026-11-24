<script setup>
import { inject } from 'vue'
import { KeyRound, Palette, Smile, UserRound } from 'lucide-vue-next'
import { petOptions } from './useProfile'
import { APP_KEY, PROFILE_KEY } from '../app/keys'

const ctx = inject(APP_KEY)
const profile = inject(PROFILE_KEY)
</script>

<template>
  <section class="profile-settings-content" :aria-labelledby="`${ctx.activePage}-page-title`">
    <template v-if="ctx.profileSection === 'basics'">
      <div class="profile-settings-intro"><div class="profile-settings-avatar"><UserRound :size="25" /></div><div><h2>个人资料</h2></div></div>
      <div class="profile-form"><label>昵称<input v-model="profile.state.profileDraft.nickname" class="text-field" maxlength="60" placeholder="输入昵称" /></label><label>个人简介<textarea v-model="profile.state.profileDraft.bio" class="text-field" rows="3" maxlength="500" placeholder="介绍一下自己"></textarea></label><button class="primary-button" type="button" :disabled="profile.state.profileBusy" @click="profile.actions.saveProfileBasics">{{ profile.state.profileBusy ? '保存中…' : '保存资料' }}</button></div>
    </template>
    <template v-else-if="ctx.profileSection === 'api'">
      <div class="settings-section-copy"><KeyRound :size="22" /><div><h2>模型 API Key</h2></div></div>
      <div class="profile-form">
        <label class="api-key-field">访问令牌<input v-model="profile.state.accessTokenDraft" class="text-field" type="password" placeholder="与后端 HOTLINE_API_TOKEN 一致（留空表示不启用）" /></label>
        <p class="settings-note">后端配置了 HOTLINE_API_TOKEN 时，浏览器请求需要带上同一个令牌。</p>
        <div class="dialog-actions">
          <button class="primary-button" type="button" @click="profile.actions.saveAccessToken">保存令牌</button>
        </div>
      </div>
      <div class="profile-form">
        <label>服务商<input v-model="profile.state.credentialDraft.provider" class="text-field" placeholder="例如：openai-compatible" /></label>
        <label>Base URL<input v-model="profile.state.credentialDraft.baseUrl" class="text-field" placeholder="https://api.example.com/v1" /></label>
        <label>模型名称<input v-model="profile.state.credentialDraft.model" class="text-field" placeholder="模型 ID" /></label>
        <label class="api-key-field">API Key<input v-model="profile.state.credentialDraft.apiKey" class="text-field" type="password" placeholder="sk-••••••••••••••••" /></label>
        <p v-if="profile.state.credentialMask" class="settings-note">已保存密钥：{{ profile.state.credentialMask }}（留空表示不修改）</p>
        <div class="dialog-actions">
          <button class="secondary-button" type="button" :disabled="profile.state.credentialBusy" @click="profile.actions.testCredentialForm">测试连接</button>
          <button class="primary-button" type="button" :disabled="profile.state.credentialBusy" @click="profile.actions.saveCredentialForm">{{ profile.state.credentialBusy ? '处理中…' : '保存凭证' }}</button>
          <button v-if="profile.state.credentialMask" class="text-action danger" type="button" @click="profile.actions.removeCredential">删除凭证</button>
        </div>
      </div>
    </template>
    <template v-else-if="ctx.profileSection === 'personalization'">
      <div class="settings-section-copy"><Palette :size="22" /><div><h2>个性化偏好</h2></div></div>
      <div class="preference-row"><div><strong>回答风格</strong></div><select v-model="profile.state.profileDraft.answerStyle"><option value="default">默认</option><option value="concise">简洁</option><option value="detailed">详尽</option><option value="friendly">亲切</option></select></div>
      <div class="preference-row"><div><strong>界面主题</strong></div><select v-model="profile.state.profileDraft.theme"><option value="system">跟随系统</option><option value="light">浅色</option><option value="dark">深色</option></select></div>
      <button class="primary-button" type="button" :disabled="profile.state.profileBusy" @click="profile.actions.savePreferences">{{ profile.state.profileBusy ? '保存中…' : '保存偏好' }}</button>
    </template>
    <template v-else>
      <div class="pet-preview"><component :is="profile.state.petIcon" :size="38" /><strong>{{ profile.state.petLabel }}</strong></div>
      <div class="preference-row"><div><strong>桌宠状态</strong><small>开启后可在页面右下角显示虚拟伙伴</small></div><label class="switch switch-pill"><input type="checkbox" :checked="profile.state.petEnabled" @change="profile.actions.togglePet" /><span class="switch-track" aria-hidden="true"></span></label></div>
      <div class="pet-options"><button v-for="option in petOptions" :key="option.id" type="button" class="pet-option" :class="{ active: profile.state.petChoice === option.id }" @click="profile.actions.choosePet(option.id)"><component :is="option.icon" :size="18" /><span>{{ option.label }}</span></button></div>
    </template>
  </section>
</template>
