<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  BasePagination — the page bar under a list or table (#14780 group 1).

  Presentation for the kit's usePagination (which owns the page state) and for server-paged
  lists that only know whether another page exists. Its API comes from the bars it replaces:
  a "Page X of Y" summary with Previous / Next, and First / Last where the total is known.

    props   : page (v-model:page, 1-based), totalPages (when known), hasNext (when only that is
              known, e.g. cursor paging), showFirstLast, labels (translated button text),
              label (names the nav landmark; a plain `aria-label` would land on
              the root as an attribute and leave the prop unset), disabled
    slots   : summary (left side, e.g. "Page 2 of 7")
    emits   : update:page

  The kit ships no user-facing text: every label comes in translated from the app.
-->
<script setup lang="ts">
import { computed } from 'vue'
import BaseButton from './BaseButton.vue'

export interface PaginationLabels {
  previous: string
  next: string
  first?: string
  last?: string
}

const props = withDefaults(
  defineProps<{
    page: number
    totalPages?: number
    hasNext?: boolean
    showFirstLast?: boolean
    labels: PaginationLabels
    label: string
    disabled?: boolean
  }>(),
  { totalPages: undefined, hasNext: undefined, showFirstLast: false, disabled: false },
)

const emit = defineEmits<{ 'update:page': [page: number] }>()

const known = computed(() => props.totalPages !== undefined)
const canPrev = computed(() => !props.disabled && props.page > 1)
const canNext = computed(() => !props.disabled && (props.hasNext ?? (known.value && props.page < (props.totalPages ?? 0))))
const showEnds = computed(() => props.showFirstLast && known.value && !!props.labels.first && !!props.labels.last)

// Never emits a page outside 1..totalPages (when known): a page past the end steps back into range
// instead of further out, so the kit does not rely on the caller's own bounds check (#19078 review).
function go(page: number): void {
  const last = known.value ? Math.max(1, props.totalPages ?? 1) : Infinity
  const target = Math.min(last, Math.max(1, page))
  if (target !== props.page) emit('update:page', target)
}
</script>

<template>
  <nav class="aui-pagination" :aria-label="label">
    <div class="aui-pagination__summary"><slot name="summary" /></div>
    <div class="aui-pagination__controls">
      <BaseButton v-if="showEnds" size="sm" variant="secondary" :disabled="!canPrev" @click="go(1)">{{ labels.first }}</BaseButton>
      <BaseButton size="sm" variant="secondary" :disabled="!canPrev" @click="go(page - 1)">{{ labels.previous }}</BaseButton>
      <BaseButton size="sm" variant="secondary" :disabled="!canNext" @click="go(page + 1)">{{ labels.next }}</BaseButton>
      <BaseButton v-if="showEnds" size="sm" variant="secondary" :disabled="!canNext" @click="go(totalPages!)">{{ labels.last }}</BaseButton>
    </div>
  </nav>
</template>

<style scoped>
.aui-pagination {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--aui-space-3);
  font-family: var(--aui-font-sans);
}

.aui-pagination__summary {
  font-size: var(--aui-text-sm);
  color: var(--aui-color-text-muted);
}

.aui-pagination__controls {
  display: flex;
  gap: var(--aui-space-1);
  margin-left: auto;
}
</style>
