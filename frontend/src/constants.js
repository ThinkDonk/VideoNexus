// 审计动作常量：值 → 中文标签
export const AUDIT_ACTIONS = {
  LOGIN_SUCCESS: '登录成功',
  LOGIN_FAIL: '登录失败',
  LOGIN_LOCKED: '登录锁定',
  LOGOUT: '登出',
  PASSWORD_CHANGE: '修改密码',
  PASSWORD_RESET: '重置密码',
  PLAY_START: '开始播放',
  PLAY_END: '结束播放',
  PLAYBACK_START: '开始回放',
  PLAYBACK_END: '结束回放',
  RECORD_QUERY: '录像查询',
  DOWNLOAD_CREATE: '创建下载',
  DOWNLOAD_START: '开始下载',
  DOWNLOAD_COMPLETE: '下载完成',
  DOWNLOAD_FAIL: '下载失败',
  DOWNLOAD_EXPIRED: '下载过期',
  DOWNLOAD_FILE_FETCH: '获取文件',
  GRANT_ADDED: '新增授权',
  GRANT_UPDATED: '变更授权',
  GRANT_REMOVED: '收回授权',
  ORG_CREATED: '创建机构',
  ORG_UPDATED: '变更机构',
  ORG_DELETED: '删除机构',
  USER_CREATED: '创建用户',
  USER_UPDATED: '变更用户',
  CHANNEL_SYNC: '通道同步',
  CHANNEL_UPDATED: '通道更新',
  STREAM_AUTH_FAIL: '流鉴权失败'
}

// 下载任务状态 → 标签类型与中文
export const TASK_STATUS = {
  PENDING: { label: '等待中', tag: 'info' },
  RUNNING: { label: '进行中', tag: 'primary' },
  COMPLETE: { label: '已完成', tag: 'success' },
  FAILED: { label: '失败', tag: 'danger' },
  EXPIRED: { label: '已过期', tag: 'warning' }
}

// 倍速选项
export const SPEED_OPTIONS = [0.25, 0.5, 1, 2, 4, 8]

export const ROLES = [
  { value: 'BANK_USER', label: '机构用户' },
  { value: 'ADMIN', label: '管理员' },
  { value: 'AUDITOR', label: '审计' }
]

export function roleLabel(role) {
  const hit = ROLES.find((r) => r.value === role)
  return hit ? hit.label : role
}
