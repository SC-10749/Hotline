import { reactive, ref } from 'vue'
import { createSchedule, deleteSchedule, getSchedules, runSchedule, updateSchedule } from '../../api'

export function useAutomation(ctx) {
  const schedules = ref([])
  const scheduleBusy = ref(false)
  const showScheduleForm = ref(false)
  const scheduleDraft = ref({ name: '', prompt: '', agent: 'chat', intervalMinutes: 60 })

  async function refreshSchedules() {
    try {
      schedules.value = (await getSchedules(ctx.backendUrl))?.items || []
    } catch (error) {
      schedules.value = []
    }
  }

  function openScheduleForm() {
    scheduleDraft.value = { name: '', prompt: '', agent: 'chat', intervalMinutes: 60 }
    showScheduleForm.value = true
  }

  async function submitSchedule() {
    if (scheduleBusy.value) return
    if (!scheduleDraft.value.name.trim() || !scheduleDraft.value.prompt.trim()) {
      ctx.showToast('请填写任务名称和任务内容')
      return
    }
    scheduleBusy.value = true
    try {
      await createSchedule(ctx.backendUrl, {
        name: scheduleDraft.value.name.trim(),
        prompt: scheduleDraft.value.prompt.trim(),
        agent: scheduleDraft.value.agent,
        intervalMinutes: Number(scheduleDraft.value.intervalMinutes) || 60,
      })
      showScheduleForm.value = false
      await refreshSchedules()
      ctx.showToast('定时任务已创建')
    } catch (error) {
      ctx.showToast(`创建失败：${error.message || '定时任务服务不可用'}`)
    } finally {
      scheduleBusy.value = false
    }
  }

  async function toggleSchedule(task) {
    if (scheduleBusy.value) return
    scheduleBusy.value = true
    try {
      await updateSchedule(ctx.backendUrl, task.task_id, { enabled: !task.enabled })
      await refreshSchedules()
    } catch (error) {
      ctx.showToast(`更新失败：${error.message || '定时任务服务不可用'}`)
    } finally {
      scheduleBusy.value = false
    }
  }

  async function runScheduleNow(task) {
    if (scheduleBusy.value) return
    scheduleBusy.value = true
    try {
      const result = await runSchedule(ctx.backendUrl, task.task_id)
      await refreshSchedules()
      ctx.showToast(result?.run?.run_id ? `已提交运行 ${result.run.run_id}` : '已提交执行')
    } catch (error) {
      ctx.showToast(`执行失败：${error.message || '执行服务不可用'}`)
    } finally {
      scheduleBusy.value = false
    }
  }

  async function removeSchedule(task) {
    if (!window.confirm(`删除定时任务 ${task.name}？`)) return
    try {
      await deleteSchedule(ctx.backendUrl, task.task_id)
      await refreshSchedules()
      ctx.showToast(`已删除 ${task.name}`)
    } catch (error) {
      ctx.showToast(`删除失败：${error.message || '定时任务服务不可用'}`)
    }
  }

  const state = reactive({ schedules, scheduleBusy, showScheduleForm, scheduleDraft })

  const actions = {
    refreshSchedules, openScheduleForm, submitSchedule, toggleSchedule, runScheduleNow, removeSchedule,
  }

  return { state, actions }
}
