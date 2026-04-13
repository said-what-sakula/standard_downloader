import axios from 'axios'

const api = axios.create({
  baseURL: (import.meta as any).env?.VITE_API_BASE ?? '',
  timeout: 15000,
})

// ── 下载器 ───────────────────────────────────────────────────────────────────
export const getDownloaders   = ()        => api.get('/api/downloaders')
export const startDownloader  = (id: string) => api.post(`/api/downloaders/${id}/start`)
export const stopDownloader   = (id: string) => api.post(`/api/downloaders/${id}/stop`)
export const getDownloaderStatus = (id: string) => api.get(`/api/downloaders/${id}/status`)

// ── 日志 ─────────────────────────────────────────────────────────────────────
export const getLogHistory  = (id: string)                    => api.get(`/api/logs/${id}/history`)
export const getLogFile     = (id: string, filename: string, full = false)  => api.get(`/api/logs/${id}/file/${filename}`, { params: full ? { full: true } : {} })
export const clearLog       = (id: string, filename: string)  => api.delete(`/api/logs/${id}/clear/${filename}`)

export const createSSE = (id: string): EventSource => {
  return new EventSource(`/api/logs/${id}/stream`)
}

// ── 配置 ─────────────────────────────────────────────────────────────────────
export const getConfig     = ()              => api.get('/api/config')
export const updateConfig  = (data: object)  => api.put('/api/config', data)
export const getSources    = ()              => api.get('/api/config/sources')
export const updateSources = (data: object[]) => api.put('/api/config/sources', data)

// ── 标准库 ────────────────────────────────────────────────────────────────────
export const searchRecords = (params: {
  keyword?: string; source_type?: string; status?: string;
  page?: number; page_size?: number;
}) => api.get('/api/records', { params })
export const getRecordDetail = (id: number) => api.get(`/api/records/${id}`)

// ── 定时任务 ──────────────────────────────────────────────────────────────────
export const getJobs    = ()              => api.get('/api/schedule')
export const createJob  = (data: object)  => api.post('/api/schedule', data)
export const deleteJob  = (id: string)   => api.delete(`/api/schedule/${id}`)
export const pauseJob   = (id: string)   => api.post(`/api/schedule/${id}/pause`)
export const resumeJob  = (id: string)   => api.post(`/api/schedule/${id}/resume`)

export default api
