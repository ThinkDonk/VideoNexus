<template>
  <div ref="rootRef" class="watermark" :style="posStyle">
    <div class="wm-line">{{ prefix }}</div>
    <div class="wm-line">{{ timeText }}</div>
  </div>
</template>

<script setup>
// 播放器水印：用户信息 + 每秒刷新时间，30 秒轮换四角，防止 devtools 删除
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps({
  displayName: { type: String, default: '' },
  orgName: { type: String, default: '' }
})

const rootRef = ref(null)
const now = ref(new Date())
const cornerIdx = ref(0) // 0左上 1右上 2左下 3右下

const CORNERS = [
  { top: '12px', left: '12px' },
  { top: '12px', right: '12px' },
  { bottom: '12px', left: '12px' },
  { bottom: '12px', right: '12px' }
]

const pad = (n) => String(n).padStart(2, '0')
const timeText = computed(() => {
  const d = now.value
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
})
const prefix = computed(() => {
  const name = props.displayName || ''
  const org = props.orgName || ''
  return org ? `${name}(${org})` : name
})
const posStyle = computed(() => CORNERS[cornerIdx.value % 4])

let timeTimer = null
let moveTimer = null
let observer = null
let destroyed = false

function tick() {
  now.value = new Date()
}

onMounted(() => {
  timeTimer = setInterval(tick, 1000)
  moveTimer = setInterval(() => {
    cornerIdx.value = (cornerIdx.value + 1) % 4
  }, 30000)
  // 监听自身被从父容器移除（防 devtools 删节点），立即追加回去
  const el = rootRef.value
  const parent = el?.parentElement
  if (el && parent && window.MutationObserver) {
    observer = new MutationObserver((muts) => {
      if (destroyed) return
      for (const m of muts) {
        if (m.type !== 'childList') continue
        for (const n of m.removedNodes) {
          if (n === el) {
            parent.appendChild(el)
            return
          }
        }
      }
    })
    observer.observe(parent, { childList: true })
  }
})

onBeforeUnmount(() => {
  destroyed = true
  clearInterval(timeTimer)
  clearInterval(moveTimer)
  if (observer) observer.disconnect()
})
</script>

<style scoped>
.watermark {
  position: absolute;
  z-index: 20;
  pointer-events: none;
  user-select: none;
  text-align: left;
  line-height: 1.5;
  transition: all 0.4s ease;
}
.wm-line {
  color: rgba(255, 255, 255, 0.75);
  font-size: 14px;
  font-weight: 600;
  white-space: nowrap;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.9), 0 0 6px rgba(0, 0, 0, 0.6);
  letter-spacing: 0.5px;
}
</style>
