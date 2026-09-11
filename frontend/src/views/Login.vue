<template>
  <AuthLayout title="欢迎登录">
    <el-form ref="formRef" :model="form" :rules="rules" size="large" class="login-form" @keyup.enter="submit">
      <el-form-item prop="username">
        <el-input v-model="form.username" placeholder="账号" :prefix-icon="User" autocomplete="username" />
      </el-form-item>
      <el-form-item prop="password">
        <el-input
          v-model="form.password"
          type="password"
          show-password
          placeholder="密码"
          :prefix-icon="Lock"
          autocomplete="current-password"
        />
      </el-form-item>
      <el-form-item style="width: 100%">
        <el-button type="primary" class="login-btn" :loading="submitting" @click="submit">
          <span v-if="!submitting">登 录</span>
          <span v-else>登 录 中...</span>
        </el-button>
      </el-form-item>
    </el-form>
  </AuthLayout>
</template>

<script setup>
// 登录页：成功后拉取用户信息，按 redirect 跳转（强制改密由主布局弹窗处理）
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'
import { authApi } from '../api'
import AuthLayout from '../components/AuthLayout.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const formRef = ref(null)
const submitting = ref(false)
const form = reactive({ username: '', password: '' })
const rules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

async function submit() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    await authApi.login({ username: form.username, password: form.password })
    await auth.fetchMe()
    ElMessage.success('登录成功')
    router.push(route.query.redirect || '/')
  } catch (e) {
    /* 失败提示由拦截器统一处理 */
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.login-form {
  width: 100%;
}

/* 输入框聚焦：主色边框 + 柔光 */
.login-form :deep(.el-input__inner) {
  transition: border-color 0.3s, box-shadow 0.3s;
}
.login-form :deep(.el-input__inner:focus) {
  border-color: #409eff;
  box-shadow: 0 0 0 3px rgba(64, 158, 255, 0.15);
}

/* 登录按钮：主色渐变 + 悬浮微光 */
.login-btn {
  width: 100%;
  height: 42px;
  font-size: 14px;
  letter-spacing: 6px;
  border: none;
  background: linear-gradient(90deg, #409eff, #79bbff);
  background-size: 150% 100%;
  box-shadow: 0 6px 14px rgba(64, 158, 255, 0.3);
  transition: all 0.3s;
}
.login-btn:hover,
.login-btn:focus {
  background: linear-gradient(90deg, #409eff, #79bbff);
  background-position: 100% 0;
  box-shadow: 0 8px 18px rgba(64, 158, 255, 0.45);
  transform: translateY(-1px);
}
.login-btn:active {
  transform: translateY(0);
}
</style>
