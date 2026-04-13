<template>
  <div style="display:flex; gap:16px; height:calc(100vh - 120px)">
    <!-- 左侧：来源选择 + 日志文件列表 -->
    <div style="width:260px; flex-shrink:0; display:flex; flex-direction:column; gap:12px">
      <a-select
        v-model:value="selectedId"
        placeholder="选择来源"
        style="width:100%"
        @change="onSourceChange"
      >
        <a-select-option v-for="d in downloaders" :key="d.id" :value="d.id">
          {{ d.name }}
        </a-select-option>
      </a-select>

      <!-- 仅在流运行时显示停止按钮 -->
      <a-button
        v-if="streaming"
        type="default"
        block
        @click="stopStream"
      >
        ⏹ 停止实时日志
      </a-button>

      <a-divider style="margin:4px 0">历史日志</a-divider>

      <div style="flex:1; overflow-y:auto">
        <a-spin :spinning="historyLoading">
          <a-empty v-if="!historyLoading && historyFiles.length === 0" description="暂无日志" :image-size="40" />
          <div
            v-for="f in historyFiles"
            :key="f.filename"
            class="log-file-item"
            :class="{ active: activeFile === f.filename }"
            @click="loadFile(f.filename)"
          >
            <div style="font-size:12px; font-weight:600">{{ f.filename }}</div>
            <div style="font-size:11px; color:#888">{{ formatSize(f.size) }}</div>
          </div>
        </a-spin>
      </div>

      <!-- 清空按钮 -->
      <a-button
        v-if="activeFile"
        danger
        size="small"
        block
        @click="clearFile"
      >清空日志</a-button>
    </div>

    <!-- 右侧：日志内容 -->
    <div style="flex:1; display:flex; flex-direction:column; border:1px solid #d9d9d9; border-radius:6px; overflow:hidden">
      <div
        style="padding:8px 12px; background:#f5f5f5; font-size:12px; color:#666; border-bottom:1px solid #d9d9d9; display:flex; align-items:center; justify-content:space-between"
      >
        <span>{{ streaming ? '实时日志流' : (activeFile || '请选择来源或日志文件') }}</span>
        <div style="display:flex; align-items:center; gap:8px">
          <!-- 截断提示 -->
          <a-tooltip v-if="truncated" :title="`文件共 ${totalLines} 行，当前仅显示最后 ${shownLines} 行`">
            <a-tag color="orange" style="cursor:default">
              仅显示最后 {{ shownLines }} 行 / 共 {{ totalLines }} 行
            </a-tag>
          </a-tooltip>
          <!-- 实时流行数提示 -->
          <a-tag v-if="streaming && streamLineCount >= MAX_STREAM_LINES" color="orange" style="cursor:default">
            已截断，仅显示最新 {{ MAX_STREAM_LINES }} 行
          </a-tag>
          <!-- 加载全部按钮 -->
          <a-button
            v-if="truncated && !fileLoading"
            size="small"
            @click="loadFileFull"
          >
            加载全部
          </a-button>
          <a-spin v-if="fileLoading" :spinning="true" size="small" />
          <a-badge v-if="streaming" status="processing" text="直播中" />
        </div>
      </div>
      <pre
        ref="logEl"
        v-html="colorizedLog"
        style="flex:1; margin:0; padding:12px; overflow-y:auto; font-size:12px; background:#1e1e1e; line-height:1.6; white-space:pre-wrap; word-break:break-all"
      ></pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  getDownloaders, getLogHistory, getLogFile, clearLog, createSSE,
} from '../api'

const route = useRoute()

const MAX_STREAM_LINES = 2000  // 实时流最大保留行数

const downloaders    = ref<any[]>([])
const selectedId     = ref<string | undefined>(undefined)
const historyFiles   = ref<any[]>([])
const historyLoading = ref(false)
const activeFile     = ref('')
const logContent     = ref('')
const logEl          = ref<HTMLPreElement | null>(null)
const fileLoading    = ref(false)

// 截断信息
const truncated   = ref(false)
const totalLines  = ref(0)
const shownLines  = ref(0)

// 实时流行数统计（直接统计 logContent 中换行数，避免每次 split 开销）
const streamLineCount = ref(0)

