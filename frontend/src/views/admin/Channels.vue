<template>
  <div class="page">
    <div class="toolbar">
      <el-input
        v-model="query"
        placeholder="通道名称 / 国标编号"
        clearable
        style="width: 220px"
        @keyup.enter="onSearch"
        @clear="onSearch"
      />
      <el-button type="primary" :icon="Search" @click="onSearch">查询</el-button>
      <el-button type="success" :loading="syncing" :icon="Refresh" @click="onSync">从 WVP 同步</el-button>
    </div>

    <el-table :data="list" v-loading="loading" stripe>
      <el-table-column prop="deviceId" label="设备 ID" min-width="150" show-overflow-tooltip />
      <el-table-column prop="deviceName" label="设备名称" min-width="140" show-overflow-tooltip />
      <el-table-column prop="channelGbId" label="通道国标编号" min-width="160" show-overflow-tooltip />
      <el-table-column prop="name" label="通道名称" min-width="150" show-overflow-tooltip />
      <el-table-column prop="displayName" label="对外别名" min-width="150" show-overflow-tooltip>
        <template #default="{ row }">{{ row.displayName || '-' }}</template>
      </el-table-column>
      <el-table-column label="在线" width="80" align="center">
        <template #default="{ row }">
          <span class="dot" :class="row.online ? 'on' : 'off'"></span>
        </template>
      </el-table-column>
      <el-table-column label="active" width="80" align="center">
        <template #default="{ row }">
          <el-tag size="small" :type="row.active ? 'success' : 'info'">{{ row.active ? '是' : '否' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="lastSyncAt" label="最近同步" width="160">
        <template #default="{ row }">{{ row.lastSyncAt || '-' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="90" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link @click="openEdit(row)">编辑别名</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-model:current-page="page"
      :page-size="count"
      :total="total"
      layout="total, prev, pager, next"
      background
      class="pager"
      @current-change="load"
    />

    <el-dialog v-model="dialog" title="编辑对外别名" width="420px" :close-on-click-modal="false">
      <el-form label-width="90px" @submit.prevent>
        <el-form-item label="通道">
          <span>{{ editing?.name }}</span>
        </el-form-item>
        <el-form-item label="对外别名">
          <el-input v-model="displayName" placeholder="留空则使用通道名称" maxlength="64" clearable />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
// 通道台账：查询/WVP 同步/编辑对外别名
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Search } from '@element-plus/icons-vue'
import { adminApi } from '../../api'

const list = ref([])
const total = ref(0)
const loading = ref(false)
const syncing = ref(false)
const submitting = ref(false)
const query = ref('')
const page = ref(1)
const count = 20

const dialog = ref(false)
const editing = ref(null)
const displayName = ref('')

async function load() {
  loading.value = true
  try {
    const res = await adminApi.listChannels({ query: query.value || undefined, page: page.value, count })
    list.value = res.list || []
    total.value = res.total || 0
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}

function onSearch() {
  page.value = 1
  load()
}

async function onSync() {
  const ok = await ElMessageBox.confirm('确定从 WVP 平台同步通道数据？', '通道同步', { type: 'info' }).catch(() => false)
  if (!ok) return
  syncing.value = true
  try {
    const res = await adminApi.syncChannels()
    const summary = res && typeof res === 'object'
      ? Object.entries(res).map(([k, v]) => `${k}: ${v}`).join('，')
      : ''
    ElMessage.success(summary ? `同步完成（${summary}）` : '同步完成')
    page.value = 1
    await load()
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    syncing.value = false
  }
}

function openEdit(row) {
  editing.value = row
  displayName.value = row.displayName || ''
  dialog.value = true
}

async function submit() {
  submitting.value = true
  try {
    await adminApi.updateChannel(editing.value.id, displayName.value)
    ElMessage.success('别名已保存')
    dialog.value = false
    await load()
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    submitting.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.toolbar {
  display: flex;
  gap: 8px;
}
.pager {
  justify-content: flex-end;
}
.dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
}
.dot.on {
  background: #67c23a;
}
.dot.off {
  background: #c0c4cc;
}
</style>
