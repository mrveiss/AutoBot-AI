<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  KnowledgeTreePane — the document tree of the Knowledge Browser (#18244): loading, error
  and empty states, the tree itself (role="tree"), Load More for the paginated categorised
  browse (#12394), and the AI documents branch (#11526) under it. It owns no data; the Browser
  passes the tree and listens to the events.
-->
<template>
  <div class="kb-tree-pane">
    <div v-if="isLoading" class="kb-tree-state" role="status">
      <BaseSpinner />
      <p>{{ $t('knowledge.browser.loadingFileTree') }}</p>
    </div>

    <div v-else-if="error" class="kb-tree-state">
      <BaseAlert variant="error" :message="error.message" />
      <BaseButton variant="primary" size="sm" @click="$emit('retry')">{{ $t('knowledge.browser.retryBtn') }}</BaseButton>
    </div>

    <template v-else>
      <EmptyState v-if="nodes.length === 0" :description="$t('knowledge.browser.noItemsFound')">
        <template #icon><Icon name="folder-open" size="xl" aria-hidden="true" /></template>
      </EmptyState>
      <div v-else role="tree" class="kb-tree" :aria-label="$t('knowledge.browser.treeLabel')">
        <TreeNodeComponent
          v-for="node in nodes"
          :key="node.id"
          :node="node"
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

      <div v-if="hasMore && !isLoadingMore" class="kb-tree-more">
        <BaseButton variant="outline" size="sm" @click="$emit('load-more')">{{ $t('knowledge.browser.loadMore') }}</BaseButton>
      </div>
      <div v-if="isLoadingMore" class="kb-tree-state" role="status">
        <BaseSpinner size="sm" />
        <span>{{ $t('knowledge.browser.loadingMoreEntries') }}</span>
      </div>

      <KnowledgeDocumentsBranch
        :selected-doc-id="selectedDocId"
        @select="$emit('doc-select', $event)"
        @deleted="$emit('doc-deleted', $event)"
        @error="$emit('doc-error', $event)"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { BaseAlert, BaseButton, BaseSpinner, EmptyState } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import TreeNodeComponent, { type TreeNode } from './TreeNodeComponent.vue'
import KnowledgeDocumentsBranch from './KnowledgeDocumentsBranch.vue'
import type { DocumentVectorizationState } from '@/composables/useKnowledgeVectorization'

defineProps<{
  isLoading: boolean
  error: Error | null
  nodes: TreeNode[]
  expandedNodes: Set<string>
  selectedId?: string
  selectedDocuments: Set<string>
  vectorizationStates: Map<string, DocumentVectorizationState>
  hasMore: boolean
  isLoadingMore: boolean
  selectedDocId: string | null
}>()

defineEmits<{
  retry: []
  toggle: [nodeId: string]
  select: [node: TreeNode]
  'toggle-select': [documentId: string]
  vectorize: [documentId: string]
  'vectorize-folder': [node: TreeNode]
  'load-more': []
  'doc-select': [id: string]
  'doc-deleted': [id: string]
  'doc-error': [message: string]
}>()
</script>

<style scoped>
.kb-tree-pane {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
  min-block-size: 0;
  overflow-y: auto;
}

.kb-tree {
  display: flex;
  flex-direction: column;
}

.kb-tree-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-6);
  color: var(--muted);
}

.kb-tree-more {
  display: flex;
  justify-content: center;
}
</style>
