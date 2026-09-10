<template>
  <div class="page">
    <div class="toolbar">
      <el-select v-model="filter.action" placeholder="全部动作" clearable filterable style="width: 150px" @change="onFilterChange">
        <el-option v-for="(label, key) in AUDIT_ACTIONS" :key="key" :label="`${label} (${key})`" :value="key" />
      </el-select>
      <el-input
        v-model="filter.username"
        placeholder="用户名"
        clearable
        style="width: 150px"
        @keyup.enter="onFilterChange"
        @clear="onFilterChange"
      />
      <el-select v-model="filter.orgId" placeholder="全部机构" clearable filterable style="width: 180px" @change="onFilterChange">
        <el-option v-for="o in orgs" :key="o.id" :label="o.name" :value="o.id" />
      </el-select>
      <el-date-picker
        v-model="range"
        type="datetimerange"
        start-placeholder="开始时间"
        end-placeholder="结束时间"
        format="YYYY-MM-DD HH:mm:ss"
        value-format="YYYY-MM-DD HH:mm:ss"
        style="width: 360px"
        @change="onFilterChange"
      />
      <el-button type="primary" :icon="Search" @click="onFilterChange">查询</el-button>
      <el-button type="success" :icon="Download" @click="exportCsv">导出 CSV</el-button>
    </div>

    <el-table :data="list" v-loading="loading" stripe>
      <el-table-column prop="ts" label="时间" width="160" />
      <el-table-column prop="username" label="用户" width="110" show-overflow-tooltip />
      <el-table-column prop="orgName" label="机构" width="130" show-overflow-tooltip>
        <template #default="{ row }">{{ row.orgName || '-' }}</template>
      </el-table-column>
      <el-table-column label="动作" width="120">
        <template #default="{ row }">
          <el-tag size="small" :type="actionTagType(row.action)" effect="plain">{{ AUDIT_ACTIONS[row.action] || row.action }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="对象" width="150" show-overflow-tooltip>
        <template #default="{ row }">{{ row.objectType ? `${row.objectType}#${row.objectId ?? ''}` : '-' }}</template>
      </el-table-column>
      <el-table-column label="参数" width="90">
        <template #default="{ row }">
          <el-popover v-if="prettyParams(row.params)" placement="left" :width="420" trigger="click">
            <template #reference>
              <el-button type="primary" link size="small">查看</el-button>
            </template>
            <pre class="params-pre">{{ prettyParams(row.params) }}</pre>
          </el-popover>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="结果" width="80" align="center">
        <template #default="{ row }">
          <el-tag size="small" :type="resultTagType(row.result)">{{ row.result ?? '-' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="ip" label="IP" width="130" show-overflow-tooltip />
      <el-table-column label="UA" min-width="120">
        <template #default="{ row }">
          <el-tooltip v-if="row.ua" :content="row.ua" placement="top" :show-after="200">
            <span class="ua">{{ row.ua }}</span>
          </el-tooltip>
          <span v-else>-</span>
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
  </div>
</template>

<script setup>
// 审计查询：多条件筛选 + 分页 + CSV 导出
import { computed, onMounted, reactive, ref } from 'vue'
import { Download, Search } from '@element-plus/icons-vue'
import { adminApi } from '../../api'
import { AUDIT_ACTIONS } from '../../constants'

const orgs = ref([])
const list = ref([])
const total = ref(0)
const loading = ref(false)

const filter = reactive({ action: null, username: '', orgId: null })
const range = ref(null) // [start, end]
const page = ref(1)
const count = 20

const exportParams = computed(() => ({
  action: filter.action || undefined,
  username: filter.username || undefined,
  orgId: filter.orgId ?? undefined,
  start: range.value?.[0] || undefined,
  end: range.value?.[1] || undefined
}))

function actionTagType(action) {
  if (String(action).includes('FAIL') || String(action).includes('LOCKED') || action === 'STREAM_AUTH_FAIL') return 'danger'
  if (String(action).includes('SUCCESS') || String(action).includes('COMPLETE')) return 'success'
  return 'info'
}

function resultTagType(result) {
  const r = Number(result)
  if (r === 0) return 'success'
  return 'danger'
}

// params 是 JSON 字符串，解析美化后展示
function prettyParams(params) {
  if (!params) return ''
  try {
    return JSON.stringify(JSON.parse(params), null, 2)
  } catch (e) {
    return String(params)
  }
}

async function loadOrgs() {
  try {
    orgs.value = await adminApi.listOrgs()
  } catch (e) {
    /* 拦截器已提示 */
  }
}

async function load() {
  loading.value = true
  try {
    const res = await adminApi.listAudit({ ...exportParams.value, page: page.value, count })
    list.value = res.list || []
    total.value = res.total || 0
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}

function onFilterChange() {
  page.value = 1
  load()
}

function exportCsv() {
  // 直接以当前用户身份（携带 cookie）下载 CSV
  window.open(adminApi.auditExportUrl(exportParams.value))
}

onMounted(() => {
  loadOrgs()
  load()
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
  flex-wrap: wrap;
}
.pager {
  justify-content: flex-end;
}
.params-pre {
  margin: 0;
  max-height: 320px;
  overflow: auto;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
}
.ua {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #909399;
  font-size: 12px;
}
</style>
