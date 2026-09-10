<template>
  <div class="page">
    <div class="toolbar">
      <el-select v-model="filter.orgId" placeholder="全部机构" clearable filterable style="width: 200px" @change="onFilterChange">
        <el-option v-for="o in orgs" :key="o.id" :label="o.name" :value="o.id" />
      </el-select>
      <el-input
        v-model="filter.query"
        placeholder="用户名 / 姓名"
        clearable
        style="width: 200px"
        @keyup.enter="onFilterChange"
        @clear="onFilterChange"
      />
      <el-button type="primary" :icon="Search" @click="onFilterChange">查询</el-button>
      <el-button type="success" :icon="Plus" @click="openCreate">新建用户</el-button>
    </div>

    <el-table :data="list" v-loading="loading" stripe>
      <el-table-column prop="username" label="用户名" min-width="120" />
      <el-table-column prop="displayName" label="姓名" min-width="110" />
      <el-table-column label="角色" width="100">
        <template #default="{ row }">
          <el-tag size="small" :type="roleTagType(row.role)">{{ roleLabel(row.role) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="orgName" label="所属机构" min-width="140" />
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.status === 'ENABLED' ? 'success' : 'info'" size="small">
            {{ row.status === 'ENABLED' ? '启用' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="锁定至" width="160">
        <template #default="{ row }">
          <span v-if="row.lockedUntil" class="locked">{{ row.lockedUntil }}</span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column prop="lastLoginAt" label="最近登录" width="160">
        <template #default="{ row }">{{ row.lastLoginAt || '-' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="260" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link @click="openEdit(row)">编辑</el-button>
          <el-button type="warning" link @click="openResetPwd(row)">重置密码</el-button>
          <el-button v-if="row.lockedUntil" type="danger" link @click="onUnlock(row)">解锁</el-button>
          <el-button v-if="row.status === 'ENABLED'" type="info" link @click="onToggleStatus(row)">停用</el-button>
          <el-button v-else type="success" link @click="onToggleStatus(row)">启用</el-button>
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

    <!-- 新建用户 -->
    <el-dialog v-model="createDialog" title="新建用户" width="480px" :close-on-click-modal="false">
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="90px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="createForm.username" placeholder="登录账号" maxlength="32" />
        </el-form-item>
        <el-form-item label="初始密码" prop="password">
          <el-input v-model="createForm.password" type="password" show-password placeholder="至少 8 位" />
        </el-form-item>
        <el-form-item label="姓名" prop="displayName">
          <el-input v-model="createForm.displayName" maxlength="32" />
        </el-form-item>
        <el-form-item label="所属机构" prop="orgId">
          <el-select v-model="createForm.orgId" filterable style="width: 100%">
            <el-option v-for="o in orgs" :key="o.id" :label="o.name" :value="o.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="createForm.role" style="width: 100%">
            <el-option v-for="r in ROLES" :key="r.value" :label="r.label" :value="r.value" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialog = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 编辑用户 -->
    <el-dialog v-model="editDialog" title="编辑用户" width="480px" :close-on-click-modal="false">
      <el-form ref="editFormRef" :model="editForm" :rules="editRules" label-width="90px">
        <el-form-item label="用户名">
          <el-input :model-value="editForm.username" disabled />
        </el-form-item>
        <el-form-item label="姓名" prop="displayName">
          <el-input v-model="editForm.displayName" maxlength="32" />
        </el-form-item>
        <el-form-item label="所属机构" prop="orgId">
          <el-select v-model="editForm.orgId" filterable style="width: 100%">
            <el-option v-for="o in orgs" :key="o.id" :label="o.name" :value="o.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="editForm.role" style="width: 100%">
            <el-option v-for="r in ROLES" :key="r.value" :label="r.label" :value="r.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="editForm.status" active-value="ENABLED" inactive-value="DISABLED" active-text="启用" inactive-text="停用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialog = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 重置密码 -->
    <el-dialog v-model="resetDialog" title="重置密码" width="420px" :close-on-click-modal="false">
      <el-form ref="resetFormRef" :model="resetForm" :rules="resetRules" label-width="90px">
        <el-form-item label="用户">
          <span>{{ resetting?.username }}</span>
        </el-form-item>
        <el-form-item label="新密码" prop="newPassword">
          <el-input v-model="resetForm.newPassword" type="password" show-password placeholder="至少 8 位" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetDialog = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitReset">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
// 用户管理：筛选/新建/编辑/重置密码/解锁/停用启用
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search } from '@element-plus/icons-vue'
import { adminApi } from '../../api'
import { ROLES, roleLabel } from '../../constants'

const orgs = ref([])
const list = ref([])
const total = ref(0)
const loading = ref(false)
const submitting = ref(false)

const filter = reactive({ orgId: null, query: '' })
const page = ref(1)
const count = 20

const createDialog = ref(false)
const createFormRef = ref(null)
const createForm = reactive({ username: '', password: '', displayName: '', orgId: null, role: 'BANK_USER' })
const createRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入初始密码', trigger: 'blur' },
    { min: 8, message: '密码至少 8 位', trigger: 'blur' }
  ],
  displayName: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  orgId: [{ required: true, message: '请选择机构', trigger: 'change' }],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }]
}

