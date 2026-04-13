<template>
  <div>
    <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:16px">
      <h2 style="margin:0">定时增量</h2>
      <a-button type="primary" @click="showModal = true">＋ 新增任务</a-button>
    </div>

    <a-table
      :dataSource="jobs"
      :columns="columns"
      :loading="loading"
      :pagination="false"
      row-key="id"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'source_id'">
          {{ sourceName(record.source_id) }}
        </template>
        <template v-if="column.key === 'next_run'">
          {{ record.next_run ? formatTime(record.next_run) : (record.paused ? '已暂停' : '-') }}
        </template>
        <template v-if="column.key === 'last_run'">
          <template v-if="record.last_run">
            <a-tooltip v-if="!record.last_run.success" :title="record.last_run.error">
              <a-badge status="error" :text="formatTime(record.last_run.time)" />
            </a-tooltip>
            <a-badge v-else status="success" :text="formatTime(record.last_run.time)" />
          </template>
          <span v-else style="color:#bfbfbf">-</span>
        </template>
        <template v-if="column.key === 'action'">
          <a-space>
            <a-button size="small" v-if="!record.paused" @click="pause(record.id)">暂停</a-button>
            <a-button size="small" v-else @click="resume(record.id)">恢复</a-button>
            <a-popconfirm title="确认删除？" @confirm="remove(record.id)">
              <a-button size="small" danger>删除</a-button>
            </a-popconfirm>
          </a-space>
        </template>
      </template>
    </a-table>

    <!-- 新增任务弹窗 -->
    <a-modal
      v-model:open="showModal"
      title="新增定时任务"
      @ok="submitJob"
      :confirm-loading="submitting"
    >
      <a-form :model="form" layout="vertical">
        <a-form-item label="来源" required>
          <a-select v-model:value="form.source_id" placeholder="选择来源">
            <a-select-option v-for="d in downloaders" :key="d.id" :value="d.id">
              {{ d.name }}
            </a-select-option>
          </a-select>
        </a-form-item>

        <a-form-item label="触发方式" required>
          <a-radio-group v-model:value="form.trigger_type">
            <a-radio value="cron">定时（Cron）</a-radio>
            <a-radio value="interval">间隔（Interval）</a-radio>
          </a-radio-group>
        </a-form-item>

        <!-- Cron 参数 -->
        <template v-if="form.trigger_type === 'cron'">
          <a-form-item label="星期（留空=每天）">
            <a-input v-model:value="form.day_of_week" placeholder="如 mon,wed,fri 或留空" />
          </a-form-item>
          <a-form-item label="小时（0-23）" required>
            <a-input v-model:value="form.hour" placeholder="如 9 或 */6" />
          </a-form-item>
          <a-form-item label="分钟（0-59）">
            <a-input v-model:value="form.minute" placeholder="如 30，默认 0" />
          </a-form-item>
        </template>

        <!-- Interval 参数 -->
        <template v-else>
          <a-form-item label="间隔小时数">
            <a-input-number v-model:value="form.hours" :min="0" style="width:100%" />
          </a-form-item>
          <a-form-item label="间隔分钟数">
            <a-input-number v-model:value="form.minutes" :min="0" style="width:100%" />
          </a-form-item>
        </template>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { getJobs, createJob, deleteJob, pauseJob, resumeJob, getDownloaders } from '../api'

const jobs        = ref<any[]>([])
const downloaders = ref<any[]>([])
const loading     = ref(false)
const showModal   = ref(false)
const submitting  = ref(false)

const form = reactive({
  source_id:    '',
  trigger_type: 'cron',
  hour:         '',
  minute:       '0',
  day_of_week:  '',
  hours:        null as number | null,
  minutes:      null as number | null,
})

const columns = [
  { title: '来源',     key: 'source_id',  dataIndex: 'source_id' },
  { title: '触发规则', key: 'trigger',    dataIndex: 'trigger'   },
  { title: '下次执行', key: 'next_run'                           },
  { title: '上次执行', key: 'last_run'                           },
  { title: '操作',     key: 'action'                             },
]

onMounted(async () => {
  await Promise.all([loadJobs(), loadDownloaders()])
})

async function loadJobs() {
  loading.value = true
  try {
    const res = await getJobs()
    jobs.value = res.data
  } catch { message.error('获取任务列表失败') }
  finally { loading.value = false }
}

async function loadDownloaders() {
  const res = await getDownloaders()
  downloaders.value = res.data
}

async function submitJob() {
  if (!form.source_id) { message.warning('请选择来源'); return }
  submitting.value = true
  try {
    const payload: any = {
      source_id:    form.source_id,
      trigger_type: form.trigger_type,
    }
    if (form.trigger_type === 'cron') {
      if (form.hour)        payload.hour = form.hour
      if (form.minute)      payload.minute = form.minute
      if (form.day_of_week) payload.day_of_week = form.day_of_week
    } else {
      if (form.hours)   payload.hours = form.hours
      if (form.minutes) payload.minutes = form.minutes
    }
    await createJob(payload)
    message.success('任务已创建')
    showModal.value = false
    await loadJobs()
  } catch (e: any) {
    message.error(e.response?.data?.detail ?? '创建失败')
  } finally {
    submitting.value = false
  }
}

async function pause(id: string) {
  await pauseJob(id); await loadJobs(); message.success('已暂停')
}

async function resume(id: string) {
  await resumeJob(id); await loadJobs(); message.success('已恢复')
}

async function remove(id: string) {
  await deleteJob(id); await loadJobs(); message.success('已删除')
}

function sourceName(id: string) {
  const d = downloaders.value.find(x => x.id === id)
  return d ? d.name : id
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleString('zh-CN')
}
</script>
