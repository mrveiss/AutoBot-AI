<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  PlannerGateList (#19938): the seven gates G1-G7 as the owner sees them before converting. The
  state of each is read from the server's gate report; an open gate lists the exact criteria the
  server says are missing, and a gate that was not evaluated yet says so instead of passing.
  Colour is always paired with a text tag.
-->
<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseBadge } from '@autobot/ui'
import { gateRows, type GateRowState } from '@/composables/llc/workflowPlanGate'
import type { GateResponse, PlanStatus } from '@/composables/llc/workflowPlanTypes'

const props = defineProps<{ status: PlanStatus; gate: GateResponse }>()
const { t } = useI18n()

const rows = computed(() => gateRows(props.status, props.gate))
const VARIANT: Record<GateRowState, 'success' | 'error' | 'neutral'> = { met: 'success', open: 'error', pending: 'neutral' }

function title(id: string): string {
  return `${id} ${t(`llc.workflowPlanner.gate.name.${id}`, t('llc.workflowPlanner.gate.unknown'))}`
}
</script>

<template>
  <ul class="space-y-2" :aria-label="t('llc.workflowPlanner.gate.title')" data-testid="gate-list">
    <li v-for="row in rows" :key="row.id" :data-testid="`gate-${row.id}`" :data-state="row.state">
      <div class="flex flex-wrap items-center gap-2">
        <BaseBadge :variant="VARIANT[row.state]" tone="subtle" size="sm" :label="t(`llc.workflowPlanner.gate.state.${row.state}`)" />
        <span class="text-sm text-autobot-text-primary">{{ title(row.id) }}</span>
      </div>
      <ul v-if="row.messages.length" class="ms-6 list-disc text-sm text-autobot-text-secondary" :data-testid="`gate-${row.id}-missing`">
        <li v-for="m in row.messages" :key="m">{{ m }}</li>
      </ul>
    </li>
  </ul>
</template>