const editDialog = ref(false)
const editFormRef = ref(null)
const editing = ref(null)
const editForm = reactive({ username: '', displayName: '', orgId: null, role: '', status: 'ENABLED' })
const editRules = {
  displayName: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  orgId: [{ required: true, message: '请选择机构', trigger: 'change' }],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }]
}

const resetDialog = ref(false)
const resetFormRef = ref(null)
const resetting = ref(null)
const resetForm = reactive({ newPassword: '' })
const resetRules = {
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 8, message: '密码至少 8 位', trigger: 'blur' }
  ]
}

function roleTagType(role) {
  if (role === 'ADMIN') return 'danger'
  if (role === 'AUDITOR') return 'warning'
  return ''
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
    const res = await adminApi.listUsers({
      orgId: filter.orgId ?? undefined,
      query: filter.query || undefined,
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
}

function onFilterChange() {
  page.value = 1
  load()
}

function openCreate() {
  Object.assign(createForm, { username: '', password: '', displayName: '', orgId: filter.orgId ?? null, role: 'BANK_USER' })
  createDialog.value = true
}

async function submitCreate() {
  const valid = await createFormRef.value.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    await adminApi.createUser({ ...createForm })
    ElMessage.success('用户已创建')
    createDialog.value = false
    await load()
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    submitting.value = false
  }
}

function openEdit(row) {
  editing.value = row
  Object.assign(editForm, {
    username: row.username,
    displayName: row.displayName,
    orgId: row.orgId,
    role: row.role,
    status: row.status
  })
  editDialog.value = true
}

async function submitEdit() {
  const valid = await editFormRef.value.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    await adminApi.updateUser(editing.value.id, {
      displayName: editForm.displayName,
      orgId: editForm.orgId,
      role: editForm.role,
      status: editForm.status
    })
    ElMessage.success('用户已更新')
    editDialog.value = false
    await load()
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    submitting.value = false
  }
}

function openResetPwd(row) {
  resetting.value = row
  resetForm.newPassword = ''
  resetDialog.value = true
}

async function submitReset() {
  const valid = await resetFormRef.value.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    await adminApi.resetPassword(resetting.value.id, resetForm.newPassword)
    ElMessage.success('密码已重置')
    resetDialog.value = false
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    submitting.value = false
  }
}

async function onUnlock(row) {
  try {
    await adminApi.unlockUser(row.id)
    ElMessage.success('已解锁')
    await load()
  } catch (e) {
    /* 拦截器已提示 */
  }
}

async function onToggleStatus(row) {
  const toEnabled = row.status !== 'ENABLED'
  const ok = await ElMessageBox.confirm(`确定${toEnabled ? '启用' : '停用'}用户「${row.username}」？`, '提示', { type: 'warning' }).catch(() => false)
  if (!ok) return
  try {
    await adminApi.updateUser(row.id, { status: toEnabled ? 'ENABLED' : 'DISABLED' })
    ElMessage.success(toEnabled ? '已启用' : '已停用')
    await load()
  } catch (e) {
    /* 拦截器已提示 */
  }
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
.locked {
  color: #f56c6c;
}
</style>
