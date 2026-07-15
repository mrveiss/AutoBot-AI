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

/* type palette — theme-adaptive categorical tokens (GH#10868) */
.type-epic { background: var(--badge-type-epic-bg); color: var(--badge-type-epic-fg); }
.type-feature { background: var(--badge-type-feature-bg); color: var(--badge-type-feature-fg); }
.type-pbi { background: var(--badge-type-pbi-bg); color: var(--badge-type-pbi-fg); }
.type-task { background: var(--badge-type-task-bg); color: var(--badge-type-task-fg); }
.type-bug { background: var(--badge-type-bug-bg); color: var(--badge-type-bug-fg); }
.type-spike { background: var(--badge-type-spike-bg); color: var(--badge-type-spike-fg); }
.type-subtask { background: var(--badge-type-subtask-bg); color: var(--badge-type-subtask-fg); }
.type-risk { background: var(--badge-type-risk-bg); color: var(--badge-type-risk-fg); }

/* work-item status palette — theme-adaptive (GH#10868) */
.status-backlog { background: var(--badge-status-backlog-bg); color: var(--badge-status-backlog-fg); }
.status-ready { background: var(--badge-status-ready-bg); color: var(--badge-status-ready-fg); }
.status-in_progress { background: var(--badge-status-in_progress-bg); color: var(--badge-status-in_progress-fg); }
.status-in_review { background: var(--badge-status-in_review-bg); color: var(--badge-status-in_review-fg); }
.status-done { background: var(--badge-status-done-bg); color: var(--badge-status-done-fg); }
.status-blocked { background: var(--badge-status-blocked-bg); color: var(--badge-status-blocked-fg); }
.status-cancelled { background: var(--badge-status-cancelled-bg); color: var(--badge-status-cancelled-fg); }

/* priority pill palette — theme-adaptive (GH#10868) */
.priority-critical { background: var(--badge-priority-critical-bg); color: var(--badge-priority-critical-fg); }
.priority-high { background: var(--badge-priority-high-bg); color: var(--badge-priority-high-fg); }
.priority-medium { background: var(--badge-priority-medium-bg); color: var(--badge-priority-medium-fg); }
.priority-low { background: var(--badge-priority-low-bg); color: var(--badge-priority-low-fg); }

/* priority dot palette — solid fills, theme-adaptive (GH#10868) */
.dot-critical { background: var(--badge-dot-critical); }
.dot-high { background: var(--badge-dot-high); }
.dot-medium { background: var(--badge-dot-medium); }
.dot-low { background: var(--badge-dot-low); }
</style>
