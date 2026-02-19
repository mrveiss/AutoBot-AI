<template>
  <div class="tree-node">
    <div
      :class="{
        'node-content': true,
        'is-folder': node.type === 'folder',
        'is-file': node.type === 'file',
        'is-expanded': node.type === 'folder' && expandedNodes.has(node.id),
        'is-selected': node.id === selectedId
      }"
    >
      <!-- Checkbox for files -->
      <input
        v-if="node.type === 'file'"
        type="checkbox"
        class="node-checkbox"
        :checked="isSelected"
        @click.stop="$emit('toggle-select', node.id)"
      />
      <span v-else class="checkbox-spacer"></span>

      <!-- Expand button for folders -->
      <button
        v-if="node.type === 'folder'"
        class="expand-btn"
        @click.stop="$emit('toggle', node.id)"
      >
        <i :class="['fas', expandedNodes.has(node.id) ? 'fa-chevron-down' : 'fa-chevron-right']"></i>
      </button>
      <span v-else class="expand-spacer"></span>

      <!-- Node icon -->
      <i :class="['node-icon', nodeIcon]" @click="$emit('select', node)"></i>

      <!-- Node name -->
      <span class="node-name" @click="$emit('select', node)">{{ node.name }}</span>

      <!-- Folder count or file size -->
      <span v-if="node.type === 'folder' && node.children" class="folder-count">
        {{ node.children.length }} items
      </span>
      <span v-else-if="node.type === 'file' && node.size !== undefined" class="node-size">
        {{ formatSize(node.size) }}
      </span>

      <!-- Unvectorized count badge for folders -->
      <button
        v-if="node.type === 'folder' && unvectorizedCount > 0"
        class="unvectorized-badge"
        :title="`Click to vectorize ${unvectorizedCount} document${unvectorizedCount !== 1 ? 's' : ''}`"
        @click.stop="$emit('vectorize-folder', node)"
      >
        <i class="fas fa-exclamation-circle"></i>
        {{ unvectorizedCount }} unvectorized
        <i class="fas fa-play-circle"></i>
      </button>

      <!-- Vectorization status badge for files -->
      <VectorizationStatusBadge
        v-if="node.type === 'file'"
        :status="vectorizationStatus"
        :compact="true"
      />

      <!-- Vectorize button for non-vectorized files -->
      <button
        v-if="node.type === 'file' && canVectorize"
        :class="['vectorize-btn', { 'retry-btn': vectorizationStatus === 'failed' }]"
        :title="vectorizationStatus === 'failed' ? 'Retry vectorization' : 'Vectorize this document'"
        @click.stop="$emit('vectorize', node.id)"
      >
        <i :class="vectorizationStatus === 'failed' ? 'fas fa-redo' : 'fas fa-cube'"></i>
      </button>
    </div>

    <!-- Children (recursive) -->
    <div
      v-if="node.type === 'folder' && expandedNodes.has(node.id) && node.children"
      class="node-children"
    >
      <TreeNodeComponent
        v-for="child in node.children"
        :key="child.id"
        :node="child"
        :expanded-nodes="expandedNodes"
        :selected-id="selectedId"
        :selected-documents="selectedDocuments"
        :vectorization-states="vectorizationStates"
        @toggle="$emit('toggle', $event)"
        @select="$emit('select', $event)"
        @toggle-select="$emit('toggle-select', $event)"
        @vectorize="$emit('vectorize', $event)"
        @vectorize-folder="$emit('vectorize-folder', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import VectorizationStatusBadge from './VectorizationStatusBadge.vue'
import { useKnowledgeVectorization } from '@/composables/useKnowledgeVectorization'

// Tree node interface
export interface TreeNode {
  id: string
  name: string
  type: 'folder' | 'file'
  path: string
  children?: TreeNode[]
  size?: number
  date?: string
  category?: string
  metadata?: any
  content?: string
}

// Props
interface Props {
  node: TreeNode
  expandedNodes: Set<string>
  selectedId?: string
  selectedDocuments: Set<string>
  vectorizationStates: Map<string, any>
}

const props = withDefaults(defineProps<Props>(), {
  selectedId: undefined
})

// Emits
defineEmits<{
  'toggle': [nodeId: string]
  'select': [node: TreeNode]
  'toggle-select': [documentId: string]
  'vectorize': [documentId: string]
  'vectorize-folder': [node: TreeNode]
}>()

