<template>
  <div class="tree-panel">
    <div class="tree-header">
      <h3><i class="fas fa-folder-tree"></i> Directory Structure</h3>
      <div class="tree-controls">
        <button @click="$emit('expand-all')" title="Expand All">
          <i class="fas fa-expand-alt"></i>
        </button>
        <button @click="$emit('collapse-all')" title="Collapse All">
          <i class="fas fa-compress-alt"></i>
        </button>
      </div>
    </div>

    <div class="tree-content">
      <div
        v-for="item in directoryTree"
        :key="item.path"
        class="tree-node"
        :class="{
          expanded: item.expanded,
          selected: selectedPath === item.path
        }"
      >
        <div
          class="tree-node-content"
          @click="$emit('toggle-node', item)"
          :style="{ paddingLeft: (item.level * 20) + 'px' }"
        >
          <i
            v-if="item.is_dir"
            :class="item.expanded ? 'fas fa-chevron-down' : 'fas fa-chevron-right'"
            class="tree-toggle"
          ></i>
          <i
            :class="getFileIcon(item)"
            class="tree-icon"
          ></i>
          <span class="tree-label">{{ item.name }}</span>
        </div>
      </div>

      <EmptyState
        v-if="directoryTree.length === 0"
        icon="fas fa-folder-open"
        message="No directory structure available"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import EmptyState from '@/components/ui/EmptyState.vue'

interface TreeItem {
  name: string
  path: string
  is_dir: boolean
  level: number
  expanded?: boolean
}

interface Props {
  directoryTree: TreeItem[]
  selectedPath: string
}

interface Emits {
  (e: 'toggle-node', item: TreeItem): void
  (e: 'expand-all'): void
  (e: 'collapse-all'): void
}

defineProps<Props>()
defineEmits<Emits>()

// Methods
const getFileIcon = (item: TreeItem): string => {
  if (item.is_dir) {
    return item.expanded ? 'fas fa-folder-open text-blue-500' : 'fas fa-folder text-blue-500'
  }

  const extension = item.name.split('.').pop()?.toLowerCase()

  switch (extension) {
    case 'txt':
    case 'md':
    case 'readme':
      return 'fas fa-file-alt text-gray-500'
    case 'js':
    case 'ts':
    case 'html':
    case 'css':
    case 'vue':
    case 'json':
      return 'fas fa-file-code text-green-500'
    case 'jpg':
    case 'jpeg':
    case 'png':
    case 'gif':
    case 'svg':
    case 'webp':
      return 'fas fa-file-image text-purple-500'
    case 'pdf':
      return 'fas fa-file-pdf text-red-500'
    case 'zip':
    case 'tar':
    case 'gz':
    case 'rar':
      return 'fas fa-file-archive text-orange-500'
    default:
      return 'fas fa-file text-gray-400'
  }
}
</script>

<style scoped>
.tree-panel {
  @apply bg-white border border-gray-200 rounded-lg flex flex-col h-full;
}

.tree-header {
  @apply flex justify-between items-center p-4 border-b border-gray-200 bg-gray-50 flex-shrink-0;
}

.tree-header h3 {
  @apply text-lg font-semibold text-gray-900 flex items-center gap-2;
}

.tree-controls {
  @apply flex gap-1;
}

.tree-controls button {
  @apply w-8 h-8 flex items-center justify-center rounded text-gray-500 hover:text-gray-700 hover:bg-gray-100;
}

.tree-content {
  @apply flex-1 overflow-y-auto p-2 min-h-0;
}

.tree-node {
  @apply select-none;
}

.tree-node-content {
  @apply flex items-center gap-2 py-1 px-2 rounded cursor-pointer hover:bg-gray-100;
}

.tree-node.selected .tree-node-content {
  @apply bg-blue-50 text-blue-900;
}

.tree-toggle {
  @apply w-4 text-xs text-gray-400;
}

.tree-icon {
  @apply w-4;
}

.tree-label {
  @apply text-sm truncate;
}
</style>