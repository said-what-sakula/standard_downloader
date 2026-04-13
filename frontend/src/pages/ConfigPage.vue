<template>
  <div style="max-width:900px">
    <h2>配置管理</h2>

    <a-tabs v-model:activeKey="activeTab">
      <!-- ── 来源管理 ── -->
      <a-tab-pane key="sources" tab="来源列表">
        <!-- 国标 / 行标 子标签 -->
        <a-tabs v-model:activeKey="sourceTypeTab" type="card">

          <!-- 国家标准 -->
          <a-tab-pane key="guobiao" tab="国家标准">
            <div style="display:flex; justify-content:flex-end; margin-bottom:12px">
              <a-button type="primary" @click="addSource('guobiao')">＋ 新增国标来源</a-button>
            </div>
            <a-table
              :dataSource="guobiaoSources"
              :columns="sourceColumns"
              :pagination="false"
              row-key="name"
              bordered
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'action'">
                  <a-space>
                    <a-button size="small" @click="editSourceByName(record.name)">编辑</a-button>
                    <a-popconfirm title="确认删除？" @confirm="removeSourceByName(record.name)">
                      <a-button size="small" danger>删除</a-button>
                    </a-popconfirm>
                  </a-space>
                </template>
              </template>
            </a-table>
          </a-tab-pane>

          <!-- 行业标准 -->
          <a-tab-pane key="hangbiao" tab="行业标准">
            <div style="display:flex; justify-content:flex-end; margin-bottom:12px">
              <a-button type="primary" @click="addSource('hangbiao')">＋ 新增行标来源</a-button>
            </div>
            <a-table
              :dataSource="hangbiaoSources"
              :columns="sourceColumns"
              :pagination="false"
              row-key="name"
              bordered
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'action'">
                  <a-space>
                    <a-button size="small" @click="editSourceByName(record.name)">编辑</a-button>
                    <a-popconfirm title="确认删除？" @confirm="removeSourceByName(record.name)">
                      <a-button size="small" danger>删除</a-button>
                    </a-popconfirm>
                  </a-space>
                </template>
              </template>
            </a-table>
          </a-tab-pane>

        </a-tabs>

        <a-button
          type="primary"
          style="margin-top:16px"
          :loading="savingSources"
          @click="saveSources"
        >保存来源列表</a-button>
      </a-tab-pane>

      <!-- ── 存储配置 ── -->
      <a-tab-pane key="storage" tab="存储配置">
        <a-form :model="storageCfg" layout="vertical" style="max-width:560px">
          <a-form-item label="存储模式">
            <a-radio-group v-model:value="storageCfg.mode">
              <a-radio-button value="local">本地</a-radio-button>
              <a-radio-button value="oss">OSS</a-radio-button>
              <a-radio-button value="both">本地 + OSS</a-radio-button>
            </a-radio-group>
            <div style="margin-top:6px; color:#888; font-size:12px">
              本地：文件保存到服务器 download/ 目录；OSS：上传到对象存储；两者同时保留选"本地 + OSS"
            </div>
          </a-form-item>

          <template v-if="storageCfg.mode === 'oss' || storageCfg.mode === 'both'">
            <a-divider>OSS 配置</a-divider>
            <a-form-item label="上传接口 URL">
              <a-input v-model:value="storageCfg.upload_url" placeholder="http://..." />
            </a-form-item>
            <a-form-item label="访问地址前缀（save_path）">
              <a-input v-model:value="storageCfg.save_path" placeholder="https://oss.example.com/" />
            </a-form-item>
            <a-form-item label="Bucket 名称">
              <a-input v-model:value="storageCfg.bucket_name" />
            </a-form-item>
            <a-form-item label="Bucket 路径">
              <a-input v-model:value="storageCfg.bucket_path" placeholder="standard" />
            </a-form-item>
          </template>

          <a-form-item>
            <a-button type="primary" :loading="savingStorage" @click="saveStorage">保存</a-button>
          </a-form-item>
        </a-form>
      </a-tab-pane>

      <!-- ── 服务器配置 ── -->
      <a-tab-pane key="server" tab="服务器配置">
        <a-form :model="serverCfg" layout="vertical" style="max-width:500px">
          <a-form-item label="监听地址">
            <a-input v-model:value="serverCfg.host" />
          </a-form-item>
          <a-form-item label="端口">
            <a-input-number v-model:value="serverCfg.port" :min="1" :max="65535" style="width:100%" />
          </a-form-item>
          <a-form-item label="日志目录">
            <a-input v-model:value="serverCfg.log_dir" />
          </a-form-item>

          <a-divider>Chromium 浏览器路径</a-divider>

          <a-form-item>
            <template #label>
              Chromium 可执行文件路径
              <a-tooltip>
                <template #title>
                  留空时 Playwright 自动使用内置 Chromium。<br/>
                  也可通过环境变量 <b>CHROMIUM_PATH</b> 覆盖（优先级最高）。<br/>
                  Linux 服务器示例：/usr/bin/google-chrome<br/>
                  Windows 示例：C:\...\chrome.exe
                </template>
                <question-circle-outlined style="margin-left:4px; color:#888" />
              </a-tooltip>
            </template>
            <a-input
              v-model:value="serverCfg.chromium_path"
              placeholder="留空 = Playwright 自动检测（推荐服务器部署时留空）"
            />
          </a-form-item>

          <a-form-item>
            <a-button type="primary" :loading="savingServer" @click="saveServer">保存</a-button>
          </a-form-item>
        </a-form>
      </a-tab-pane>
    </a-tabs>

    <!-- 编辑/新增来源弹窗 -->
    <a-modal
      v-model:open="showSourceModal"
      :title="editingName ? '编辑来源' : '新增来源'"
      @ok="confirmSource"
    >
      <a-form :model="sourceForm" layout="vertical">
        <a-form-item label="来源名称" required>
          <a-input v-model:value="sourceForm.name" placeholder="如：AQ-安全生产" />
        </a-form-item>
        <a-form-item label="类型" required>
          <a-radio-group v-model:value="sourceForm.type">
            <a-radio value="guobiao">国家标准</a-radio>
            <a-radio value="hangbiao">行业标准</a-radio>
          </a-radio-group>
        </a-form-item>
        <a-form-item label="列表页 URL" required>
          <a-textarea
            v-model:value="sourceForm.url"
            :rows="3"
            placeholder="https://..."
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import { getConfig, updateConfig, getSources, updateSources } from '../api'

