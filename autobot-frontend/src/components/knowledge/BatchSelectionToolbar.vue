<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  BatchSelectionToolbar (#3388, #22332) — the document-list adapter over the one selection bar,
  KnowledgeBatchToolbar. It takes the selected documents with their vectorization status, decides
  which are eligible with the shared `isVectorizable` rule (`pending` = not yet vectorized =
  vectorizable) and emits the eligible ids; the markup and styling are KnowledgeBatchToolbar's.
-->
<template>
  <KnowledgeBatchToolbar
    :has-selection="selectedDocuments.length > 0"
    :selection-count="selectedDocuments.length"
    :can-vectorize="eligibleIds.length > 0"
    :eligible-count="eligibleIds.length"
    :is-vectorizing="isVectorizing"
    @vectorize="onVectorize"
    @deselect-all="emit('deselect-all')"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import KnowledgeBatchToolbar from './KnowledgeBatchToolbar.vue'
import { isVectorizable } from '@/composables/knowledge/vectorizable'
import type { VectorizationStatus } from '@/composables/useKnowledgeVectorization'

interface SelectedDocumentInfo {
  id: string
  status: VectorizationStatus
}

const props = withDefaults(
  defineProps<{
    /** Documents currently selected by the user */
    selectedDocuments: SelectedDocumentInfo[]
    /** True while a batch vectorization job is in flight */
    isVectorizing?: boolean
  }>(),
  { isVectorizing: false },
)

const emit = defineEmits<{
  /** Request batch vectorization for the eligible document ids */
  (e: 'vectorize', documentIds: string[]): void
  /** Request clearing the current selection */
  (e: 'deselect-all'): void
}>()

const eligibleIds = computed(() => props.selectedDocuments.filter((d) => isVectorizable(d.status)).map((d) => d.id))

function onVectorize(): void {
  if (eligibleIds.value.length > 0 && !props.isVectorizing) emit('vectorize', eligibleIds.value)
}
</script>
