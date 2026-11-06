<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  PlannerMapEdges (#20086): the flow between steps. A new step is chained after the last one, so a
  branch or a rework loop is drawn here: connect two steps, say when the path is taken, or cut it.
  Each edit is one edge, not the whole map.
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseButton } from '@autobot/ui'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import type { Edge, EdgePatch, Plan } from '@/composables/llc/workflowPlanTypes'

const props = defineProps<{ plan: Plan; busy: boolean }>()
const emit = defineEmits<{
  addEdge: [body: Edge]
  patchEdge: [from: string, to: string, body: EdgePatch]
  deleteEdge: [from: string, to: string]
}>()
const { t } = useI18n()
const { confirm } = useConfirmDialog()

const from = ref('')
const to = ref('')
const steps = computed(() => props.plan.steps ?? [])
const edges = computed(() => props.plan.edges ?? [])

function label(key: string): string {
  return steps.value.find((s) => s.key === key)?.label ?? key
}

function connect() {
  if (!from.value || !to.value || from.value === to.value) return
  emit('addEdge', { from_step: from.value, to_step: to.value })
  from.value = ''
  to.value = ''
}

function setCondition(e: Edge, ev: Event) {
  const next = (ev.target as HTMLInputElement).value.trim()
  if (next !== (e.condition ?? '')) emit('patchEdge', e.from_step, e.to_step, { condition: next || null })
}

async function cut(e: Edge) {
  const ok = await confirm({
    title: t('llc.workflowPlanner.map.deleteEdgeTitle'),
    message: t('llc.workflowPlanner.map.deleteEdgeMessage', { from: label(e.from_step), to: label(e.to_step) }),
  })
  if (ok) emit('deleteEdge', e.from_step, e.to_step)
}
</script>

<template>
  <section v-if="steps.length > 1 || edges.length" class="my-3" :aria-label="t('llc.workflowPlanner.map.edges')">
    <h4 class="text-sm font-semibold text-autobot-text-primary">{{ t('llc.workflowPlanner.map.edges') }}</h4>
    <ul>
      <li v-for="e in edges" :key="`${e.from_step}>${e.to_step}`" class="flex flex-wrap items-center gap-2 py-1 text-sm text-autobot-text-secondary">
        <span>{{ label(e.from_step) }} &rarr; {{ label(e.to_step) }}</span>
        <input
          :value="e.condition ?? ''"
          class="min-w-48 flex-1 rounded-md border border-autobot-border bg-autobot-bg-card px-2 py-1 text-sm text-autobot-text-primary"
          :aria-label="t('llc.workflowPlanner.map.edgeCondition')"
          :placeholder="t('llc.workflowPlanner.map.edgeCondition')"
          :disabled="busy"
          :data-testid="`edge-condition-${e.from_step}-${e.to_step}`"
          @change="setCondition(e, $event)"
        />
        <BaseButton size="xs" variant="ghost" :disabled="busy" :data-testid="`delete-edge-${e.from_step}-${e.to_step}`" @click="cut(e)">
          {{ t('llc.workflowPlanner.map.deleteEdge') }}
        </BaseButton>
      </li>
    </ul>
    <div class="mt-2 flex flex-wrap items-end gap-3">
      <select v-model="from" class="rounded-md border border-autobot-border bg-autobot-bg-card px-2 py-1.5 text-sm text-autobot-text-primary" :aria-label="t('llc.workflowPlanner.map.edgeFrom')" data-testid="edge-from">
        <option value="" disabled>{{ t('llc.workflowPlanner.map.edgeFrom') }}</option>
        <option v-for="s in steps" :key="s.key" :value="s.key">{{ s.label }}</option>
      </select>
      <select v-model="to" class="rounded-md border border-autobot-border bg-autobot-bg-card px-2 py-1.5 text-sm text-autobot-text-primary" :aria-label="t('llc.workflowPlanner.map.edgeTo')" data-testid="edge-to">
        <option value="" disabled>{{ t('llc.workflowPlanner.map.edgeTo') }}</option>
        <option v-for="s in steps" :key="s.key" :value="s.key">{{ s.label }}</option>
      </select>
      <BaseButton size="sm" variant="secondary" :disabled="busy || !from || !to || from === to" data-testid="add-edge" @click="connect">
        {{ t('llc.workflowPlanner.map.addEdge') }}
      </BaseButton>
    </div>
  </section>
</template>
