<template>
  <div class="page">
    <div class="toolbar">
      <el-select v-model="filter.org_id" placeholder="全部机构" clearable filterable style="width: 200px" @change="onFilterChange">
        <el-option v-for="o in orgs" :key="o.id" :label="o.name" :value="o.id" />
      </el-select>
      <el-select v-model="filter.status" placeholder="全部状态" clearable style="width: 140px" @change="onFilterChange">
        <el-option v-for="(info, key) in TASK_STATUS" :key="key" :label="info.label" :value="key" />
      </el-select>
      <el-button :icon="Refresh" @click="load">刷新</el-button>
    </div>

    <TaskTable :tasks="list" :loading="loading" />

    <el-pagination
      v-model:current-page="page"
      :page-size="count"
      :total="total"
      layout="total, prev, pager, next"
      background
      class="pager"
      @current-change="load"
    />
  </div>
</template>

<script setup>
// 管理端下载任务：按机构/状态筛选（注意接口参数为小写下划线）
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import TaskTable from '../../components/TaskTable.vue'
import { adminApi } from '../../api'
import { TASK_STATUS } from '../../constants'

const orgs = ref([])
const list = ref([])
const total = ref(0)
const loading = ref(false)

const filter = reactive({ org_id: null, status: null })
const page = ref(1)
const count = 20

let pollTimer = null

async function loadOrgs() {
  try {
    orgs.value = await adminApi.listOrgs()
  } catch (e) {
    /* 拦截器已提示 */
  }
}

async function load(silent = false) {
  if (!silent) loading.value = true
  try {
    const res = await adminApi.listTasks({
      org_id: filter.org_id ?? undefined,
      status: filter.status || undefined,
      page: page.value,
      count
    })
    list.value = res.list || []
    total.value = res.total || 0
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
  if (list.value.some((t) => t.status === 'PENDING' || t.status === 'RUNNING')) {
    pollTimer = setTimeout(() => load(true), 5000)
  }
}

function onFilterChange() {
  page.value = 1
  load()
}

onMounted(() => {
  loadOrgs()
  load()
})

onBeforeUnmount(() => {
  if (pollTimer) clearTimeout(pollTimer)
})
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
</style>
