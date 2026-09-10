import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '../router'

// 统一请求实例：同源、携带 HttpOnly cookie（portal_session）
const http = axios.create({
  baseURL: '/',
  withCredentials: true,
  timeout: 30000
})

http.interceptors.response.use(
  (res) => res.data,
  (err) => {
    const status = err.response?.status
    const detail = err.response?.data?.detail || err.message || '请求失败'
    const silent = err.config?.silent === true
    // 路由守卫的登录态探测（authCheck）：完全静默，由守卫自行处理跳转
    if (err.config?.authCheck) {
      return Promise.reject(err)
    }
    if (status === 401) {
      // 未登录：清用户态并跳登录页；登录页上的 401（如密码错误）仅提示
      if (router.currentRoute.value.path !== '/login') {
        import('../stores/auth').then(({ useAuthStore }) => {
          useAuthStore().reset()
          router.push('/login')
        })
        ElMessage.error(detail)
      } else if (!silent) {
        ElMessage.error(detail)
      }
    } else if (status === 423) {
      if (!silent) ElMessage.error(`${detail}（账号已锁定）`)
    } else if (status === 429) {
      if (!silent) ElMessage.error(`${detail}（请求过于频繁）`)
    } else if (!silent) {
      ElMessage.error(detail)
    }
    return Promise.reject(err)
  }
)

// ==================== 认证 ====================
export const authApi = {
  login: (data) => http.post('/api/auth/login', data),
  logout: () => http.post('/api/auth/logout'),
  me: () => http.get('/api/auth/me', { silent: true, authCheck: true }),
  changePassword: (data) => http.post('/api/auth/password', data)
}

// ==================== 通道 ====================
export const channelApi = {
  tree: () => http.get('/api/channels/tree')
}

// ==================== 实时播放 ====================
export const playApi = {
  start: (channelId) => http.post(`/api/play/${channelId}`),
  stop: (channelId) => http.post(`/api/play/${channelId}/stop`)
}

// ==================== 录像查询与回放 ====================
export const recordApi = {
  query: (channelId, startTime, endTime) =>
    http.get(`/api/record/${channelId}`, {
      params: { startTime, endTime }
    })
}

export const playbackApi = {
  start: (channelId, data) => http.post(`/api/playback/${channelId}`, data),
  pause: (sessionId) => http.post(`/api/playback/sessions/${sessionId}/pause`),
  resume: (sessionId) => http.post(`/api/playback/sessions/${sessionId}/resume`),
  stop: (sessionId) => http.post(`/api/playback/sessions/${sessionId}/stop`),
  seek: (sessionId, seconds) => http.post(`/api/playback/sessions/${sessionId}/seek`, { seconds }),
  speed: (sessionId, speed) => http.post(`/api/playback/sessions/${sessionId}/speed`, { speed })
}

// ==================== 下载任务 ====================
export const downloadApi = {
  create: (data) => http.post('/api/download-tasks', data),
  list: () => http.get('/api/download-tasks'),
  get: (id) => http.get(`/api/download-tasks/${id}`),
  fileUrl: (id) => `/api/download-tasks/${id}/file`
}

// ==================== 管理端 ====================
export const adminApi = {
  // 机构
  listOrgs: () => http.get('/api/admin/orgs'),
  createOrg: (data) => http.post('/api/admin/orgs', data),
  updateOrg: (id, data) => http.put(`/api/admin/orgs/${id}`, data),
  deleteOrg: (id) => http.delete(`/api/admin/orgs/${id}`),

  // 用户
  listUsers: (params) => http.get('/api/admin/users', { params }),
  createUser: (data) => http.post('/api/admin/users', data),
  updateUser: (id, data) => http.put(`/api/admin/users/${id}`, data),
  resetPassword: (id, newPassword) => http.post(`/api/admin/users/${id}/reset-password`, { newPassword }),
  unlockUser: (id) => http.post(`/api/admin/users/${id}/unlock`),
  listGrants: (userId) => http.get(`/api/admin/users/${userId}/grants`),
  updateGrants: (userId, grants) => http.put(`/api/admin/users/${userId}/grants`, { grants }),

  // 通道
  listChannels: (params) => http.get('/api/admin/channels', { params }),
  updateChannel: (id, displayName) => http.put(`/api/admin/channels/${id}`, { displayName }),
  syncChannels: () => http.post('/api/admin/channels/sync'),

  // 审计
  listAudit: (params) => http.get('/api/admin/audit', { params }),
  auditExportUrl: (params) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
    ).toString()
    return `/api/admin/audit/export${qs ? '?' + qs : ''}`
  },

  // 下载任务（注意参数名小写下划线）
  listTasks: (params) => http.get('/api/admin/download-tasks', { params })
}

export default http
