<template>
  <el-table :data="tasks" v-loading="loading" stripe>
    <el-table-column prop="channelName" label="通道" min-width="140" show-overflow-tooltip />
    <el-table-column label="时间段" min-width="280">
      <template #default="{ row }">{{ row.startTime }} ~ {{ row.endTime }}</template>
    </el-table-column>
    <el-table-column label="状态" width="100">
      <template #default="{ row }">
        <el-tag :type="statusInfo(row.status).tag" size="small">{{ statusInfo(row.status).label }}</el-tag>
      </template>
    </el-table-column>
    <el-table-column label="进度" width="140">
      <template #default="{ row }">
        <el-progress
          v-if="row.status === 'RUNNING'"
          :percentage="row.progress || 0"
          :stroke-width="8"
        />
        <span v-else-if="row.status === 'COMPLETE'">100%</span>
        <span v-else>-</span>
      </template>
    </el-table-column>
    <el-table-column label="文件大小" width="100">
      <template #default="{ row }">{{ fmtSize(row.fileSize) }}</template>
    </el-table-column>
    <el-table-column label="过期时间" width="160">
      <template #default="{ row }">{{ row.expiresAt || '-' }}</template>
    </el-table-column>
    <el-table-column label="操作" width="90" fixed="right">
      <template #default="{ row }">
        <el-tooltip v-if="row.status === 'FAILED' && row.error" :content="row.error" placement="left">
          <el-tag type="danger" size="small">失败详情</el-tag>
        </el-tooltip>
        <a v-else-if="row.status === 'COMPLETE'" class="dl-link" :href="downloadApi.fileUrl(row.id)">
          下载
        </a>
        <span v-else>-</span>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup>
// 下载任务表格：下载页与管理端任务页共用
import { TASK_STATUS } from '../constants'
import { fmtSize } from '../utils/format'
import { downloadApi } from '../api'

defineProps({
  tasks: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false }
})

function statusInfo(status) {
  return TASK_STATUS[status] || { label: status, tag: 'info' }
}
</script>

<style scoped>
.dl-link {
  color: #409eff;
  text-decoration: none;
}
.dl-link:hover {
  text-decoration: underline;
}
</style>
