<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Author: mrveiss -->
<script setup lang="ts">
// The Org Chart's executor rollup panel (#13942): work items counted by
// executor class (person / AI agent / unassigned) and by status.
//
// The unassigned bucket is the point — it is the work nobody owns — so it is
// never hidden even at zero, and it is never a subtraction. See
// `composables/llc/executorRollup.ts` for how the matrix is built and why
// "person / automation / AI agent" collapses to "person / AI agent" here.

import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import WorkItemBadge from './WorkItemBadge.vue'
import {
  EXECUTOR_CLASSES,
  executorClassTotals,
  rollupTotal,
  statusesPresent,
} from '@/composables/llc/executorRollup'
import type { ExecutorClass, ExecutorRollupMatrix } from '@/composables/llc/executorRollup'
import type { WorkItemStatus } from '@/views/llc/workItemTypes'

const props = defineProps<{
  matrix: ExecutorRollupMatrix
  loading: boolean
  /**
   * A source that did not answer. Distinct from a source that answered "zero
   * work items" — a failed fetch must never render as a zero count (#14064's
   * family; the same precedent #14104 shipped as `peopleUnavailable`).
   */
  unavailable: boolean
}>()

const { t } = useI18n()

/** Declared status order (`workItemTypes.ts`) — the columns' stable order. */
const STATUS_ORDER: readonly WorkItemStatus[] = [
  'backlog',
  'ready',
  'in_progress',
  'in_review',
  'done',
  'blocked',
  'cancelled',
]

const CLASS_BADGE_CLASS: Record<ExecutorClass, string> = {
  user: 'bg-autobot-info-bg text-autobot-info border-autobot-info',
  agent: 'bg-autobot-primary-bg text-autobot-primary border-autobot-primary',
  unassigned: 'bg-autobot-warning-bg text-autobot-warning border-autobot-warning',
}

function classLabel(executorClass: ExecutorClass): string {
  return t(`llc.executorRollup.class.${executorClass}`)
}

const totals = computed(() => executorClassTotals(props.matrix))
const total = computed(() => rollupTotal(props.matrix))
const visibleStatuses = computed(() => statusesPresent(props.matrix, STATUS_ORDER))

function cellCount(executorClass: ExecutorClass, status: WorkItemStatus): number {
  return props.matrix[executorClass][status] ?? 0
}
</script>

<template>
  <section
    data-testid="executor-rollup"
    class="space-y-3 rounded-lg border border-autobot-border bg-autobot-bg-card p-3"
    :aria-label="t('llc.executorRollup.title')"
  >
    <div class="flex items-center justify-between">
      <h2 class="text-sm font-semibold text-autobot-text-primary">{{ t('llc.executorRollup.title') }}</h2>
      <span v-if="!loading && !unavailable" class="text-xs text-autobot-text-muted" data-testid="executor-rollup-total">
        {{ t('llc.executorRollup.totalItems', { count: total }) }}
      </span>
    </div>

    <p v-if="loading" class="py-4 text-center text-xs text-autobot-text-muted" data-testid="executor-rollup-loading">
      {{ t('llc.orgChart.loading') }}
    </p>

    <p
      v-else-if="unavailable"
      class="py-4 text-center text-xs text-autobot-text-muted"
      data-testid="executor-rollup-unavailable"
    >
      {{ t('llc.executorRollup.unavailable') }}
    </p>

    <template v-else>
      <!-- Legend: the three classes, named and counted — unassigned always shown, even at zero. -->
      <div class="flex flex-wrap items-center gap-3" data-testid="executor-rollup-legend">
        <span
          v-for="executorClass in EXECUTOR_CLASSES"
          :key="executorClass"
          class="inline-flex items-center gap-2 text-xs"
          :data-testid="`executor-rollup-legend-${executorClass}`"
        >
          <span class="rounded-full border px-2 py-0.5 font-semibold" :class="CLASS_BADGE_CLASS[executorClass]">
            {{ classLabel(executorClass) }}
          </span>
          <span class="text-autobot-text-muted" :data-testid="`executor-rollup-total-${executorClass}`">
            {{ totals[executorClass] }}
          </span>
        </span>
      </div>

      <p
        v-if="total === 0"
        class="py-4 text-center text-xs text-autobot-text-muted"
        data-testid="executor-rollup-empty"
      >
        {{ t('llc.executorRollup.empty') }}
      </p>

      <!-- Breakdown: one row per status that actually has a count, one column per class. -->
      <table v-else class="w-full text-xs" data-testid="executor-rollup-table">
        <thead>
          <tr class="text-autobot-text-muted">
            <th class="py-1 text-start font-medium">{{ t('llc.executorRollup.statusColumn') }}</th>
            <th
              v-for="executorClass in EXECUTOR_CLASSES"
              :key="executorClass"
              class="py-1 text-end font-medium"
            >
              {{ classLabel(executorClass) }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="status in visibleStatuses"
            :key="status"
            class="border-t border-autobot-border"
            :data-testid="`executor-rollup-row-${status}`"
          >
            <td class="py-1">
              <WorkItemBadge kind="status" :value="status" size="xs" />
            </td>
            <td
              v-for="executorClass in EXECUTOR_CLASSES"
              :key="executorClass"
              class="py-1 text-end text-autobot-text-primary"
              :data-testid="`executor-rollup-cell-${executorClass}-${status}`"
            >
              {{ cellCount(executorClass, status) }}
            </td>
          </tr>
        </tbody>
      </table>
    </template>
  </section>
</template>
