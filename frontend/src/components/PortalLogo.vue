<template>
  <div class="portal-logo" :class="{ compact }">
    <svg class="mark" viewBox="0 0 48 48" role="img" aria-label="VideoNexus">
      <defs>
        <linearGradient :id="gradId" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="#409eff" />
          <stop offset="100%" stop-color="#79bbff" />
        </linearGradient>
      </defs>
      <rect width="48" height="48" rx="12" :fill="`url(#${gradId})`" />
      <!-- 摄像头机身 -->
      <rect x="9" y="17" width="21" height="15" rx="3.5" fill="#ffffff" />
      <!-- 镜头 -->
      <circle cx="19.5" cy="24.5" r="4.6" fill="#16385f" />
      <circle cx="19.5" cy="24.5" r="1.9" fill="#8ecbff" />
      <!-- 取景楔形 -->
      <path d="M31 21.8l7-3.1v11.6l-7-3.1z" fill="#ffffff" />
    </svg>
    <span v-if="!compact" class="word">VideoNexus</span>
  </div>
</template>

<script setup>
// 门户占位 logo（自绘 SVG，不依赖任何外部图片资源）。
// 替换为贵司 logo 时，只需改本文件的 SVG 或改用 <img>，其余组件无需改动。
const props = defineProps({
  // 紧凑模式：只显示图形、不显示文字（用于侧边栏折叠等场景）
  compact: { type: Boolean, default: false }
})

// 同页多实例时避免 SVG 渐变 id 冲突
const gradId = `vn-logo-grad-${Math.random().toString(36).slice(2, 9)}`
</script>

<style scoped>
.portal-logo {
  display: inline-flex;
  align-items: center;
  gap: 12px;
}
.mark {
  width: 48px;
  height: 48px;
  flex-shrink: 0;
  filter: drop-shadow(0 6px 14px rgba(64, 158, 255, 0.35));
}
.compact .mark {
  width: 36px;
  height: 36px;
}
.word {
  font-size: 24px;
  font-weight: 700;
  letter-spacing: 1px;
  color: #1f2d3d;
  line-height: 1;
}
</style>
