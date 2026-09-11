<template>
  <div class="page">
    <div class="toolbar">
      <span class="label">选择用户：</span>
      <el-select
        v-model="userId"
        filterable
        placeholder="请选择要配置授权的用户"
        style="width: 280px"
        :loading="usersLoading"
        @change="onUserChange"
      >
        <el-option
          v-for="u in users"
          :key="u.id"
          :label="`${u.displayName}（${u.username} / ${roleLabel(u.role)}）`"
          :value="u.id"
        />
      </el-select>
      <el-button type="primary" :disabled="!userId" :loading="saving" @click="save">保存授权（全量覆盖）</el-button>
    </div>

    <template v-if="userId">
      <div class="sub-toolbar">
        <el-input
          v-model="query"
          placeholder="通道名称 / 国标编号"
          clearable
          style="width: 220px"
          @keyup.enter="onSearch"
          @clear="onSearch"
        />
        <el-button :icon="Search" @click="onSearch">查询</el-button>
        <span class="tip">
          开关为“开”即授权；三个开关全关视为收回授权。有效期可留空。
        </span>
        <el-alert
          v-if="staleCount"
          type="warning"
          :closable="false"
          show-icon
          class="stale-alert"
          :title="`有 ${staleCount} 条授权指向已从设备目录移除的通道，保存后将自动收回`"
        />
      </div>

      <el-table :data="rows" v-loading="loading" stripe>
        <el-table-column prop="deviceName" label="设备" min-width="130" show-overflow-tooltip />
        <el-table-column prop="channelGbId" label="通道国标编号" min-width="160" show-overflow-tooltip />
        <el-table-column label="通道名称" min-width="190" show-overflow-tooltip>
          <template #default="{ row }">
            <span>{{ row.name }}</span>
            <el-tag v-if="row.stale" type="info" size="small" class="stale-tag">已失效</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="实时" width="70" align="center">
          <template #default="{ row }">
            <el-switch v-model="grantMap[row.id].canLive" :disabled="row.stale" />
          </template>
        </el-table-column>
        <el-table-column label="回放" width="70" align="center">
          <template #default="{ row }">
            <el-switch v-model="grantMap[row.id].canPlayback" :disabled="row.stale" />
          </template>
        </el-table-column>
        <el-table-column label="下载" width="70" align="center">
          <template #default="{ row }">
            <el-switch v-model="grantMap[row.id].canDownload" :disabled="row.stale" />
          </template>
        </el-table-column>
        <el-table-column label="有效期起" min-width="200">
          <template #default="{ row }">
            <el-date-picker
              v-model="grantMap[row.id].validFrom"
              :disabled="row.stale"
              type="datetime"
              placeholder="可空"
              format="YYYY-MM-DD HH:mm:ss"
              value-format="YYYY-MM-DD HH:mm:ss"
              style="width: 175px"
            />
          </template>
        </el-table-column>
        <el-table-column label="有效期止" min-width="200">
          <template #default="{ row }">
            <el-date-picker
              v-model="grantMap[row.id].validUntil"
              :disabled="row.stale"
              type="datetime"
              placeholder="可空"
              format="YYYY-MM-DD HH:mm:ss"
              value-format="YYYY-MM-DD HH:mm:ss"
              style="width: 175px"
            />
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
        @current-change="loadChannels"
      />
    </template>
    <el-empty v-else description="请先选择用户" :image-size="80" />
  </div>
</template>

<script setup>
// 授权管理：按用户配置通道级实时/回放/下载授权与有效期，保存为全量覆盖
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { adminApi } from '../../api'
import { roleLabel } from '../../constants'

const users = ref([])
const usersLoading = ref(false)
const userId = ref(null)

const loading = ref(false)
const saving = ref(false)
const query = ref('')
const page = ref(1)
const count = 20
const channels = ref([])
const total = ref(0)

// channelId → { canLive, canPlayback, canDownload, validFrom, validUntil }
const grantMap = reactive({})
// channelId → { name, channelGbId, active }：用于识别"已失效但仍留有授权"的通道
const grantChannels = reactive({})

const rows = computed(() => channels.value)