const activeTab     = ref('sources')
const sourceTypeTab = ref('guobiao')

// ── 来源列表 ──────────────────────────────────────────────────────────────────
const sources       = ref<any[]>([])
const savingSources = ref(false)
const showSourceModal = ref(false)
const editingName   = ref('')   // 正在编辑的来源名称（空=新增）
const sourceForm    = reactive({ name: '', type: 'guobiao', url: '' })

const sourceColumns = [
  { title: '名称', dataIndex: 'name', key: 'name' },
  { title: 'URL',  dataIndex: 'url',  key: 'url',  ellipsis: true },
  { title: '操作', key: 'action', width: 120 },
]

const guobiaoSources = computed(() => sources.value.filter(s => s.type === 'guobiao'))
const hangbiaoSources = computed(() => sources.value.filter(s => s.type === 'hangbiao'))

function addSource(type: 'guobiao' | 'hangbiao') {
  editingName.value = ''
  Object.assign(sourceForm, { name: '', type, url: '' })
  showSourceModal.value = true
}

function editSourceByName(name: string) {
  const item = sources.value.find(s => s.name === name)
  if (!item) return
  editingName.value = name
  Object.assign(sourceForm, { ...item })
  showSourceModal.value = true
}

function confirmSource() {
  if (!sourceForm.name || !sourceForm.url) {
    message.warning('名称和 URL 不能为空')
    return
  }
  if (editingName.value) {
    // 编辑：找到原来的项并替换
    const idx = sources.value.findIndex(s => s.name === editingName.value)
    if (idx >= 0) sources.value[idx] = { ...sourceForm }
  } else {
    // 新增：检查名称重复
    if (sources.value.some(s => s.name === sourceForm.name)) {
      message.warning('来源名称已存在')
      return
    }
    sources.value.push({ ...sourceForm })
  }
  showSourceModal.value = false
}

function removeSourceByName(name: string) {
  const idx = sources.value.findIndex(s => s.name === name)
  if (idx >= 0) sources.value.splice(idx, 1)
}

async function saveSources() {
  savingSources.value = true
  try {
    await updateSources(sources.value)
    message.success('来源列表已保存')
  } catch {
    message.error('保存失败')
  } finally {
    savingSources.value = false
  }
}

// ── 存储配置 ──────────────────────────────────────────────────────────────────
const storageCfg   = reactive({ mode: 'oss', upload_url: '', save_path: '', bucket_name: '', bucket_path: '' })
const savingStorage = ref(false)

async function saveStorage() {
  savingStorage.value = true
  try {
    const cfg = await getConfig()
    const existing = cfg.data ?? {}
    await updateConfig({ ...existing, storage: { ...storageCfg } })
    message.success('存储配置已保存')
  } catch {
    message.error('保存失败')
  } finally {
    savingStorage.value = false
  }
}

// ── 服务器配置 ────────────────────────────────────────────────────────────────
const serverCfg    = reactive({ host: '127.0.0.1', port: 8000, log_dir: 'logs', chromium_path: '' })
const savingServer = ref(false)

async function saveServer() {
  savingServer.value = true
  try {
    const cfg = await getConfig()
    const existing = cfg.data ?? {}
    const { chromium_path, ...serverOnly } = serverCfg
    await updateConfig({ ...existing, server: serverOnly, chromium_path })
    message.success('服务器配置已保存')
  } catch {
    message.error('保存失败')
  } finally {
    savingServer.value = false
  }
}

onMounted(async () => {
  try {
    const [srcRes, cfgRes] = await Promise.all([getSources(), getConfig()])
    sources.value = srcRes.data ?? []
    const data = cfgRes.data ?? {}
    Object.assign(serverCfg, data.server ?? {})
    serverCfg.chromium_path = data.chromium_path ?? ''
    Object.assign(storageCfg, { mode: 'oss', upload_url: '', save_path: '', bucket_name: '', bucket_path: '', ...(data.storage ?? {}) })
  } catch {
    message.error('加载配置失败')
  }
})
</script>
