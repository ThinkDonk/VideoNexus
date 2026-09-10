<template>
  <div class="page">
    <div class="toolbar">
      <el-button type="primary" :icon="Plus" @click="openCreate">新建机构</el-button>
      <el-button :icon="Refresh" @click="load">刷新</el-button>
    </div>

    <el-table :data="orgs" v-loading="loading" stripe>
      <el-table-column prop="name" label="机构名称" min-width="160" show-overflow-tooltip />
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.status === 'ENABLED' ? 'success' : 'info'" size="small">
            {{ row.status === 'ENABLED' ? '启用' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="ipWhitelist" label="IP 白名单" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">{{ row.ipWhitelist || '-' }}</template>
      </el-table-column>
      <el-table-column prop="maxConcurrentPlays" label="并发上限" width="90" align="center" />
      <el-table-column prop="quotaGb" label="配额 GB" width="90" align="center" />
      <el-table-column prop="remark" label="备注" min-width="140" show-overflow-tooltip>
        <template #default="{ row }">{{ row.remark || '-' }}</template>
      </el-table-column>
      <el-table-column prop="createdAt" label="创建时间" width="160" />
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link @click="openEdit(row)">编辑</el-button>
          <el-button type="danger" link @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialog" :title="editing ? '编辑机构' : '新建机构'" width="500px" :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="机构名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入机构名称" maxlength="50" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="form.status" active-value="ENABLED" inactive-value="DISABLED" active-text="启用" inactive-text="停用" />
        </el-form-item>
        <el-form-item label="IP 白名单">
          <el-input v-model="form.ipWhitelist" type="textarea" :rows="2" placeholder="逗号分隔，留空不限制" />
        </el-form-item>
        <el-form-item label="并发播放上限">
          <el-input-number v-model="form.maxConcurrentPlays" :min="0" :max="999" />
        </el-form-item>
        <el-form-item label="配额 GB">
          <el-input-number v-model="form.quotaGb" :min="0" :max="102400" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" />
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
// 机构管理：CRUD
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { adminApi } from '../../api'

const orgs = ref([])
const loading = ref(false)
const dialog = ref(false)
const editing = ref(null)
const submitting = ref(false)
const formRef = ref(null)

const form = reactive({
  name: '',
  status: 'ENABLED',
  ipWhitelist: '',
  maxConcurrentPlays: 5,
  quotaGb: 10,
  remark: ''
})
const rules = {
  name: [{ required: true, message: '请输入机构名称', trigger: 'blur' }]
}

async function load() {
  loading.value = true
  try {
    orgs.value = await adminApi.listOrgs()
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  Object.assign(form, { name: '', status: 'ENABLED', ipWhitelist: '', maxConcurrentPlays: 5, quotaGb: 10, remark: '' })
  dialog.value = true
}

function openEdit(row) {
  editing.value = row
  Object.assign(form, {
    name: row.name,
    status: row.status,
    ipWhitelist: row.ipWhitelist || '',
    maxConcurrentPlays: row.maxConcurrentPlays ?? 0,
    quotaGb: row.quotaGb ?? 0,
    remark: row.remark || ''
  })
  dialog.value = true
}

async function submit() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  const body = {
    name: form.name,
    status: form.status,
    ipWhitelist: form.ipWhitelist,
    maxConcurrentPlays: form.maxConcurrentPlays,
    quotaGb: form.quotaGb,
    remark: form.remark
  }
  try {
    if (editing.value) {
      await adminApi.updateOrg(editing.value.id, body)
      ElMessage.success('机构已更新')
    } else {
      await adminApi.createOrg(body)
      ElMessage.success('机构已创建')
    }
    dialog.value = false
    await load()
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    submitting.value = false
  }
}

async function onDelete(row) {
  const ok = await ElMessageBox.confirm(`确定删除机构「${row.name}」？该操作不可恢复。`, '删除确认', { type: 'warning' }).catch(() => false)
  if (!ok) return
  try {
    await adminApi.deleteOrg(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    /* 拦截器已提示 */
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
</style>