function ensureGrant(id) {
  if (!grantMap[id]) {
    grantMap[id] = { canLive: false, canPlayback: false, canDownload: false, validFrom: null, validUntil: null }
  }
  return grantMap[id]
}

async function loadUsers() {
  usersLoading.value = true
  try {
    const res = await adminApi.listUsers({ page: 1, count: 100 })
    users.value = res.list || []
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    usersLoading.value = false
  }
}

const staleCount = ref(0)

async function loadGrants() {
  try {
    const grants = await adminApi.listGrants(userId.value)
    // 先按现有授权勾选
    for (const g of grants || []) {
      grantChannels[g.channelId] = {
        name: g.channelName,
        channelGbId: g.channelGbId,
        active: g.active
      }
      grantMap[g.channelId] = {
        canLive: !!g.canLive,
        canPlayback: !!g.canPlayback,
        canDownload: !!g.canDownload,
        validFrom: g.validFrom || null,
        validUntil: g.validUntil || null
      }
    }
  } catch (e) {
    /* 拦截器已提示 */
  }
}

async function loadChannels() {
  loading.value = true
  try {
    // 只列"仍存在于 WVP 目录"的通道（active=true）供授权
    const res = await adminApi.listChannels({
      query: query.value || undefined, active: true, page: page.value, count
    })
    channels.value = res.list || []
    total.value = res.total || 0
    for (const ch of channels.value) ensureGrant(ch.id)
    appendStaleRows()
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}

// 把"已失效但仍留有授权"的通道补进列表：标记为失效、禁用操作，保存时自动收回
function appendStaleRows() {
  const shown = new Set(channels.value.map((c) => c.id))
  let n = 0
  for (const [cid, meta] of Object.entries(grantChannels)) {
    const id = Number(cid)
    if (shown.has(id) || meta.active !== false) continue
    channels.value.unshift({
      id,
      deviceName: '—',
      channelGbId: meta.channelGbId || '',
      name: meta.name || `通道 #${id}`,
      online: false,
      active: false,
      stale: true
    })
    ensureGrant(id)
    n++
  }
  staleCount.value = n
}

async function onUserChange() {
  page.value = 1
  query.value = ''
  // 切换用户：清空上一用户的勾选，避免串数据
  for (const k of Object.keys(grantMap)) delete grantMap[k]
  for (const k of Object.keys(grantChannels)) delete grantChannels[k]
  staleCount.value = 0
  await Promise.all([loadGrants(), loadChannels()])
}

function onSearch() {
  page.value = 1
  loadChannels()
}

async function save() {
  const grants = []
  let revoked = 0
  for (const ch of Object.keys(grantMap)) {
    // 已失效通道：不再提交，等同于收回其授权（后端会记录 GRANT_REMOVED 审计）
    const row = channels.value.find((c) => c.id === Number(ch))
    if (row?.stale) {
      if (grantMap[ch].canLive || grantMap[ch].canPlayback || grantMap[ch].canDownload) revoked++
      continue
    }
    const g = grantMap[ch]
    if (g.canLive || g.canPlayback || g.canDownload) {
      grants.push({
        channelId: Number.isNaN(Number(ch)) ? ch : Number(ch),
        canLive: g.canLive,
        canPlayback: g.canPlayback,
        canDownload: g.canDownload,
        validFrom: g.validFrom || undefined,
        validUntil: g.validUntil || undefined
      })
    }
  }
  saving.value = true
  try {
    await adminApi.updateGrants(userId.value, grants)
    ElMessage.success(
      `授权已保存（共 ${grants.length} 条${revoked ? `，并收回 ${revoked} 条失效通道授权` : ''}）`
    )
    // 清理本地缓存后重新加载勾选状态
    for (const k of Object.keys(grantChannels)) delete grantChannels[k]
    await loadGrants()
    await loadChannels()
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadUsers()
})
</script>

<style scoped>
.stale-tag {
  margin-left: 6px;
}
.stale-alert {
  width: 100%;
  margin-top: 8px;
}
.page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
}
.label {
  color: #606266;
}
.sub-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
}
.tip {
  color: #909399;
  font-size: 12px;
  margin-left: auto;
}
.pager {
  justify-content: flex-end;
}
</style>
