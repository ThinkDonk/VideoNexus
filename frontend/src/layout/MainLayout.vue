<template>
  <el-container class="layout">
    <el-aside width="200px" class="aside">
      <div class="logo">
        <el-icon :size="22"><VideoCamera /></el-icon>
        <span>视频监管门户</span>
      </div>
      <el-menu :default-active="activeMenu" router background-color="#001529" text-color="#a6adb4" active-text-color="#ffffff" class="menu">
        <el-menu-item index="/live">
          <el-icon><VideoPlay /></el-icon><span>实时预览</span>
        </el-menu-item>
        <el-menu-item index="/playback">
          <el-icon><VideoCameraFilled /></el-icon><span>录像回放</span>
        </el-menu-item>
        <el-menu-item index="/downloads">
          <el-icon><Download /></el-icon><span>录像下载</span>
        </el-menu-item>
        <template v-if="auth.canAccessAdmin">
          <div class="menu-group-title">管理端</div>
          <el-menu-item v-if="auth.isAdmin" index="/admin/orgs">
            <el-icon><OfficeBuilding /></el-icon><span>机构管理</span>
          </el-menu-item>
          <el-menu-item v-if="auth.isAdmin" index="/admin/users">
            <el-icon><User /></el-icon><span>用户管理</span>
          </el-menu-item>
          <el-menu-item v-if="auth.isAdmin" index="/admin/channels">
            <el-icon><Connection /></el-icon><span>通道台账</span>
          </el-menu-item>
          <el-menu-item v-if="auth.isAdmin" index="/admin/grants">
            <el-icon><Key /></el-icon><span>授权管理</span>
          </el-menu-item>
          <el-menu-item index="/admin/tasks">
            <el-icon><Tickets /></el-icon><span>下载任务</span>
          </el-menu-item>
          <el-menu-item index="/admin/audit">
            <el-icon><Document /></el-icon><span>审计查询</span>
          </el-menu-item>
        </template>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header" height="56px">
        <div class="page-title">{{ route.meta.title || '' }}</div>
        <el-dropdown @command="onCommand">
          <span class="user-chip">
            <el-icon><UserFilled /></el-icon>
            {{ auth.user?.displayName || auth.user?.username }}
            <span v-if="auth.user?.orgName" class="org">（{{ auth.user.orgName }}）</span>
            <el-tag size="small" type="info" class="role-tag">{{ roleLabel(auth.role) }}</el-tag>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="password">修改密码</el-dropdown-item>
              <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>

    <!-- 首次登录强制改密：不可关闭 -->
    <el-dialog
      v-model="pwdDialog"
      title="首次登录请修改密码"
      width="440px"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      :show-close="!auth.mustChangePassword"
    >
      <el-alert v-if="auth.mustChangePassword" type="warning" :closable="false" title="安全要求：修改密码后才能继续使用系统" class="pwd-alert" />
      <el-form ref="pwdFormRef" :model="pwdForm" :rules="pwdRules" label-width="90px">
        <el-form-item label="原密码" prop="oldPassword">
          <el-input v-model="pwdForm.oldPassword" type="password" show-password placeholder="请输入原密码" />
        </el-form-item>
        <el-form-item label="新密码" prop="newPassword">
          <el-input v-model="pwdForm.newPassword" type="password" show-password placeholder="至少 8 位" />
        </el-form-item>
        <el-form-item label="确认新密码" prop="confirm">
          <el-input v-model="pwdForm.confirm" type="password" show-password placeholder="再次输入新密码" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button v-if="!auth.mustChangePassword" @click="pwdDialog = false">取消</el-button>
        <el-button type="primary" :loading="pwdSubmitting" @click="submitPassword">确定修改</el-button>
      </template>
    </el-dialog>
  </el-container>
</template>

<script setup>
// 主布局：侧边菜单按角色过滤；顶部用户信息；强制/主动修改密码
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  VideoCamera, VideoPlay, VideoCameraFilled, Download, OfficeBuilding,
  User, Connection, Key, Tickets, Document, UserFilled
} from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'
import { authApi } from '../api'
import { roleLabel } from '../constants'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const activeMenu = computed(() => route.path)

const pwdDialog = ref(false)
const pwdSubmitting = ref(false)
const pwdFormRef = ref(null)
const pwdForm = reactive({ oldPassword: '', newPassword: '', confirm: '' })
const pwdRules = {
  oldPassword: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 8, message: '新密码至少 8 位', trigger: 'blur' }
  ],
  confirm: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    {
      validator: (rule, value, cb) => {
        if (value !== pwdForm.newPassword) cb(new Error('两次输入的密码不一致'))
        else cb()
      },
      trigger: 'blur'
    }
  ]
}

// 首次登录（mustChangePassword）强制弹出
watch(
  () => auth.mustChangePassword,
  (v) => {
    if (v) pwdDialog.value = true
  },
  { immediate: true }
)

async function submitPassword() {
  const valid = await pwdFormRef.value.validate().catch(() => false)
  if (!valid) return
  pwdSubmitting.value = true
  try {
    await authApi.changePassword({
      oldPassword: pwdForm.oldPassword,
      newPassword: pwdForm.newPassword
    })
    ElMessage.success('密码修改成功')
    pwdDialog.value = false
    pwdForm.oldPassword = ''
    pwdForm.newPassword = ''
    pwdForm.confirm = ''
    await auth.fetchMe() // 刷新 mustChangePassword 状态
  } catch (e) {
    /* 错误提示由拦截器统一处理 */
  } finally {
    pwdSubmitting.value = false
  }
}

function onCommand(cmd) {
  if (cmd === 'password') {
    pwdDialog.value = true
  } else if (cmd === 'logout') {
    ElMessageBox.confirm('确定退出登录？', '提示', { type: 'warning' })
      .then(async () => {
        try {
          await authApi.logout()
        } catch (e) {
          /* 忽略 */
        }
        auth.reset()
        router.push('/login')
      })
      .catch(() => {})
  }
}
</script>

<style scoped>
.layout {
  height: 100vh;
}
.aside {
  background: #001529;
  display: flex;
  flex-direction: column;
}
.logo {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  flex-shrink: 0;
}
.menu {
  border-right: none;
  flex: 1;
  overflow-y: auto;
}
.menu-group-title {
  padding: 14px 20px 6px;
  color: #5a6470;
  font-size: 12px;
}
.header {
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #e4e7ed;
}
.page-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}
.user-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  color: #303133;
  font-size: 14px;
  outline: none;
}
.org {
  color: #909399;
}
.role-tag {
  margin-left: 4px;
}
.main {
  padding: 16px;
  overflow: auto;
}
.pwd-alert {
  margin-bottom: 16px;
}
</style>
