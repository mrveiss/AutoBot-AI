<template>
  <div
    class="tree-node"
    role="treeitem"
    :aria-level="level"
    :aria-expanded="isFolder ? isExpanded : undefined"
    :aria-selected="node.id === selectedId"
  >
    <div
      :class="{
        'node-content': true,
        'is-folder': isFolder,
        'is-file': !isFolder,
        'is-expanded': isExpanded,
        'is-selected': node.id === selectedId
      }"
      :style="{ '--tree-level': level }"
    >
      <input
        v-if="!isFolder"
        type="checkbox"
        class="node-checkbox"
        :checked="isSelected"
        :aria-label="$t('knowledge.treeNode.selectDocument', { name: displayName })"
        @click.stop="$emit('toggle-select', node.id)"
      />

      <button class="node-name-btn" type="button" @click.stop="$emit('select', node)">
        <Icon v-if="isFolder" :name="isExpanded ? 'chevron-down' : 'chevron-right'" class="node-chevron" aria-hidden="true" />
        <Icon :name="nodeIcon" class="node-icon" aria-hidden="true" />
        <span class="node-label" :class="{ 'is-strong': isFolder }">{{ displayName }}</span>
      </button>

      <BaseTooltip v-if="isFolder && node.children" :text="$t('knowledge.treeNode.itemsCount', { count: node.children.length })" placement="left">
        <template #default="{ describedby }">
          <span class="folder-count" tabindex="0" :aria-describedby="describedby">{{ node.children.length }}</span>
        </template>
      </BaseTooltip>
      <span v-else-if="node.size !== undefined" class="node-size">{{ formatFileSize(node.size, sizeOptions) }}</span>

      <BaseTooltip v-if="isFolder && unvectorizedCount > 0" class="adv" :text="$t('knowledge.treeNode.vectorizeFolderTitle', { count: unvectorizedCount })" placement="left">
        <template #default="{ describedby }">
          <BaseButton
            variant="ghost"
            size="xs"
            class="unvectorized-badge"
            :aria-describedby="describedby"
            @click.stop="$emit('vectorize-folder', node)"
          >
            {{ $t('knowledge.treeNode.unvectorized', { count: unvectorizedCount }) }}
            <Icon name="play-circle" aria-hidden="true" />
          </BaseButton>
        </template>
      </BaseTooltip>

      <VectorizationStatusBadge v-if="!isFolder" class="adv" :status="vectorizationStatus" :show-label="true" />

      <BaseTooltip v-if="!isFolder && canVectorize" class="adv" :text="vectorizeTip" placement="left">
        <template #default="{ describedby }">
          <BaseButton
            variant="ghost"
            size="xs"
            class="vectorize-btn"
            :class="{ 'retry-btn': vectorizationStatus === 'failed' }"
            :aria-label="vectorizeTip"
            :aria-describedby="describedby"
            @click.stop="$emit('vectorize', node.id)"
          >
            <Icon :name="vectorizationStatus === 'failed' ? 'redo' : 'cube'" aria-hidden="true" />
          </BaseButton>
        </template>
      </BaseTooltip>
    </div>

    <div v-if="isExpanded && node.children" class="node-children" role="group">
      <TreeNodeComponent
        v-for="child in node.children"
        :key="child.id"
        :node="child"
        :level="level + 1"
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
import Icon from '@/components/ui/Icon.vue'
import { BaseButton, BaseTooltip } from '@autobot/ui'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { formatFileSize, formatManPageTitle, knowledgeNodeFactType } from '@/utils/formatHelpers'
import VectorizationStatusBadge from './VectorizationStatusBadge.vue'
import type { DocumentVectorizationState } from '@/composables/useKnowledgeVectorization'

// Metadata attached to a knowledge tree node. Mirrors the KnowledgeFactLike
// shape produced by the knowledge browser (all fields optional).
export interface TreeNodeMetadata {
  key?: string
  title?: string
  source?: string
  content?: string
  // Issue #12370: full_content removed — lazy-loaded via GET /fact/{fact_key}.
  timestamp?: string
  created_at?: string
  category?: string
  metadata?: Record<string, unknown>
}

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
  metadata?: TreeNodeMetadata
  content?: string
}

