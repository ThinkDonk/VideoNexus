<template>
  <div class="channel-tree">
    <el-input
      v-model="keyword"
      placeholder="搜索通道名称 / 国标编号"
      clearable
      :prefix-icon="Search"
      size="default"
      class="tree-search"
    />
    <div v-loading="loading" class="tree-wrap">
      <el-empty v-if="!loading && !treeData.length" description="暂无授权通道" :image-size="60" />
      <el-tree
        v-else
        ref="treeRef"
        :data="treeData"
        :props="treeProps"
        node-key="nodeKey"
        highlight-current
        :expand-on-click-node="false"
        default-expand-all
        :filter-node-method="filterNode"
        @node-click="onNodeClick"
      >
        <template #default="{ data }">
          <span class="tree-node" :class="{ disabled: data.disabled }">
            <template v-if="data.isDevice">
              <el-icon class="dev-icon"><Monitor /></el-icon>
              <span class="dev-name">{{ data.deviceName }}</span>
              <span class="gb-id">{{ data.children?.length || 0 }} 通道</span>
            </template>
            <template v-else>
              <span class="dot" :class="data.online ? 'on' : 'off'"></span>
              <span class="ch-name" :title="data.name">{{ data.name }}</span>
              <span class="gb-id">{{ data.channelGbId }}</span>
            </template>
          </span>
        </template>
      </el-tree>
    </div>
  </div>
</template>

<script setup>
// 授权通道树：按设备分组，支持关键字过滤；按 grant 类型禁用无权限/离线节点
import { computed, onMounted, ref, watch } from 'vue'
import { Search, Monitor } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { channelApi } from '../api'

const props = defineProps({
  // live: 需 grants.live 且在线；playback/download: 需对应授权
  grant: { type: String, required: true }
})
const emit = defineEmits(['select'])

const loading = ref(false)
const keyword = ref('')
const treeRef = ref(null)
const rawDevices = ref([])

const treeProps = { label: 'label', children: 'children', disabled: 'disabled' }

const treeData = computed(() =>
  rawDevices.value.map((d) => ({
    ...d,
    isDevice: true,
    nodeKey: `dev-${d.deviceId}`,
    children: (d.children || []).map((c) => ({
      ...c,
      nodeKey: `ch-${c.channelId}`,
      disabled: props.grant === 'live' ? !c.online || !c.grants?.live : !c.grants?.[props.grant]
    }))
  }))
)

function filterNode(value, data) {
  if (!value) return true
  const v = value.toLowerCase()
  if (data.isDevice) {
    return (data.deviceName || '').toLowerCase().includes(v)
  }
  return (
    (data.name || '').toLowerCase().includes(v) ||
    String(data.channelGbId || '').toLowerCase().includes(v)
  )
}

watch(keyword, (v) => treeRef.value?.filter(v))

function onNodeClick(data) {
  if (data.isDevice || data.disabled) return
  emit('select', data)
}

async function load() {
  loading.value = true
  try {
    const res = await channelApi.tree()
    rawDevices.value = res.devices || []
  } catch (e) {
    ElMessage.error('加载通道树失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)
defineExpose({ reload: load })
</script>

<style scoped>
.channel-tree {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.tree-search {
  margin-bottom: 8px;
}
.tree-wrap {
  flex: 1;
  overflow: auto;
  min-height: 0;
}
.tree-node {
  display: flex;
  align-items: center;
  gap: 6px;
  overflow: hidden;
  flex: 1;
}
.tree-node.disabled {
  color: #c0c4cc;
  cursor: not-allowed;
}
.dev-icon {
  color: #409eff;
}
.dev-name {
  font-weight: 600;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dot.on {
  background: #67c23a;
  box-shadow: 0 0 4px rgba(103, 194, 58, 0.8);
}
.dot.off {
  background: #c0c4cc;
}
.ch-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.gb-id {
  color: #909399;
  font-size: 12px;
  margin-left: auto;
  flex-shrink: 0;
}
</style>