// Get document status from vectorization composable
const { getDocumentStatus } = useKnowledgeVectorization()

// Computed properties
const nodeIcon = computed(() => {
  if (props.node.type === 'folder') {
    return props.expandedNodes.has(props.node.id) ? 'fas fa-folder-open' : 'fas fa-folder'
  }
  return 'fas fa-file-alt'
})

const isSelected = computed(() => {
  return props.selectedDocuments.has(props.node.id)
})

const vectorizationStatus = computed(() => {
  const state = props.vectorizationStates.get(props.node.id)
  return state?.status || getDocumentStatus(props.node.id)
})

const canVectorize = computed(() => {
  if (props.node.type !== 'file') return false
  return vectorizationStatus.value !== 'vectorized'
})

// Count unvectorized documents in a folder (recursive)
const unvectorizedCount = computed(() => {
  if (props.node.type !== 'folder' || !props.node.children) return 0

  const countUnvectorized = (node: TreeNode): number => {
    if (node.type === 'file') {
      const state = props.vectorizationStates.get(node.id)
      const status = state?.status || getDocumentStatus(node.id)
      return status !== 'vectorized' ? 1 : 0
    }

    if (node.type === 'folder' && node.children) {
      return node.children.reduce((sum, child) => sum + countUnvectorized(child), 0)
    }

    return 0
  }

  return countUnvectorized(props.node)
})

// Helper function
const formatSize = (bytes: number): string => {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)}KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`
}
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
/* Tree node */
.tree-node {
  user-select: none;
}

.node-content {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-3);
  cursor: pointer;
  border-radius: var(--radius-md);
  transition: all var(--duration-150) var(--ease-in-out);
  margin: var(--spacing-0-5) 0;
}

.node-content:hover {
  background: var(--bg-secondary);
}

.node-content.is-selected {
  background: var(--color-primary-bg);
  color: var(--color-primary);
  font-weight: var(--font-medium);
}

.node-checkbox {
  width: 1rem;
  height: 1rem;
  cursor: pointer;
  flex-shrink: 0;
}

.checkbox-spacer {
  width: 1rem;
  flex-shrink: 0;
}

.expand-btn {
  width: 1.25rem;
  height: 1.25rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 0;
  transition: transform var(--duration-200) var(--ease-in-out);
}

.expand-btn:hover {
  color: var(--text-primary);
}

.expand-spacer {
  width: 1.25rem;
}

.node-icon {
  color: var(--color-primary);
  font-size: var(--text-sm);
  min-width: 1rem;
  cursor: pointer;
}

.node-name {
  flex: 1 1 0;
  min-width: 0;
  font-size: var(--text-sm);
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
}

.folder-count {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  background: var(--bg-secondary);
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-md);
  margin-left: var(--spacing-2);
  font-weight: var(--font-medium);
}

.node-size {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.unvectorized-badge {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  font-size: var(--text-xs);
  color: var(--color-error);
  background: var(--color-error-bg);
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-md);
  margin-left: var(--spacing-2);
  font-weight: var(--font-medium);
  border: 1px solid var(--color-error-border);
  cursor: pointer;
  transition: all var(--duration-200) var(--ease-in-out);
}

.unvectorized-badge:hover {
  background: var(--color-error-bg-hover);
  border-color: var(--color-error);
  transform: translateX(2px);
  box-shadow: var(--shadow-sm);
}

.unvectorized-badge i {
  font-size: var(--text-xs);
}

.unvectorized-badge i.fa-play-circle {
  font-size: var(--text-sm);
  margin-left: var(--spacing-1);
  opacity: 0.7;
}

.unvectorized-badge:hover i.fa-play-circle {
  opacity: 1;
  color: var(--color-error-hover);
}

.vectorize-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.75rem;
  height: 1.75rem;
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--duration-200) var(--ease-in-out);
  font-size: var(--text-xs);
}

.vectorize-btn:hover {
  background: var(--color-primary-hover);
  transform: scale(1.1);
}

.vectorize-btn.retry-btn {
  background: var(--color-error);
}

.vectorize-btn.retry-btn:hover {
  background: var(--color-error-hover);
}

.node-children {
  padding-left: var(--spacing-6);
}
</style>
