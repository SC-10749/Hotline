// Skill 目录：本地安装包与 Catalog 版本绑定。
import { computed, ref } from 'vue'
import { usePageState } from '../../composables/usePageState'
import { getSkillDetail, setSkillEnabled } from '../../api'
import { getCatalogSkills, getCatalogVersion, compareCatalogVersions } from '../../api'
import { bindCatalogSkill, unbindCatalogSkill } from '../../api'
import { getSkills } from '../../api'

export function useSkillDirectory({ props, notify }) {
  const harnessSkills = ref([])
  const skillsConnected = ref(false)
  const skillsError = ref('')
  const selectedSkill = ref(null)
  const skillChangingId = ref('')
  const skillChangeError = ref('')
  const skillDirectoryTab = usePageState('skills-tab', 'installed', ['installed', 'catalog'])
  const catalog = ref({ project: '', skills: [], bindings: [], rollouts: [] })
  const catalogLoading = ref(false)
  const catalogConnected = ref(false)
  const catalogError = ref('')
  const selectedCatalogName = ref('')
  const catalogVersion = ref('')
  const catalogBaseVersion = ref('')
  const catalogDetail = ref(null)
  const catalogComparison = ref(null)
  const catalogDetailBusy = ref(false)
  const catalogDetailError = ref('')
  const catalogNames = computed(() => [...new Set(catalog.value.skills.map(item => item.name))])
  const catalogVersions = computed(() => catalog.value.skills.filter(item => item.name === selectedCatalogName.value))
  const catalogBindPercentage = ref(0)
  const catalogBindBusy = ref(false)
  const catalogBindError = ref('')
  const skillRows = computed(() => harnessSkills.value)
  async function bindSelectedCatalogVersion() {
    if (!selectedCatalogName.value || !catalogVersion.value) { catalogBindError.value = '请先选择技能与版本'; return }
    catalogBindBusy.value = true
    catalogBindError.value = ''
    try {
      await bindCatalogSkill(props.apiBase, { name: selectedCatalogName.value, version: catalogVersion.value, percentage: Number(catalogBindPercentage.value) || 0 })
      notify(`已绑定 ${selectedCatalogName.value} ${catalogVersion.value}`)
      await refreshCatalogData()
    } catch (error) { catalogBindError.value = error.message || '绑定失败' }
    finally { catalogBindBusy.value = false }
  }

  async function unbindCurrentCatalogSkill() {
    if (!selectedCatalogName.value) return
    catalogBindBusy.value = true
    catalogBindError.value = ''
    try {
      await unbindCatalogSkill(props.apiBase, { name: selectedCatalogName.value })
      notify(`已解绑 ${selectedCatalogName.value}`)
      await refreshCatalogData()
    } catch (error) { catalogBindError.value = error.message || '解绑失败' }
    finally { catalogBindBusy.value = false }
  }

  async function refreshSkillData() {
    try {
      harnessSkills.value = await getSkills(props.apiBase)
      skillsConnected.value = true
      skillsError.value = ''
    } catch (error) { skillsError.value = error.message || 'Skill 目录暂不可用' }
  }

  async function refreshCatalogData() {
    if (catalogLoading.value) return
    catalogLoading.value = true
    try {
      catalog.value = await getCatalogSkills(props.apiBase)
      catalogConnected.value = true
      catalogError.value = ''
    } catch (error) { catalogError.value = error.message || 'Catalog 读取失败' }
    finally { catalogLoading.value = false }
  }

  function selectSkillDirectory(tab) {
    skillDirectoryTab.value = tab
    if (tab === 'catalog') refreshCatalogData()
    else refreshSkillData()
  }

  async function loadCatalogVersion() {
    if (catalogDetailBusy.value) return
    catalogDetailBusy.value = true
    catalogDetail.value = null
    catalogComparison.value = null
    catalogDetailError.value = ''
    try {
      catalogDetail.value = await getCatalogVersion(props.apiBase, selectedCatalogName.value, catalogVersion.value)
    } catch (error) { catalogDetailError.value = error.message || '版本读取失败' }
    finally { catalogDetailBusy.value = false }
  }

  function openCatalogSkill(name) {
    selectedCatalogName.value = name
    const versions = catalog.value.skills.filter(item => item.name === name)
    catalogVersion.value = versions[0].version
    catalogBaseVersion.value = versions[1]?.version || versions[0].version
    loadCatalogVersion()
  }

  async function compareCatalogSkill() {
    if (catalogDetailBusy.value) return
    catalogDetailBusy.value = true
    catalogDetailError.value = ''
    catalogComparison.value = null
    try {
      catalogComparison.value = await compareCatalogVersions(props.apiBase, selectedCatalogName.value, catalogBaseVersion.value, catalogVersion.value)
    } catch (error) { catalogDetailError.value = error.message || '版本比较失败' }
    finally { catalogDetailBusy.value = false }
  }

  async function openSkillDetails(row) {
    if (row.id.startsWith('demo-')) return notify('请连接 Skill 目录后查看真实安装包')
    try {
      selectedSkill.value = await getSkillDetail(props.apiBase, row.id)
      skillChangeError.value = ''
    } catch (error) { notify(`读取 Skill 失败：${error.message}`) }
  }

  async function toggleInstalledSkill(skill) {
    if (skillChangingId.value) return
    skillChangeError.value = ''
    skillChangingId.value = skill.id
    try {
      const updated = await setSkillEnabled(props.apiBase, skill.id, !skill.enabled)
      harnessSkills.value = harnessSkills.value.map(item => item.id === updated.id ? updated : item)
      if (selectedSkill.value?.id === updated.id) selectedSkill.value = { ...selectedSkill.value, ...updated }
      notify(updated.enabled ? 'Skill 已启用' : 'Skill 已停用')
    } catch (error) { skillChangeError.value = error.message || 'Skill 启停失败，请重试' }
    finally { skillChangingId.value = '' }
  }


  return {
    bindSelectedCatalogVersion,
    catalog,
    catalogBaseVersion,
    catalogBindBusy,
    catalogBindError,
    catalogBindPercentage,
    catalogComparison,
    catalogConnected,
    catalogDetail,
    catalogDetailBusy,
    catalogDetailError,
    catalogError,
    catalogLoading,
    catalogNames,
    catalogVersion,
    catalogVersions,
    compareCatalogSkill,
    harnessSkills,
    loadCatalogVersion,
    openCatalogSkill,
    openSkillDetails,
    refreshCatalogData,
    refreshSkillData,
    selectSkillDirectory,
    selectedCatalogName,
    selectedSkill,
    skillChangeError,
    skillChangingId,
    skillDirectoryTab,
    skillRows,
    skillsConnected,
    skillsError,
    toggleInstalledSkill,
    unbindCurrentCatalogSkill,
  }
}
