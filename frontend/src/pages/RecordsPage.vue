<template>
  <div>
    <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:16px">
      <h2 style="margin:0">标准库</h2>
    </div>

    <!-- 搜索栏 -->
    <a-card style="margin-bottom:16px">
      <a-form layout="inline" :model="query">
        <a-form-item label="关键词">
          <a-input
            v-model:value="query.keyword"
            placeholder="标准号 / 标准名称"
            style="width:220px"
            allow-clear
            @pressEnter="doSearch"
          />
        </a-form-item>
        <a-form-item label="类型">
          <a-select v-model:value="query.source_type" style="width:120px" allow-clear placeholder="全部">
            <a-select-option value="guobiao">国家标准</a-select-option>
            <a-select-option value="hangbiao">行业标准</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="状态">
          <a-select v-model:value="query.status" style="width:120px" allow-clear placeholder="全部">
            <a-select-option value="SUCCESS">已下载</a-select-option>
            <a-select-option value="NO_FULL_TEXT">无全文</a-select-option>
            <a-select-option value="ABOLISHED">已废止</a-select-option>
            <a-select-option value="ADOPTED">被代替</a-select-option>
            <a-select-option value="FAILED">失败</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item>
          <a-space>
            <a-button type="primary" :loading="loading" @click="doSearch">搜索</a-button>
            <a-button @click="doReset">重置</a-button>
          </a-space>
        </a-form-item>
      </a-form>
    </a-card>

    <!-- 结果表格 -->
    <a-card>
      <a-table
        :columns="columns"
        :data-source="records"
        :loading="loading"
        :pagination="pagination"
        row-key="id"
        size="middle"
        @change="handleTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'source_type'">
            <a-tag :color="record.source_type === 'guobiao' ? 'blue' : 'green'" style="margin:0">
              {{ record.source_type === 'guobiao' ? '国标' : '行标' }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'status'">
            <a-tag :color="STATUS_COLOR[record.status]" style="margin:0">
              {{ STATUS_LABEL[record.status] ?? record.status }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'action'">
            <a-space size="small">
              <a-button type="link" size="small" style="padding:0" @click="openDetail(record)">详情</a-button>
              <a-button
                type="link" size="small" style="padding:0"
                :disabled="!record.oss_url"
                @click="record.oss_url && downloadFile(record)"
              >下载</a-button>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- 详情抽屉 -->
    <a-drawer
      v-model:open="drawerOpen"
      title="标准详情"
      :width="700"
      destroy-on-close
    >
      <a-spin :spinning="detailLoading">
        <template v-if="detail">

          <!-- 文件操作区 -->
          <a-card size="small" style="margin-bottom:16px; background:#fafafa">
            <a-space wrap>
              <a-button
                v-if="detail.oss_url"
                type="primary"
                @click="downloadFile(detail)"
              >下载文件</a-button>
              <a-button
                v-if="isPdf(detail.oss_url)"
                @click="previewFile(detail)"
              >在线预览 PDF</a-button>
              <a-tag v-if="!detail.oss_url" color="default">暂无文件</a-tag>
            </a-space>
          </a-card>

          <!-- 基本信息 -->
          <a-descriptions
            title="基本信息"
            bordered
            size="small"
            :column="2"
            style="margin-bottom:16px"
          >
            <a-descriptions-item label="标准号">{{ detail.std_no }}</a-descriptions-item>
            <a-descriptions-item label="类型">
              <a-tag :color="detail.source_type === 'guobiao' ? 'blue' : 'green'">
                {{ detail.source_type === 'guobiao' ? '国家标准' : '行业标准' }}
              </a-tag>
            </a-descriptions-item>
            <a-descriptions-item label="标准名称" :span="2">{{ detail.std_name }}</a-descriptions-item>
            <a-descriptions-item label="来源">{{ detail.source_name }}</a-descriptions-item>
            <a-descriptions-item label="下载状态">
              <a-tag :color="STATUS_COLOR[detail.status]">
                {{ STATUS_LABEL[detail.status] ?? detail.status }}
              </a-tag>
            </a-descriptions-item>
            <a-descriptions-item label="更新时间" :span="2">{{ detail.updated_at }}</a-descriptions-item>
          </a-descriptions>

          <!-- 行标详情 -->
          <template v-if="detail.source_type === 'hangbiao' && detail.detail">
            <a-descriptions
              title="标准信息"
              bordered
              size="small"
              :column="2"
              style="margin-bottom:16px"
            >
              <a-descriptions-item label="行业分类">
                {{ detail.detail.industry_code }} {{ detail.detail.industry_name }}
              </a-descriptions-item>
              <a-descriptions-item label="行业大类">{{ detail.detail.industry_category ?? '-' }}</a-descriptions-item>
              <a-descriptions-item label="标准分类">{{ detail.detail.mandatory_type ?? '-' }}</a-descriptions-item>
              <a-descriptions-item label="当前状态">
                <a-tag v-if="detail.detail.status" :color="STD_STATUS_COLOR[detail.detail.status] ?? 'default'" style="margin:0">
                  {{ detail.detail.status }}
                </a-tag>
                <span v-else>-</span>
              </a-descriptions-item>
              <a-descriptions-item label="发布日期">{{ detail.detail.publish_date ?? '-' }}</a-descriptions-item>
              <a-descriptions-item label="实施日期">{{ detail.detail.implement_date ?? '-' }}</a-descriptions-item>
              <a-descriptions-item label="废止日期">{{ detail.detail.abolish_date ?? '-' }}</a-descriptions-item>
              <a-descriptions-item label="中国标准分类号">{{ detail.detail.ccs ?? '-' }}</a-descriptions-item>
              <a-descriptions-item label="国际标准分类号">{{ detail.detail.ics ?? '-' }}</a-descriptions-item>
              <a-descriptions-item label="归口单位" :span="2">{{ detail.detail.org_unit ?? '-' }}</a-descriptions-item>
              <a-descriptions-item label="主管部门" :span="2">{{ detail.detail.department ?? '-' }}</a-descriptions-item>
              <a-descriptions-item label="备案号">{{ detail.detail.record_no ?? '-' }}</a-descriptions-item>
              <a-descriptions-item label="备案公告">{{ detail.detail.record_notice ?? '-' }}</a-descriptions-item>
              <a-descriptions-item v-if="detail.detail.drafting_orgs" label="起草单位" :span="2">
                {{ detail.detail.drafting_orgs }}
              </a-descriptions-item>
              <a-descriptions-item v-if="detail.detail.drafting_persons" label="起草人" :span="2">
                {{ detail.detail.drafting_persons }}
              </a-descriptions-item>
            </a-descriptions>
            <a-descriptions
              v-if="detail.detail.scope"
              bordered
              size="small"
              :column="1"
              style="margin-bottom:16px"
            >
              <a-descriptions-item label="适用范围">{{ detail.detail.scope }}</a-descriptions-item>
            </a-descriptions>
            <a-descriptions
              v-if="detail.detail.replaced_stds?.length"
              bordered
              size="small"
              :column="1"
              style="margin-bottom:16px"
            >
              <a-descriptions-item label="代替标准">
                <a-tag v-for="s in detail.detail.replaced_stds" :key="s" style="margin:2px">{{ s }}</a-tag>
              </a-descriptions-item>
            </a-descriptions>
          </template>

          <!-- 国标详情 -->
          <template v-if="detail.source_type === 'guobiao' && detail.detail">
            <a-descriptions
              title="标准信息"
              bordered
              size="small"
              :column="2"
              style="margin-bottom:16px"
            >
              <a-descriptions-item label="中文名称" :span="2">{{ detail.detail.std_name_zh ?? '-' }}</a-descriptions-item>
              <a-descriptions-item v-if="detail.detail.std_name_en" label="英文名称" :span="2">
                {{ detail.detail.std_name_en }}
              </a-descriptions-item>
              <a-descriptions-item label="标准分类">{{ detail.detail.mandatory_type ?? '-' }}</a-descriptions-item>
              <a-descriptions-item label="当前状态">
                <a-tag v-if="detail.detail.status" :color="STD_STATUS_COLOR[detail.detail.status] ?? 'default'" style="margin:0">
                  {{ detail.detail.status }}
                </a-tag>
                <span v-else>-</span>
              </a-descriptions-item>
              <a-descriptions-item label="发布日期">{{ detail.detail.publish_date ?? '-' }}</a-descriptions-item>
              <a-descriptions-item label="实施日期">{{ detail.detail.implement_date ?? '-' }}</a-descriptions-item>
              <a-descriptions-item label="中国标准分类号">{{ detail.detail.ccs ?? '-' }}</a-descriptions-item>
              <a-descriptions-item label="国际标准分类号">{{ detail.detail.ics ?? '-' }}</a-descriptions-item>
              <a-descriptions-item label="归口部门" :span="2">{{ detail.detail.org_department ?? '-' }}</a-descriptions-item>
              <a-descriptions-item label="主管部门" :span="2">{{ detail.detail.department ?? '-' }}</a-descriptions-item>
              <a-descriptions-item v-if="detail.detail.publisher" label="发布单位" :span="2">
                {{ detail.detail.publisher }}
              </a-descriptions-item>
              <a-descriptions-item v-if="detail.detail.note" label="备注" :span="2">
                {{ detail.detail.note }}
              </a-descriptions-item>
            </a-descriptions>
          </template>

          <!-- 无详情提示 -->
          <a-empty
            v-if="!detail.detail"
            description="暂无扩展信息（标准详情未采集）"
            style="padding:24px 0"
          />
        </template>
      </a-spin>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { searchRecords, getRecordDetail } from '../api'

// ── 下载状态映射 ──────────────────────────────────────────────────────────────
const STATUS_LABEL: Record<string, string> = {
  SUCCESS:      '已下载',
  NO_FULL_TEXT: '无全文',
  ABOLISHED:    '已废止',
  ADOPTED:      '被代替',
  FAILED:       '失败',
}
const STATUS_COLOR: Record<string, string> = {
  SUCCESS:      'success',
  NO_FULL_TEXT: 'warning',
  ABOLISHED:    'default',
  ADOPTED:      'purple',
  FAILED:       'error',
}

// ── 标准自身状态（详情页 detail.status）────────────────────────────────────────
const STD_STATUS_COLOR: Record<string, string> = {
  '现行':    'success',
  '即将实施': 'processing',
  '废止':    'default',
  '采标':    'blue',
}

// ── 表格列定义 ────────────────────────────────────────────────────────────────
const columns = [
  { title: '标准号',   dataIndex: 'std_no',      key: 'std_no',      width: 160, ellipsis: true },
  { title: '标准名称', dataIndex: 'std_name',     key: 'std_name',    ellipsis: true },
  { title: '类型',     dataIndex: 'source_type',  key: 'source_type', width: 80  },
  { title: '来源',     dataIndex: 'source_name',  key: 'source_name', width: 140, ellipsis: true },
  { title: '状态',     dataIndex: 'status',       key: 'status',      width: 90  },
  { title: '更新时间', dataIndex: 'updated_at',   key: 'updated_at',  width: 165, ellipsis: true },
  { title: '操作',     key: 'action',             width: 100, fixed: 'right' },
]

// ── 检索状态 ──────────────────────────────────────────────────────────────────
const query = reactive({ keyword: '', source_type: undefined as string | undefined, status: undefined as string | undefined })
const loading = ref(false)
const records = ref<any[]>([])
const pagination = reactive({ current: 1, pageSize: 20, total: 0, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` })

async function doSearch(resetPage = true) {
  if (resetPage) pagination.current = 1
  loading.value = true
  try {
    const res = await searchRecords({
      keyword:     query.keyword || undefined,
      source_type: query.source_type || undefined,
      status:      query.status || undefined,
      page:        pagination.current,
      page_size:   pagination.pageSize,
    })
    records.value  = res.data.items
    pagination.total = res.data.total
  } catch {
    message.error('查询失败')
  } finally {
    loading.value = false
  }
}

function doReset() {
  query.keyword     = ''
  query.source_type = undefined
  query.status      = undefined
  doSearch()
}

function handleTableChange(pag: any) {
  pagination.current  = pag.current
  pagination.pageSize = pag.pageSize
  doSearch(false)
}

// ── 详情抽屉 ──────────────────────────────────────────────────────────────────
const drawerOpen    = ref(false)
const detailLoading = ref(false)
const detail        = ref<any>(null)

async function openDetail(row: any) {
  drawerOpen.value    = true
  detailLoading.value = true
  detail.value        = null
  try {
    const res = await getRecordDetail(row.id)
    detail.value = res.data
  } catch {
    message.error('获取详情失败')
    drawerOpen.value = false
  } finally {
    detailLoading.value = false
  }
}

function isPdf(url: string | null | undefined): boolean {
  return !!url && url.toLowerCase().endsWith('.pdf')
}

/** 在新标签页通过后端代理预览（强制 inline，浏览器直接渲染 PDF） */
function previewFile(rec: any) {
  window.open(`/api/records/${rec.id}/preview`, '_blank')
}

/** 直接跳转 OSS URL 下载 */
function downloadFile(rec: any) {
  window.open(rec.oss_url, '_blank')
}

// ── 初始化 ────────────────────────────────────────────────────────────────────
onMounted(() => doSearch())
</script>
