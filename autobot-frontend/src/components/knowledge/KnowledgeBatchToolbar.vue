<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  KnowledgeBatchToolbar — the selection bar of the Knowledge Browser (#18244, Refined UI
  "Knowledge · Browser"): "N documents selected", Vectorize Selected, Clear Selection. It is the
  one selection bar for the tree: it replaces the inline copy that lived in KnowledgeBrowser,
  and carries the eligible-count note of the unmounted BatchSelectionToolbar. Advanced-only.
-->
<template>
  <div v-if="hasSelection" class="batch-toolbar adv" role="toolbar" :aria-label="$t('knowledge.batchToolbar.label')">
    <strong class="batch-count">{{ $t('knowledge.batchToolbar.documentsSelected', { count: selectionCount }) }}</strong>
    <span v-if="eligibleCount !== undefined && eligibleCount < selectionCount" class="batch-eligible">
      {{ $t('knowledge.batchSelection.eligible', { count: eligibleCount }) }}
    </span>
    <BaseTooltip :text="$t('knowledge.batchToolbar.vectorizeTip')" placement="top">
      <template #default="{ describedby }">
        <BaseButton
          variant="primary"
          size="sm"
          class="batch-vectorize"
          :disabled="!canVectorize || isVectorizing"
          :loading="isVectorizing"
          :aria-describedby="describedby"
          @click="$emit('vectorize')"
        >
          {{ $t('knowledge.batchToolbar.vectorizeSelected') }}
        </BaseButton>
      </template>
    </BaseTooltip>
    <BaseButton variant="outline" size="sm" @click="$emit('deselect-all')">
      {{ $t('knowledge.batchToolbar.clearSelection') }}
    </BaseButton>
  </div>
</template>

<script setup lang="ts">
import { BaseButton, BaseTooltip } from '@autobot/ui'

withDefaults(
  defineProps<{
    hasSelection: boolean
    selectionCount: number
    canVectorize: boolean
    isVectorizing?: boolean
    /** Selected documents that still need vectorizing; the note shows when it is below the selection. */
    eligibleCount?: number
  }>(),
  { isVectorizing: false, eligibleCount: undefined },
)

defineEmits<{
  vectorize: []
  'deselect-all': []
}>()
</script>

<style scoped>
.batch-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3);
  border-radius: var(--radius-lg);
  background: var(--surface2);
  border: var(--bw) solid var(--border);
  font-size: var(--text-sm);
  color: var(--text);
}

.batch-count {
  font-weight: 600;
}

.batch-eligible {
  color: var(--muted);
}

.batch-vectorize {
  margin-inline-start: auto;
}
</style>
