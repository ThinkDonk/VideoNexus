<template>
  <div class="video-player">
    <div ref="containerRef" class="player-container"></div>
    <Watermark v-if="watermark" :display-name="displayName" :org-name="orgName" />
    <div v-if="!available" class="player-missing">播放器未安装</div>
    <div v-else-if="!url && !playing" class="player-placeholder">请选择通道开始播放</div>
  </div>
</template>

<script setup>
// Jessibuca 播放器封装：暴露 play/destroy；本地 vendor 加载（window.Jessibuca）
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import Watermark from './Watermark.vue'

const props = defineProps({
  url: { type: String, default: '' },
  watermark: { type: Boolean, default: true },
  displayName: { type: String, default: '' },
  orgName: { type: String, default: '' }
})

const containerRef = ref(null)
const playing = ref(false)
const available = typeof window !== 'undefined' && !!window.Jessibuca

let player = null

function createPlayer() {
  if (!available || !containerRef.value) return null
  return new window.Jessibuca({
    container: containerRef.value,
    videoBuffer: 0.2,
    isResize: true,
    text: '',
    loadingText: '加载中…',
    debug: false,
    showBandwidth: false,
    operateBtns: {
      fullscreen: true,
      screenshot: false,
      play: true,
      audio: true,
      record: false
    }
  })
}

// 播放指定地址（自动先销毁旧实例，避免状态残留）
function play(url) {
  if (!available) {
    ElMessage.error('播放器未安装，无法播放')
    return
  }
  destroy()
  player = createPlayer()
  if (!player) return
  player.on('error', (error) => {
    ElMessage.error(`播放器错误：${error}`)
  })
  player.play(url)
  playing.value = true
}

function destroy() {
  if (player) {
    try {
      player.destroy()
    } catch (e) {
      /* 忽略销毁异常 */
    }
    player = null
  }
  playing.value = false
}

onMounted(() => {
  if (props.url && available) play(props.url)
})

onBeforeUnmount(() => {
  destroy()
})

defineExpose({ play, destroy })
</script>

<style scoped>
.video-player {
  position: relative;
  width: 100%;
  height: 100%;
  background: #000;
  overflow: hidden;
}
.player-container {
  width: 100%;
  height: 100%;
}
.player-placeholder,
.player-missing {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #909399;
  font-size: 14px;
  background: #000;
}
.player-missing {
  color: #f56c6c;
  font-size: 16px;
}
</style>
