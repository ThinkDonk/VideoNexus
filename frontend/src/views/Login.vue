<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-title">
        <el-icon :size="28" color="#409eff"><VideoCamera /></el-icon>
        <h2>视频监管门户</h2>
      </div>
      <div class="login-sub">仓库质押监管视频开放平台</div>
      <el-form ref="formRef" :model="form" :rules="rules" size="large" @keyup.enter="submit">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="用户名" :prefix-icon="User" autocomplete="username" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" show-password placeholder="密码" :prefix-icon="Lock" autocomplete="current-password" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" class="login-btn" :loading="submitting" @click="submit">登 录</el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup>
// 登录页：成功后拉取用户信息，按 redirect 跳转
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock, VideoCamera } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'
import { authApi } from '../api'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const formRef = ref(null)
const submitting = ref(false)
const form = reactive({ username: '', password: '' })
const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
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
.login-page {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1c2b3a 0%, #0e1a26 100%);
}
.login-card {
  width: 380px;
  padding: 36px 32px 28px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
}
.login-title {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
}
.login-title h2 {
  margin: 0;
  font-size: 20px;
  color: #303133;
}
.login-sub {
  text-align: center;
  color: #909399;
  font-size: 13px;
  margin: 8px 0 24px;
}
.login-btn {
  width: 100%;
}
</style>
