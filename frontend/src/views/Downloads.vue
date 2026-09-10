<template>
  <div class="dl-page">
    <div class="toolbar">
      <el-button type="primary" :icon="Plus" @click="openCreate">新建下载任务</el-button>
      <el-button :icon="Refresh" @click="loadTasks">刷新</el-button>
    </div>

    <TaskTable :tasks="tasks" :loading="loading" />

    <!-- 新建下载任务 -->
    <el-dialog v-model="createDialog" title="新建下载任务" width="480px" :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="通道" prop="channelId">
          <el-select v-model="form.channelId" placeholder="仅显示有下载授权的通道" filterable style="width: 100%">
            <el-option-group v-for="dev in channelOptions" :key="dev.deviceId" :label="dev.deviceName">
              <el-option
                v-for="ch in dev.children"
                :key="ch.channelId"
                :label="ch.name"
                :value="ch.channelId"
                :disabled="!ch.grants?.download"
              >
                <span class="opt-dot" :class="ch.online ? 'on' : 'off'"></span>{{ ch.name }}
              </el-option>
            </el-option-group>
          </el-select>
        </el-form-item>
        <el-form-item label="开始时间" prop="startTime">
          <el-date-picker
            v-model="form.startTime"
            type="datetime"
            placeholder="选择开始时间"
            format="YYYY-MM-DD HH:mm:ss"
            value-format="YYYY-MM-DD HH:mm:ss"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="结束时间" prop="endTime">
          <el-date-picker
            v-model="form.endTime"
            type="datetime"
            placeholder="选择结束时间"
            format="YYYY-MM-DD HH:mm:ss"
            value-format="YYYY-MM-DD HH:mm:ss"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item>
          <span class="form-tip">下载时段最长 4 小时</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialog = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitCreate">提交任务</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
// 录像下载：创建任务（时段≤4小时）+ 任务列表轮询刷新
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import TaskTable from '../components/TaskTable.vue'
import { downloadApi, channelApi } from '../api'

const tasks = ref([])
const loading = ref(false)
const createDialog = ref(false)
const submitting = ref(false)
const formRef = ref(null)

const channelOptions = ref([]) // 树数据，用于通道下拉（按设备分组）

const form = reactive({ channelId: null, startTime: '', endTime: '' })
const rules = {
  channelId: [{ required: true, message: '请选择通道', trigger: 'change' }],
  startTime: [{ required: true, message: '请选择开始时间', trigger: 'change' }],
  endTime: [
    { required: true, message: '请选择结束时间', trigger: 'change' },
    {
      validator: (rule, value, cb) => {
        if (!value || !form.startTime) return cb()
        const s = new Date(form.startTime.replace(/-/g, '/')).getTime()
        const e = new Date(value.replace(/-/g, '/')).getTime()
        if (e <= s) return cb(new Error('结束时间需晚于开始时间'))
        if (e - s > 4 * 3600 * 1000) return cb(new Error('下载时段不能超过 4 小时'))
        cb()
      },
      trigger: 'change'
    }
  ]
}

const hasActive = computed(() =>
  tasks.value.some((t) => t.status === 'PENDING' || t.status === 'RUNNING')
)

let pollTimer = null

async function loadChannels() {
  try {
    const res = await channelApi.tree()
    channelOptions.value = res.devices || []
  } catch (e) {
    /* 拦截器已提示 */
  }
}

async function loadTasks(silent = false) {
  if (!silent) loading.value = true
  try {
    tasks.value = await downloadApi.list()
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
  schedulePoll()
}

function schedulePoll() {
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
  if (hasActive.value) {
    pollTimer = setTimeout(() => loadTasks(true), 5000) // 有进行中的任务时每 5 秒轮询
  }
}

function openCreate() {
  form.channelId = null
  form.startTime = ''
  form.endTime = ''
  // 回放页“下载此时段”预填
  const prefill = sessionStorage.getItem('downloadPrefill')
  if (prefill) {
    try {
      const p = JSON.parse(prefill)
      form.channelId = p.channelId
      form.startTime = p.startTime || ''
      form.endTime = p.endTime || ''
    } catch (e) {
      /* 忽略 */
    }
    sessionStorage.removeItem('downloadPrefill')
  }
  createDialog.value = true
}

async function submitCreate() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    await downloadApi.create({
      channelId: form.channelId,
      startTime: form.startTime,
      endTime: form.endTime
    })
    ElMessage.success('下载任务已创建')
    createDialog.value = false
    await loadTasks()
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  loadChannels()
  loadTasks()
})

onBeforeUnmount(() => {
  if (pollTimer) clearTimeout(pollTimer)
})
</script>

<style scoped>
.dl-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.toolbar {
  display: flex;
  gap: 8px;
}
.opt-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 6px;
  vertical-align: middle;
}
.opt-dot.on {
  background: #67c23a;
}
.opt-dot.off {
  background: #c0c4cc;
}
.form-tip {
  color: #909399;
  font-size: 12px;
}
</style>
