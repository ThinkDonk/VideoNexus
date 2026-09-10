import { createRouter, createWebHistory } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'

// 角色约定：ADMIN 全部；AUDITOR 仅审计查询+任务；BANK_USER 仅业务页
const routes = [
  { path: '/login', name: 'login', component: () => import('../views/Login.vue'), meta: { title: '登录' } },
  {
    path: '/',
    component: () => import('../layout/MainLayout.vue'),
    redirect: '/live',
    children: [
      { path: 'live', name: 'live', component: () => import('../views/Live.vue'), meta: { title: '实时预览' } },
      { path: 'playback', name: 'playback', component: () => import('../views/Playback.vue'), meta: { title: '录像回放' } },
      { path: 'downloads', name: 'downloads', component: () => import('../views/Downloads.vue'), meta: { title: '录像下载' } },
      { path: 'admin/orgs', name: 'admin-orgs', component: () => import('../views/admin/Orgs.vue'), meta: { title: '机构管理', roles: ['ADMIN'] } },
      { path: 'admin/users', name: 'admin-users', component: () => import('../views/admin/Users.vue'), meta: { title: '用户管理', roles: ['ADMIN'] } },
      { path: 'admin/channels', name: 'admin-channels', component: () => import('../views/admin/Channels.vue'), meta: { title: '通道台账', roles: ['ADMIN'] } },
      { path: 'admin/grants', name: 'admin-grants', component: () => import('../views/admin/Grants.vue'), meta: { title: '授权管理', roles: ['ADMIN'] } },
      { path: 'admin/tasks', name: 'admin-tasks', component: () => import('../views/admin/Tasks.vue'), meta: { title: '下载任务', roles: ['ADMIN', 'AUDITOR'] } },
      { path: 'admin/audit', name: 'admin-audit', component: () => import('../views/admin/Audit.vue'), meta: { title: '审计查询', roles: ['ADMIN', 'AUDITOR'] } }
    ]
  },
  { path: '/:pathMatch(.*)*', redirect: '/live' }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 全局守卫：未登录先拉取用户态；按角色过滤路由
router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.fetched) {
    await auth.fetchMe()
  }
  if (!auth.user) {
    if (to.path === '/login') return true
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  if (to.path === '/login') return { path: '/' }
  const roles = to.meta.roles
  if (roles && !roles.includes(auth.role)) {
    ElMessage.error('无权限访问该页面')
    return { path: '/live' }
  }
  return true
})

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} - 视频监管门户` : '视频监管门户'
})

export default router