// 日志着色
const colorizedLog = computed(() => {
  if (!logContent.value) return '<span style="color:#555">（暂无内容）</span>'
  return logContent.value
    .split('\n')
    .map(line => {
      const esc = line.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      const t = line.trimStart()
      if (t.startsWith('→'))
        return `\n<span style="color:#e2c08d;font-weight:600">${esc}</span>`
      if (t.includes('✓') || t.includes('已保存:') || t.startsWith('🎉'))
        return `<span style="color:#4ec9b0">${esc}</span>`
      if (t.startsWith('↺'))
        return `<span style="color:#569cd6">${esc}</span>`
      if (t.includes('⚠'))
        return `<span style="color:#ce9178">${esc}</span>`
      if (t.includes('❌'))
        return `<span style="color:#f44747">${esc}</span>`
      if (t.startsWith('[') || t.startsWith('○'))
        return `<span style="color:#888">${esc}</span>`
      return `<span style="color:#d4d4d4">${esc}</span>`
    })
    .join('\n')
})

const streaming = ref(false)
let sse: EventSource | null = null

onMounted(async () => {
  await loadDownloaders()
  const id = (route.query.id as string) || downloaders.value[0]?.id
  if (id) {
    selectedId.value = id
    await onSourceChange(id)
  }
})

onUnmounted(() => { stopStream() })

async function loadDownloaders() {
  const res = await getDownloaders()
  downloaders.value = res.data
}

async function onSourceChange(id: string) {
  stopStream()
  logContent.value = ''
  activeFile.value = ''
  truncated.value = false
  totalLines.value = 0
  shownLines.value = 0
  await loadHistory(id)
  startStream()
}

async function loadHistory(id: string) {
  historyLoading.value = true
  try {
    const res = await getLogHistory(id)
    historyFiles.value = res.data
  } catch {
    message.error('获取日志列表失败')
  } finally {
    historyLoading.value = false
  }
}

async function loadFile(filename: string) {
  if (!selectedId.value) return
  stopStream()
  activeFile.value = filename
  truncated.value = false
  fileLoading.value = true
  try {
    const res = await getLogFile(selectedId.value, filename)
    const data = res.data
    logContent.value = data.content
    truncated.value = data.truncated ?? false
    totalLines.value = data.total_lines ?? 0
    shownLines.value = data.shown_lines ?? 0
    scrollBottom()
  } catch {
    message.error('读取日志失败')
  } finally {
    fileLoading.value = false
  }
}

async function loadFileFull() {
  if (!selectedId.value || !activeFile.value) return
  fileLoading.value = true
  try {
    const res = await getLogFile(selectedId.value, activeFile.value, true)
    const data = res.data
    logContent.value = data.content
    truncated.value = false
    totalLines.value = data.total_lines ?? 0
    shownLines.value = data.shown_lines ?? 0
    scrollBottom()
  } catch {
    message.error('读取日志失败')
  } finally {
    fileLoading.value = false
  }
}

function startStream() {
  if (!selectedId.value) return
  activeFile.value = ''
  logContent.value = ''
  streamLineCount.value = 0
  streaming.value = true
  sse = createSSE(selectedId.value)
  sse.onmessage = (e) => {
    const newLine = e.data.replace(/\\n/g, '\n') + '\n'
    logContent.value += newLine
    streamLineCount.value += (newLine.match(/\n/g) || []).length

    // 超出限制时截断头部
    if (streamLineCount.value > MAX_STREAM_LINES + 200) {
      const lines = logContent.value.split('\n')
      const trimmed = lines.slice(lines.length - MAX_STREAM_LINES)
      logContent.value = trimmed.join('\n')
      streamLineCount.value = MAX_STREAM_LINES
    }
    scrollBottom()
  }
  sse.addEventListener('close', () => {
    streaming.value = false
    message.info('进程已结束')
  })
  sse.addEventListener('ping', () => { /* heartbeat */ })
  sse.onerror = () => {
    stopStream()
  }
}

function stopStream() {
  if (sse) {
    sse.close()
    sse = null
  }
  streaming.value = false
}

async function clearFile() {
  if (!selectedId.value || !activeFile.value) return
  try {
    await clearLog(selectedId.value, activeFile.value)
    message.success('已清空')
    logContent.value = ''
    truncated.value = false
    await loadHistory(selectedId.value)
  } catch (e: any) {
    message.error(e.response?.data?.detail ?? '清空失败')
  }
}

function scrollBottom() {
  nextTick(() => {
    if (logEl.value) {
      logEl.value.scrollTop = logEl.value.scrollHeight
    }
  })
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1048576).toFixed(1)} MB`
}
</script>

<style scoped>
.log-file-item {
  padding: 8px 10px;
  cursor: pointer;
  border-radius: 4px;
  margin-bottom: 4px;
  border: 1px solid transparent;
}
.log-file-item:hover { background: #f0f5ff; }
.log-file-item.active { background: #e6f4ff; border-color: #91caff; }
</style>
