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
      <span v-else-if="node.type === 'file' && node.size" class="node-size">
        {{ formatSize(node.size) }}
      </span>

      <!-- Vectorization status badge for files -->
      <VectorizationStatusBadge
        v-if="node.type === 'file'"
        :status="vectorizationStatus"
        :compact="true"
      />

      <!-- Vectorize button for non-vectorized files -->
      <button
        v-if="node.type === 'file' && canVectorize"
        class="vectorize-btn"
        title="Vectorize this document"
        @click.stop="$emit('vectorize', node.id)"
      >
        <i class="fas fa-cube"></i>
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

// Helper function
const formatSize = (bytes: number): string => {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)}KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`
}
</script>

<style scoped>
/* Tree node */
.tree-node {
  user-select: none;
}

.node-content {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  cursor: pointer;
  border-radius: 0.375rem;
  transition: all 0.15s;
  margin: 0.125rem 0;
}

.node-content:hover {
  background: #f3f4f6;
}

.node-content.is-selected {
  background: #eff6ff;
  color: #3b82f6;
  font-weight: 500;
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
  color: #6b7280;
  cursor: pointer;
  padding: 0;
  transition: transform 0.2s;
}

.expand-btn:hover {
  color: #374151;
}

.expand-spacer {
  width: 1.25rem;
}

.node-icon {
  color: #3b82f6;
  font-size: 0.875rem;
  min-width: 1rem;
  cursor: pointer;
}

.node-name {
  flex: 1;
  font-size: 0.875rem;
  color: #374151;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
}

.folder-count {
  font-size: 0.75rem;
  color: #6b7280;
  background: #f3f4f6;
  padding: 0.125rem 0.5rem;
  border-radius: 0.375rem;
  margin-left: 0.5rem;
  font-weight: 500;
}

.node-size {
  font-size: 0.75rem;
  color: #9ca3af;
}

.vectorize-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.75rem;
  height: 1.75rem;
  background: #3b82f6;
  color: white;
  border: none;
  border-radius: 0.25rem;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 0.75rem;
}

.vectorize-btn:hover {
  background: #2563eb;
  transform: scale(1.1);
}

.node-children {
  padding-left: 1.5rem;
}
</style>