// Props
interface Props {
  node: TreeNode
  expandedNodes: Set<string>
  selectedId?: string
  selectedDocuments: Set<string>
  vectorizationStates: Map<string, DocumentVectorizationState>
  /** Depth in the tree, 1 for a top-level node (aria-level and the indent). */
  level?: number
}

const props = withDefaults(defineProps<Props>(), {
  selectedId: undefined,
  level: 1
})

// Emits
defineEmits<{
  'toggle': [nodeId: string]
  'select': [node: TreeNode]
  'toggle-select': [documentId: string]
  'vectorize': [documentId: string]
  'vectorize-folder': [node: TreeNode]
}>()

// Computed properties
const isFolder = computed(() => props.node.type === 'folder')
const isExpanded = computed(() => isFolder.value && props.expandedNodes.has(props.node.id))

const nodeIcon = computed(() => {
  if (isFolder.value) return isExpanded.value ? 'folder-open' : 'folder'
  return 'file-alt'
})

const isSelected = computed(() => {
  return props.selectedDocuments.has(props.node.id)
})

const vectorizationStatus = computed(() => {
  const state = props.vectorizationStates.get(props.node.id)
  // parent (KnowledgeBrowser) owns the authoritative state map via the
  // vectorization-states prop; 'pending' is the default for unknown docs
  return state?.status || 'pending'
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
      // parent (KnowledgeBrowser) owns the authoritative state map
      const status = state?.status || 'pending'
      return status !== 'vectorized' ? 1 : 0
    }

    if (node.type === 'folder' && node.children) {
      return node.children.reduce((sum, child) => sum + countUnvectorized(child), 0)
    }

    return 0
  }

  return countUnvectorized(props.node)
})

const { t } = useI18n()

const vectorizeTip = computed(() =>
  vectorizationStatus.value === 'failed' ? t('knowledge.treeNode.retryTitle') : t('knowledge.treeNode.vectorizeTitle'),
)

// #21037: display-only man-page label; node.name stays raw for search/icons.
const displayName = computed(() =>
  formatManPageTitle(props.node.name, knowledgeNodeFactType(props.node.metadata), t),
)

const sizeOptions = computed(() => ({
  decimals: [0, 0, 1],
  units: ['B', 'KB', 'MB'],
  integerBase: true,
  keepTrailingZeros: true,
  separator: '',
  zeroText: t('knowledge.treeNode.zeroSize'),
}))
</script>

<style scoped>
.tree-node {
  display: block;
}

.node-content {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-1) var(--spacing-2);
  padding-inline-start: calc(var(--spacing-2) + (var(--tree-level, 1) - 1) * var(--spacing-5));
  border-radius: var(--radius-md);
  border-inline-start: 3px solid transparent;
  font-size: var(--text-sm);
  color: var(--text);
}

.node-content:hover {
  background: var(--surface2);
}

.node-content.is-selected {
  background: var(--surface2);
  border-inline-start-color: var(--primary);
}

.node-checkbox {
  inline-size: 16px;
  block-size: 16px;
  flex: none;
  accent-color: var(--primary);
}

.node-name-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  flex: 1;
  min-inline-size: 0;
  padding: var(--spacing-1) 0;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: start;
  cursor: pointer;
}

.node-name-btn:focus-visible {
  outline: 3px solid var(--focus);
  outline-offset: 2px;
  border-radius: var(--radius-sm);
}

.node-chevron,
.node-icon {
  flex: none;
  color: var(--stroke);
}

.node-label {
  min-inline-size: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.node-label.is-strong {
  font-weight: 600;
}

.is-selected .node-label {
  font-weight: 600;
}

.folder-count,
.node-size {
  flex: none;
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--muted);
}

.vectorize-btn.retry-btn {
  color: var(--bad-fg);
}

.node-children {
  display: block;
}
</style>
