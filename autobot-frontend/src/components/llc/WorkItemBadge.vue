<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Author: mrveiss -->
<script setup lang="ts">
/**
 * Shared work-item enum badge (#11076 part 3).
 *
 * Pairs a work-item `type` / `priority` / `status` enum value with its localized
 * label (via useWorkItemLabels) and the shared color palette, replacing the
 * `.type-*` / `.priority-*` / `.status-*` CSS that was duplicated across the LLC
 * board views. `variant="dot"` renders the compact priority indicator used on
 * dense cards; `size` matches each host context's original badge sizing so the
 * extraction is visually identical.
 */
import { computed } from 'vue'
import { useWorkItemLabels } from '@/composables/useWorkItemLabels'

const props = withDefaults(
  defineProps<{
    kind: 'type' | 'priority' | 'status'
    value: string | null | undefined
    variant?: 'pill' | 'dot'
    size?: 'xs' | 'sm' | 'md'
  }>(),
  { variant: 'pill', size: 'md' },
)

const { workItemTypeLabel, workItemStatusLabel, priorityLabel } = useWorkItemLabels()

const label = computed(() => {
  if (props.kind === 'type') return workItemTypeLabel(props.value)
  if (props.kind === 'status') return workItemStatusLabel(props.value)
  return priorityLabel(props.value)
})

const colorClass = computed(() =>
  props.variant === 'dot' ? `dot-${props.value}` : `${props.kind}-${props.value}`,
)
</script>

<template>
  <span v-if="variant === 'dot'" class="wib-dot" :class="[`wib-dot--${size}`, colorClass]" :title="label" />
  <span v-else class="wib" :class="[`wib--${size}`, colorClass]">{{ label }}</span>
</template>

<style scoped>
.wib {
  display: inline-block;
  border-radius: 9999px;
  font-weight: 500;
  text-transform: capitalize;
}
.wib--xs { font-size: 0.6rem; padding: 0.1rem 0.35rem; }
.wib--sm { font-size: 0.65rem; padding: 0.1rem 0.4rem; }
.wib--md { font-size: 0.75rem; padding: 0.125rem 0.5rem; }

.wib-dot {
  display: inline-block;
  border-radius: 50%;
  flex-shrink: 0;
}
/* dot dimensions match each host: SprintBoard 0.5rem (md), Kanban 0.45rem (xs) */
.wib-dot--md { width: 0.5rem; height: 0.5rem; }
.wib-dot--sm { width: 0.5rem; height: 0.5rem; }
.wib-dot--xs { width: 0.45rem; height: 0.45rem; }

/* type palette (identical across all LLC boards) */
.type-epic { background: #ddd6fe; color: #5b21b6; }
.type-feature { background: #bfdbfe; color: #1d4ed8; }
.type-pbi { background: #d1fae5; color: #065f46; }
.type-task { background: #e0f2fe; color: #0369a1; }
.type-bug { background: #fee2e2; color: #991b1b; }
.type-spike { background: #fef3c7; color: #92400e; }
.type-subtask { background: #f3f4f6; color: #374151; }
.type-risk { background: #fce7f3; color: #9d174d; }

/* work-item status palette (from WorkItemDetail) */
.status-backlog { background: #f3f4f6; color: #374151; }
.status-ready { background: #e0f2fe; color: #0369a1; }
.status-in_progress { background: #ddd6fe; color: #5b21b6; }
.status-in_review { background: #fef9c3; color: #713f12; }
.status-done { background: #d1fae5; color: #065f46; }
.status-blocked { background: #fee2e2; color: #991b1b; }
.status-cancelled { background: #f3f4f6; color: #9ca3af; }

/* priority pill palette (Backlog / WorkItemDetail) */
.priority-critical { background: #fee2e2; color: #991b1b; }
.priority-high { background: #ffedd5; color: #9a3412; }
.priority-medium { background: #fef9c3; color: #713f12; }
.priority-low { background: #f0fdf4; color: #14532d; }

/* priority dot palette (SprintBoard / Kanban — solid fills) */
.dot-critical { background: #ef4444; }
.dot-high { background: #f97316; }
.dot-medium { background: #eab308; }
.dot-low { background: #22c55e; }
</style>
