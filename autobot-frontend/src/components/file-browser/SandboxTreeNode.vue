<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div
    class="sandbox-tree-node"
    role="treeitem"
    :aria-expanded="node.is_dir ? expanded : undefined"
    :style="{ paddingLeft: `${depth * 16 + 8}px` }"
  >
    <button
      v-if="node.is_dir"
      class="node-row node-dir"
      :aria-label="`${expanded ? 'Collapse' : 'Expand'} ${node.name}`"
      @click="expanded = !expanded"
    >
      <i :class="['fas', expanded ? 'fa-folder-open' : 'fa-folder']" class="node-icon dir-icon"></i>
      <i :class="['fas', expanded ? 'fa-chevron-down' : 'fa-chevron-right']" class="chevron"></i>
      <span class="node-name">{{ node.name }}</span>
    </button>

    <div v-else class="node-row node-file">
      <Icon name="file-alt" class="node-icon file-icon" />
      <span class="node-name">{{ node.name }}</span>
    </div>

    <div v-if="node.is_dir && expanded && node.children?.length" role="group">
      <SandboxTreeNode
        v-for="child in node.children"
        :key="child.path"
        :node="child"
        :depth="depth + 1"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref } from 'vue'
import type { SandboxTreeNode as SandboxTreeNodeType } from '@/composables/useFileSandbox'

defineProps<{ node: SandboxTreeNodeType; depth: number }>()

const expanded = ref(false)
</script>

<style scoped>
.sandbox-tree-node {
  line-height: 1.6;
}

.node-row {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  width: 100%;
  cursor: default;
  font-size: 0.875rem;
  color: var(--text-primary, #e0e0e0);
  padding: 0.15rem 0.5rem 0.15rem 0;
  border-radius: 0.25rem;
  background: none;
  border: none;
  text-align: left;
  transition: background 0.1s;
}

.node-dir {
  cursor: pointer;
}

.node-row:hover {
  background: var(--bg-hover, rgba(255, 255, 255, 0.06));
}

.node-icon {
  width: 1rem;
  flex-shrink: 0;
  font-size: 0.8rem;
}

.dir-icon {
  color: #fbbf24;
}

.file-icon {
  color: var(--text-secondary, rgba(255, 255, 255, 0.5));
}

.chevron {
  font-size: 0.65rem;
  color: var(--text-secondary, rgba(255, 255, 255, 0.4));
  width: 0.65rem;
  flex-shrink: 0;
}

.node-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
