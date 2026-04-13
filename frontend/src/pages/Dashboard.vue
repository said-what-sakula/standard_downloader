<template>
  <div>
    <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:16px">
      <h2 style="margin:0">控制台</h2>
      <a-button @click="refresh" :loading="loading">刷新</a-button>
    </div>

    <a-empty
      v-if="!loading && downloaders.length === 0"
      description="暂无来源，请前往【配置管理】添加"
    />

    <a-row :gutter="[24, 24]">
      <a-col :xs="24" :lg="12" v-for="g in groups" :key="g.type">
        <a-card class="group-card">
          <template #title>
            <a-space>
              <a-tag
                :color="g.type === 'guobiao' ? 'blue' : 'green'"
                style="font-size:14px; padding:2px 10px; margin-right:0"
              >{{ g.label }}</a-tag>
              <a-badge
                :status="g.runningCount > 0 ? 'processing' : 'default'"
                :text="g.runningCount > 0 ? `${g.runningCount}/${g.total} 运行中` : '空闲'"
              />
            </a-space>
          </template>

          <!-- 汇总统计 -->
          <a-row :gutter="16" style="margin-bottom:16px; text-align:center">
            <a-col :span="8">
              <a-statistic title="来源数" :value="g.total" suffix="个" />
            </a-col>
            <a-col :span="8">
              <a-statistic
                title="运行中"
                :value="g.runningCount"
                suffix="个"
                :value-style="{ color: g.runningCount > 0 ? '#52c41a' : '#bfbfbf' }"
              />
            </a-col>
            <a-col :span="8">
              <a-statistic title="已下载" :value="g.totalDownloaded" suffix="份" />
            </a-col>
          </a-row>

          <!-- 操作按钮 -->
          <div style="display:flex; gap:8px; margin-bottom:16px">
            <a-button
              type="primary"
              style="flex:1"
              :loading="startingAll[g.type]"
              :disabled="g.runningCount === g.total && g.total > 0"
              @click="startAll(g.type)"
            >全部启动</a-button>
            <a-button
              danger
              style="flex:1"
              :loading="stoppingAll[g.type]"
              :disabled="g.runningCount === 0"
              @click="stopAll(g.type)"
            >全部停止</a-button>
          </div>

          <!-- 来源明细（折叠） -->
          <a-collapse ghost>
            <a-collapse-panel key="1" :header="`查看明细（${g.total} 个来源）`">
              <div
                v-for="item in g.items"
                :key="item.id"
                class="source-row"
              >
                <a-badge :status="item.running ? 'processing' : 'default'" />
                <span class="source-name">{{ item.name }}</span>
                <span style="color:#888; font-size:12px; white-space:nowrap">{{ item.downloaded }} 份</span>
                <div style="margin-left:8px; display:flex; gap:4px; flex-shrink:0">
                  <a-button
                    size="small"
                    v-if="!item.running"
                    type="primary"
                    ghost
                    :loading="starting[item.id]"
                    @click="start(item.id)"
                  >启动</a-button>
                  <a-button
                    size="small"
                    v-else
                    danger
                    :loading="stopping[item.id]"
                    @click="stop(item.id)"
                  >停止</a-button>
                  <a-button size="small" @click="goLog(item.id)">日志</a-button>
                </div>
              </div>
            </a-collapse-panel>
          </a-collapse>
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { getDownloaders, startDownloader, stopDownloader } from '../api'

const router      = useRouter()
const downloaders = ref<any[]>([])
const loading     = ref(false)
const starting    = ref<Record<string, boolean>>({})
const stopping    = ref<Record<string, boolean>>({})
const startingAll = ref<Record<string, boolean>>({})
const stoppingAll = ref<Record<string, boolean>>({})

let timer: ReturnType<typeof setInterval> | null = null

interface Group {
  type: string
  label: string
  items: any[]
  total: number
  runningCount: number
  totalDownloaded: number
}

const groups = computed<Group[]>(() => {
  const defs = [
    { type: 'guobiao',  label: '国家标准' },
    { type: 'hangbiao', label: '行业标准' },
  ]
  return defs
    .map(({ type, label }) => {
      const items = downloaders.value.filter(d => d.type === type)
      return {
        type,
        label,
        items,
        total: items.length,
        runningCount: items.filter(d => d.running).length,
        totalDownloaded: items.reduce((s, d) => s + (d.downloaded || 0), 0),
      }
    })
    .filter(g => g.total > 0)
})

async function refresh() {
  loading.value = true
  try {
    const res = await getDownloaders()
    downloaders.value = res.data
  } catch {
    message.error('获取状态失败')
  } finally {
    loading.value = false
  }
}

async function start(id: string) {
  starting.value[id] = true
  try {
    await startDownloader(id)
    message.success('已启动')
    await refresh()
  } catch (e: any) {
    message.error(e.response?.data?.detail ?? '启动失败')
  } finally {
    starting.value[id] = false
  }
}

async function stop(id: string) {
  stopping.value[id] = true
  try {
    await stopDownloader(id)
    message.success('已发送停止指令，等待当前任务完成后退出')
    await refresh()
  } catch (e: any) {
    message.error(e.response?.data?.detail ?? '停止失败')
  } finally {
    stopping.value[id] = false
  }
}

async function startAll(type: string) {
  startingAll.value[type] = true
  const items = downloaders.value.filter(d => d.type === type && !d.running)
  try {
    await Promise.all(items.map(d => startDownloader(d.id).catch(() => {})))
    message.success('已发送启动指令')
    await refresh()
  } finally {
    startingAll.value[type] = false
  }
}

async function stopAll(type: string) {
  stoppingAll.value[type] = true
  const items = downloaders.value.filter(d => d.type === type && d.running)
  try {
    await Promise.all(items.map(d => stopDownloader(d.id).catch(() => {})))
    message.success('已发送停止指令')
    await refresh()
  } finally {
    stoppingAll.value[type] = false
  }
}

function goLog(id: string) {
  router.push({ path: '/logs', query: { id } })
}

onMounted(() => {
  refresh()
  timer = setInterval(refresh, 5000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.group-card {
  transition: box-shadow .2s;
}
.group-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, .12);
}
.source-row {
  display: flex;
  align-items: center;
  padding: 7px 0;
  border-bottom: 1px solid #f0f0f0;
  gap: 6px;
}
.source-row:last-child {
  border-bottom: none;
}
.source-name {
  flex: 1;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
