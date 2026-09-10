<template>
  <div class="pb-page">
    <div class="left-panel">
      <ChannelTree grant="playback" @select="onSelect" />
    </div>
    <div class="right-panel">
      <!-- 查询条件 -->
      <div class="query-bar">
        <template v-if="channel">
          <span class="ch-name">{{ channel.name }}</span>
          <span class="gb-id">{{ channel.channelGbId }}</span>
        </template>
        <span v-else class="tip">在左侧选择要回放的通道</span>
        <div class="query-fields">
          <el-date-picker
            v-model="queryForm.startTime"
            type="datetime"
            placeholder="开始时间"
            format="YYYY-MM-DD HH:mm:ss"
            value-format="YYYY-MM-DD HH:mm:ss"
            :disabled="!channel"
            style="width: 190px"
          />
          <span class="sep">至</span>
          <el-date-picker
            v-model="queryForm.endTime"
            type="datetime"
            placeholder="结束时间"
            format="YYYY-MM-DD HH:mm:ss"
            value-format="YYYY-MM-DD HH:mm:ss"
            :disabled="!channel"
            style="width: 190px"
          />
          <el-button type="primary" :loading="recordsLoading" :disabled="!channel" @click="queryRecords">
            查询录像
          </el-button>
        </div>
      </div>

      <!-- 录像段列表 -->
      <div class="records-box">
        <el-table :data="records" v-loading="recordsLoading" stripe max-height="240" size="default">
          <el-table-column label="开始时间" prop="startTime" min-width="160" />
          <el-table-column label="结束时间" prop="endTime" min-width="160" />
          <el-table-column label="时长" width="100">
            <template #default="{ row }">{{ fmtDuration(row.durationSeconds) }}</template>
          </el-table-column>
          <el-table-column label="类型" width="90">
            <template #default="{ row }">{{ row.type || '-' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="90">
            <template #default="{ row }">
              <el-button
                type="primary"
                link
                :disabled="pbStarting"
                @click="playRecord(row)"
              >
                播放
              </el-button>
            </template>
          </el-table-column>
          <template #empty>暂无录像数据</template>
        </el-table>
      </div>

      <!-- 播放器与控制条 -->
      <div class="player-box">
        <VideoPlayer ref="playerRef" :watermark="true" :display-name="auth.user?.displayName" :org-name="auth.user?.orgName" />
      </div>
      <div class="control-bar">
        <el-button-group>
          <el-button size="small" :disabled="!session || paused" @click="doPause">暂停</el-button>
          <el-button size="small" :disabled="!session || !paused" @click="doResume">恢复</el-button>
          <el-button size="small" type="danger" plain :disabled="!session" @click="doStop">停止</el-button>
        </el-button-group>
        <span class="ctl-label">进度</span>
        <el-slider
          v-model="sliderVal"
          class="seek-slider"
          :max="session ? session.duration : 0"
          :step="1"
          :disabled="!session"
          :format-tooltip="(v) => fmtDuration(v)"
          @change="onSeek"
        />
        <span class="ctl-time">{{ fmtDuration(sliderVal) }} / {{ session ? fmtDuration(session.duration) : '00:00:00' }}</span>
        <span class="ctl-label">倍速</span>
        <el-select v-model="speed" size="small" style="width: 88px" :disabled="!session" @change="onSpeed">
          <el-option v-for="s in SPEED_OPTIONS" :key="s" :label="s + 'x'" :value="s" />
        </el-select>
        <el-button
          size="small"
          type="success"
          plain
          :disabled="!channel || !queryForm.startTime || !queryForm.endTime"
          @click="gotoDownload"
        >
          下载此时段
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
// 录像回放：查询录像段 → 发起回放会话 → 控制条（暂停/恢复/停止/拖动进度/倍速）
import { onBeforeUnmount, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import ChannelTree from '../components/ChannelTree.vue'
import VideoPlayer from '../components/VideoPlayer.vue'
import { recordApi, playbackApi } from '../api'
import { fmtDuration, fmtDateTime } from '../utils/format'
import { SPEED_OPTIONS } from '../constants'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()

const channel = ref(null)
const playerRef = ref(null)
const recordsLoading = ref(false)
const records = ref([])
const pbStarting = ref(false)

const session = ref(null) // { sessionId, duration }
const paused = ref(false)
const sliderVal = ref(0)
const speed = ref(1)

const pad = (n) => String(n).padStart(2, '0')
function defaultStart() {
  const d = new Date()
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} 00:00:00`
}
const queryForm = reactive({ startTime: defaultStart(), endTime: fmtDateTime(new Date()) })

async function stopSession() {
  if (!session.value) return
  const sid = session.value.sessionId
  session.value = null
  paused.value = false
  sliderVal.value = 0
  try {
    await playbackApi.stop(sid)
  } catch (e) {
    /* 忽略 */
  }
}

async function onSelect(ch) {
  channel.value = ch
  records.value = []
  await stopSession()
  playerRef.value?.destroy()
}

async function queryRecords() {
  if (!channel.value) return
  if (!queryForm.startTime || !queryForm.endTime) {
    ElMessage.warning('请选择起止时间')
    return
  }
  if (queryForm.endTime <= queryForm.startTime) {
    ElMessage.warning('结束时间需晚于开始时间')
    return
  }
  recordsLoading.value = true
  try {
    const res = await recordApi.query(channel.value.channelId, queryForm.startTime, queryForm.endTime)
    records.value = res.records || []
    if (!records.value.length) ElMessage.info('该时间段内没有录像')
  } catch (e) {
    records.value = []
  } finally {
    recordsLoading.value = false
  }
}

async function playRecord(row) {
  if (!channel.value) return
  pbStarting.value = true
  try {
    await stopSession()
    const res = await playbackApi.start(channel.value.channelId, {
      startTime: row.startTime,
      endTime: row.endTime
    })
    const url = res.urls?.wsFlv || res.urls?.flv
    if (!url) throw new Error('未获取到回放地址')
    session.value = { sessionId: res.sessionId, duration: row.durationSeconds || 0 }
    sliderVal.value = 0
    speed.value = 1
    paused.value = false
    playerRef.value?.play(url)
  } catch (e) {
    ElMessage.error('发起回放失败')
  } finally {
    pbStarting.value = false
  }
}

async function doPause() {
  if (!session.value) return
  try {
    await playbackApi.pause(session.value.sessionId)
    paused.value = true
  } catch (e) { /* 拦截器已提示 */ }
}

async function doResume() {
  if (!session.value) return
  try {
    await playbackApi.resume(session.value.sessionId)
    paused.value = false
  } catch (e) { /* 拦截器已提示 */ }
}

async function doStop() {
  await stopSession()
  playerRef.value?.destroy()
}

async function onSeek(val) {
  if (!session.value) return
  try {
    await playbackApi.seek(session.value.sessionId, Math.round(val))
  } catch (e) { /* 拦截器已提示 */ }
}

async function onSpeed(val) {
  if (!session.value) return
  try {
    await playbackApi.speed(session.value.sessionId, val)
  } catch (e) { /* 拦截器已提示 */ }
}

// 跳转下载页并预填通道与时间段
function gotoDownload() {
  if (!channel.value) return
  sessionStorage.setItem(
    'downloadPrefill',
    JSON.stringify({
      channelId: channel.value.channelId,
      channelName: channel.value.name,
      startTime: queryForm.startTime,
      endTime: queryForm.endTime
    })
  )
  router.push('/downloads')
}

onBeforeUnmount(() => {
  stopSession()
  playerRef.value?.destroy()
})
</script>

<style scoped>
.pb-page {
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
  gap: 12px;
}
.query-bar {
  background: #fff;
  border-radius: 6px;
  padding: 12px 14px;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.query-fields {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}
.ch-name {
  font-weight: 600;
}
.gb-id,
.tip {
  color: #909399;
  font-size: 13px;
}
.sep {
  color: #909399;
}
.records-box {
  background: #fff;
  border-radius: 6px;
  padding: 8px;
}
.player-box {
  flex: 1;
  min-height: 200px;
  border-radius: 6px;
  overflow: hidden;
}
.control-bar {
  background: #fff;
  border-radius: 6px;
  padding: 10px 14px;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.ctl-label {
  color: #909399;
  font-size: 13px;
}
.seek-slider {
  flex: 1;
  min-width: 160px;
  margin: 0 8px;
}
.ctl-time {
  font-size: 13px;
  color: #606266;
  font-variant-numeric: tabular-nums;
}
</style>
