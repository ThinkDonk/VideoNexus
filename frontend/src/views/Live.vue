<template>
  <div class="live-page">
    <div class="left-panel">
      <ChannelTree grant="live" @select="onSelect" />
    </div>
    <div class="right-panel">
      <div class="player-header">
        <template v-if="current">
          <span class="ch-name">{{ current.name }}</span>
          <span class="gb-id">国标编号：{{ current.channelGbId }}</span>
          <el-tag size="small" type="success">直播中</el-tag>
        </template>
        <span v-else class="tip">在左侧选择要预览的通道</span>
      </div>
      <div class="player-box">
        <VideoPlayer ref="playerRef" :watermark="true" :display-name="auth.user?.displayName" :org-name="auth.user?.orgName" />
      </div>
    </div>
  </div>
</template>

<script setup>
// 实时预览：切换通道先 stop 旧的再播新的；离开页面/关闭窗口停止播放
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import ChannelTree from '../components/ChannelTree.vue'
import VideoPlayer from '../components/VideoPlayer.vue'
import { playApi } from '../api'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const playerRef = ref(null)
const current = ref(null) // 当前播放的通道节点
const starting = ref(false)

async function stopOld() {
  if (!current.value) return
  const id = current.value.channelId
  current.value = null
  try {
    await playApi.stop(id)
  } catch (e) {
    /* 忽略停止失败 */
  }
}

async function onSelect(channel) {
  if (starting.value) return
  starting.value = true
  const old = current.value
  current.value = channel
  try {
    if (old) {
      try {
        await playApi.stop(old.channelId)
      } catch (e) {
        /* 忽略 */
      }
    }
    const res = await playApi.start(channel.channelId)
    const url = res.urls?.wsFlv || res.urls?.flv
    if (!url) throw new Error('未获取到播放地址')
    playerRef.value?.play(url)
  } catch (e) {
    current.value = null
    ElMessage.error('发起播放失败')
  } finally {
    starting.value = false
  }
}

function onBeforeUnload() {
  if (current.value) {
    navigator.sendBeacon(`/api/play/${current.value.channelId}/stop`)
  }
}

onMounted(() => {
  window.addEventListener('beforeunload', onBeforeUnload)
})

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', onBeforeUnload)
  stopOld()
  playerRef.value?.destroy()
})
</script>

<style scoped>
.live-page {
  display: flex;
  gap: 12px;
  height: calc(100vh - 56px - 32px);
}
.left-panel {
  width: 320px;
  flex-shrink: 0;
  background: #fff;
  border-radius: 6px;
  padding: 12px;
  box-sizing: border-box;
  overflow: hidden;
}
.right-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.player-header {
  background: #fff;
  border-radius: 6px;
  padding: 10px 14px;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.ch-name {
  font-weight: 600;
  font-size: 15px;
}
.gb-id,
.tip {
  color: #909399;
  font-size: 13px;
}
.player-box {
  flex: 1;
  min-height: 0;
  border-radius: 6px;
  overflow: hidden;
}
</style>
