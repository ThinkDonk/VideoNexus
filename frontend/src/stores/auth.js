import { defineStore } from 'pinia'
import { authApi } from '../api'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null, // {id, username, displayName, role, orgId, orgName, mustChangePassword}
    fetched: false
  }),
  getters: {
    role: (s) => s.user?.role || '',
    isAdmin: (s) => s.user?.role === 'ADMIN',
    isAuditor: (s) => s.user?.role === 'AUDITOR',
    // 管理端可见（读：ADMIN/AUDITOR）
    canAccessAdmin: (s) => s.user?.role === 'ADMIN' || s.user?.role === 'AUDITOR',
    mustChangePassword: (s) => !!s.user?.mustChangePassword
  },
  actions: {
    async fetchMe() {
      try {
        this.user = await authApi.me()
      } catch (e) {
        this.user = null
      } finally {
        this.fetched = true
      }
      return this.user
    },
    reset() {
      this.user = null
      this.fetched = false
    }
  }
})
