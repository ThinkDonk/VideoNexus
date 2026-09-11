<template>
  <div class="auth-page">
    <!-- 左侧品牌区：深蓝渐变 + 科技网格 + 主色光斑 -->
    <div class="auth-left">
      <div class="auth-left-content">
        <div class="auth-brand-title">{{ brandName }}</div>
        <div class="auth-brand-subtitle">{{ brandSubtitle }}</div>
        <div class="auth-brand-divider"></div>
        <div class="auth-brand-slogan">{{ slogan }}</div>
      </div>
    </div>

    <!-- 右侧表单区 -->
    <div class="auth-right">
      <div class="auth-form-area">
        <div class="auth-form-header">
          <PortalLogo />
          <div class="auth-form-title">{{ title }}</div>
        </div>
        <slot></slot>
        <div class="auth-notice">本系统仅限授权人员使用，所有登录与操作行为均被记录审计</div>
      </div>
      <div class="auth-copyright">Copyright © {{ year }} VideoNexus Contributors</div>
    </div>
  </div>
</template>

<script setup>
// 登录类页面的通用布局：左侧品牌区 + 右侧表单区。
// 文案可通过 props 覆盖；品牌图形见 components/PortalLogo.vue。
import PortalLogo from './PortalLogo.vue'

defineProps({
  title: { type: String, default: '欢迎登录' },
  brandName: { type: String, default: '视频监管门户' },
  brandSubtitle: { type: String, default: 'GB28181 Video Supervision Portal' },
  slogan: { type: String, default: '精准授权，全链审计' }
})

// 版权年份动态取当前年，避免每年手工更新
const year = new Date().getFullYear()
</script>

<style scoped>
/* 整体左右分栏 */
.auth-page {
  display: flex;
  width: 100%;
  height: 100vh;
}

/* 左侧品牌区 */
.auth-left {
  position: relative;
  display: flex;
  flex: 0 0 55%;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: linear-gradient(160deg, #16385f 0%, #0e2a47 45%, #0a1e35 100%);
}

/* 科技感细网格线，边缘淡出 */
.auth-left::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(64, 158, 255, 0.06) 1px, transparent 1px),
    linear-gradient(90deg, rgba(64, 158, 255, 0.06) 1px, transparent 1px);
  background-size: 44px 44px;
  -webkit-mask-image: radial-gradient(ellipse at center, #000 30%, transparent 78%);
  mask-image: radial-gradient(ellipse at center, #000 30%, transparent 78%);
}

/* 主色光斑，缓慢漂浮 */
.auth-left::after {
  content: '';
  position: absolute;
  top: -180px;
  right: -140px;
  width: 560px;
  height: 560px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(64, 158, 255, 0.28) 0%, transparent 65%);
  animation: auth-glow 8s ease-in-out infinite alternate;
}

@keyframes auth-glow {
  0% {
    transform: translate(0, 0) scale(1);
    opacity: 0.7;
  }
  100% {
    transform: translate(-60px, 50px) scale(1.15);
    opacity: 1;
  }
}

.auth-left-content {
  position: relative;
  z-index: 1;
  padding: 0 48px;
  text-align: center;
  animation: auth-fade-up 0.8s ease both;
}

.auth-brand-title {
  font-size: 34px;
  font-weight: 700;
  letter-spacing: 4px;
  color: #ffffff;
}

.auth-brand-subtitle {
  margin-top: 14px;
  font-size: 14px;
  letter-spacing: 3px;
  color: rgba(255, 255, 255, 0.55);
}

.auth-brand-divider {
  width: 56px;
  height: 3px;
  margin: 28px auto;
  border-radius: 2px;
  background: linear-gradient(90deg, #409eff, transparent);
}

.auth-brand-slogan {
  font-size: 18px;
  letter-spacing: 6px;
  color: #79bbff;
}

/* 右侧表单区 */
.auth-right {
  position: relative;
  display: flex;
  flex: 1;
  flex-direction: column;
  background: #ffffff;
}

.auth-form-area {
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  max-width: 420px;
  margin: 0 auto;
  padding: 40px 24px 24px;
  animation: auth-fade-up 0.6s ease both;
}

.auth-form-header {
  width: 100%;
  margin-bottom: 36px;
  text-align: center;
}

.auth-form-title {
  margin-top: 20px;
  font-size: 20px;
  font-weight: 600;
  letter-spacing: 2px;
  color: #1f2d3d;
}

/* 合规提示 */
.auth-notice {
  width: 100%;
  margin-top: 20px;
  font-size: 12px;
  line-height: 1.7;
  color: #a8abb2;
  text-align: center;
}

/* 底部版权 */
.auth-copyright {
  flex-shrink: 0;
  padding: 0 16px 20px;
  font-size: 12px;
  color: #a8abb2;
  text-align: center;
}

@keyframes auth-fade-up {
  from {
    opacity: 0;
    transform: translateY(18px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* 窄屏回退：隐藏品牌区，表单居中，浅色渐变保持层次 */
@media (max-width: 992px) {
  .auth-left {
    display: none;
  }
  .auth-right {
    background: linear-gradient(180deg, #eef4fc 0%, #ffffff 40%);
  }
}
</style>
