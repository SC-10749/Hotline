<script setup>
import { inject } from 'vue'
import { HARNESS_SHELL, HARNESS_SKILLS } from '../context'
import { Sparkles, X } from 'lucide-vue-next'

const ctxShell = inject(HARNESS_SHELL)
const ctxSkills = inject(HARNESS_SKILLS)

const { activeSection, refreshActiveSection } = ctxShell
const { bindSelectedCatalogVersion, catalog, catalogBaseVersion, catalogBindBusy, catalogBindError, catalogBindPercentage, catalogComparison, catalogDetail, catalogDetailBusy, catalogDetailError, catalogError, catalogLoading, catalogNames, catalogVersion, catalogVersions, compareCatalogSkill, loadCatalogVersion, openCatalogSkill, openSkillDetails, selectSkillDirectory, selectedCatalogName, selectedSkill, skillChangeError, skillChangingId, skillDirectoryTab, skillRows, skillsConnected, skillsError, toggleInstalledSkill, unbindCurrentCatalogSkill } = ctxSkills
</script>

<template>



        <section v-if="activeSection === 'skills'" class="resource-page">
          <div class="evaluation-tabs" role="group" aria-label="Skill 来源"><button :class="{ active: skillDirectoryTab === 'installed' }" @click="selectSkillDirectory('installed')">本地安装包</button><button :class="{ active: skillDirectoryTab === 'catalog' }" @click="selectSkillDirectory('catalog')">Catalog 版本</button></div>
          <template v-if="skillDirectoryTab === 'installed'">
          <p v-if="skillsError" role="alert">{{ skillsError }}</p>
          <section class="harness-panel resource-table-panel"><div class="harness-panel-heading"><div><h3>本地 Skill 安装目录</h3><p>{{ skillRows.length }} 条记录 · {{ skillsConnected ? '已连接目录' : '未连接 Skill 目录' }}</p></div></div>
            <div v-if="skillRows.length" class="ui-table ui-cols-generic">
              <div class="ui-table-head"><span>名称 / 说明</span><span>来源文件</span><span>入口</span><span>状态</span><span></span></div>
              <div v-for="row in skillRows" :key="row.id" class="ui-row"><span><strong>{{ row.name }}</strong><small>{{ row.description || '暂无描述' }}</small></span><span>{{ row.sourceFile || '本地安装包' }}</span><span>{{ row.entry || '—' }}</span><span>{{ row.enabled ? '已启用' : '已停用' }}</span><button class="text-action" @click="openSkillDetails(row)">查看</button></div>
            </div>
            <div v-else class="ui-empty"><span>尚未安装本地 Skill 包</span></div>
          </section>
          </template>
          <section v-else class="harness-panel resource-table-panel">
            <div class="harness-panel-heading"><div><h3>Catalog 版本与项目绑定</h3><p>{{ catalog.project || '当前项目' }} · {{ catalogNames.length }} 个技能 · {{ catalog.skills.length }} 个版本</p></div></div>
            <p v-if="catalogError" role="alert">{{ catalogError }}</p>
            <div v-if="catalogLoading" class="ui-empty">正在读取 Catalog…</div>
            <div v-else-if="catalogNames.length" class="ui-table ui-cols-generic">
              <div class="ui-table-head"><span>技能</span><span>版本数</span><span>项目绑定</span><span>灰度状态</span><span></span></div>
              <div v-for="name in catalogNames" :key="name" class="ui-row"><span><strong>{{ name }}</strong></span><span>{{ catalog.skills.filter(row => row.name === name).length }}</span><span>{{ catalog.bindings.find(row => row.name === name)?.version || '未绑定' }}</span><span>{{ catalog.rollouts.find(row => row.name === name && row.active)?.percentage ?? '—' }}{{ catalog.rollouts.some(row => row.name === name && row.active) ? '%' : '' }}</span><button class="text-action" @click="openCatalogSkill(name)">查看</button></div>
            </div>
            <div v-else class="ui-empty">当前没有 Catalog 版本</div>
          </section>
        </section>
      <div v-if="selectedCatalogName" class="modal-backdrop" @click.self="!catalogDetailBusy && (selectedCatalogName = '')">
        <section class="dialog skills-dialog" role="dialog" aria-modal="true" aria-labelledby="catalog-detail-title">
          <div class="dialog-heading"><div class="dialog-symbol"><Sparkles :size="19" /></div><button class="icon-button" type="button" :disabled="catalogDetailBusy" aria-label="关闭 Catalog 详情" @click="selectedCatalogName = ''"><X :size="18" /></button></div>
          <h2 id="catalog-detail-title">{{ selectedCatalogName }}</h2>
          <p>项目 {{ catalog.project }} · 绑定 {{ catalog.bindings.find(row => row.name === selectedCatalogName)?.version || '未绑定' }}</p>
          <label class="run-create-field"><span>查看版本</span><select v-model="catalogVersion" :disabled="catalogDetailBusy" @change="loadCatalogVersion"><option v-for="row in catalogVersions" :key="row.version" :value="row.version">{{ row.version }}</option></select></label>
          <p v-if="catalogDetailBusy" role="status">正在读取…</p><p v-if="catalogDetailError" role="alert">{{ catalogDetailError }}</p>
          <template v-if="catalogDetail"><p>{{ catalogDetail.description }} · {{ catalogDetail.created_at }}</p><h3>SKILL.md</h3><pre class="skill-detail-content">{{ catalogDetail.content }}</pre><p v-if="catalogDetail.truncated">正文预览展示前 12000 个字符。</p><h3>附加资源</h3><ul><li v-for="resource in catalogDetail.resources" :key="resource.path">{{ resource.path }} · {{ resource.chars }} 字符</li></ul><p v-if="!catalogDetail.resources.length">无附加资源</p></template>
          <label class="run-create-field"><span>比较基准</span><select v-model="catalogBaseVersion" :disabled="catalogDetailBusy" @change="catalogComparison = null"><option v-for="row in catalogVersions" :key="row.version" :value="row.version">{{ row.version }}</option></select></label>
          <button class="secondary-button" type="button" :disabled="catalogDetailBusy" @click="compareCatalogSkill">比较版本</button>
          <div class="harness-detail-block"><strong>项目绑定</strong><div class="harness-detail-actions"><label>灰度比例<input v-model.number="catalogBindPercentage" type="number" min="0" max="100" :disabled="catalogBindBusy" /></label><button class="button button-subtle" type="button" :disabled="catalogBindBusy" @click="bindSelectedCatalogVersion">{{ catalogBindBusy ? '处理中…' : '绑定到当前项目' }}</button><button class="button button-subtle" type="button" :disabled="catalogBindBusy" @click="unbindCurrentCatalogSkill">解除绑定</button></div><p v-if="catalogBindError" role="alert">{{ catalogBindError }}</p></div>
          <template v-if="catalogComparison"><p>{{ catalogComparison.baseVersion }} → {{ catalogComparison.version }}</p><pre class="skill-detail-content">{{ catalogComparison.diff || '正文无差异' }}</pre><p v-if="catalogComparison.truncated">差异内容超过展示上限。</p><ul><li v-for="change in catalogComparison.resourceChanges" :key="change.path">{{ change.change === 'added' ? '新增' : change.change === 'removed' ? '删除' : '修改' }} · {{ change.path }}</li></ul><p v-if="!catalogComparison.resourceChanges.length">附加资源无变化</p></template>
          <div class="dialog-actions"><button class="secondary-button" type="button" :disabled="catalogDetailBusy" @click="selectedCatalogName = ''">关闭</button></div>
        </section>
      </div>
      <div v-if="selectedSkill" class="modal-backdrop" @click.self="!skillChangingId && (selectedSkill = null)">
        <section class="dialog skills-dialog" role="dialog" aria-modal="true" aria-labelledby="skill-detail-title">
          <div class="dialog-heading"><div class="dialog-symbol"><Sparkles :size="19" /></div><button class="icon-button" type="button" :disabled="!!skillChangingId" aria-label="关闭 Skill 详情" @click="selectedSkill = null"><X :size="18" /></button></div>
          <h2 id="skill-detail-title">{{ selectedSkill.name }}</h2>
          <p>{{ selectedSkill.description || '暂无描述' }}</p>
          <p>本地安装包 · {{ selectedSkill.id }} · {{ selectedSkill.enabled ? '已启用' : '已停用' }}</p>
          <p>来源文件 {{ selectedSkill.sourceFile }} · 入口 {{ selectedSkill.entry }}</p>
          <p>安装时间 {{ selectedSkill.createdAt || '未记录' }}</p>
          <h3>SKILL.md</h3><pre class="skill-detail-content">{{ selectedSkill.content }}</pre>
          <p v-if="selectedSkill.truncated">正文超过预览上限，当前展示前 12000 个字符。</p>
          <p v-if="skillChangeError" role="alert">{{ skillChangeError }}</p>
          <div class="dialog-actions"><button class="secondary-button" type="button" :disabled="!!skillChangingId" @click="selectedSkill = null">关闭</button><button class="primary-button" type="button" :disabled="!!skillChangingId" @click="toggleInstalledSkill(selectedSkill)">{{ skillChangingId ? '处理中…' : selectedSkill.enabled ? '停用 Skill' : '启用 Skill' }}</button></div>
        </section>
      </div>



</template>
