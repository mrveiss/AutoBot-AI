<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  PlannerMapStep (#19938): step 1, the process map. Lanes are who holds the work, steps are what
  happens, and a handoff is a step that crosses lanes. Every edit sends the whole map; the server
  validates it and recomputes the plan's status.
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseButton, BaseInput, EmptyState } from '@autobot/ui'
import { laneName, withLane, withStep, type MapBody, type Plan } from '@/composables/llc/workflowPlanTypes'

const props = defineProps<{ plan: Plan; busy: boolean; warnings: string[] }>()
const emit = defineEmits<{
  map: [body: MapBody]
  waitNote: [handoffKey: string, note: string | null]
}>()
const { t } = useI18n()

const newLane = ref('')
const newStep = ref('')
const stepLane = ref('')
const lanes = computed(() => props.plan.lanes ?? [])
const handoffs = computed(() => props.plan.handoffs ?? [])
const targetLane = computed(() => stepLane.value || lanes.value[0]?.key || '')

function addLane() {
  const name = newLane.value.trim()
  if (!name) return
  emit('map', withLane(props.plan, name))
  newLane.value = ''
}

function addStep() {
  const label = newStep.value.trim()
  if (!label || !targetLane.value) return
  emit('map', withStep(props.plan, label, targetLane.value))
  newStep.value = ''
}

function stepsIn(laneKey: string) {
  return (props.plan.steps ?? []).filter((s) => s.lane_key === laneKey)
}

function noteOf(e: Event): string | null {
  return (e.target as HTMLInputElement).value.trim() || null
}
</script>

<template>
  <section :aria-label="t('llc.workflowPlanner.steps.map')">
    <EmptyState v-if="!lanes.length" :title="t('llc.workflowPlanner.map.empty')" :description="t('llc.workflowPlanner.map.emptyHint')" />
    <div v-for="lane in lanes" :key="lane.key" class="mb-2 flex gap-3 rounded-md border border-autobot-border p-3" :data-testid="`lane-${lane.key}`">
      <span class="w-32 shrink-0 text-sm font-semibold text-autobot-text-primary">{{ lane.name }}</span>
      <ul class="flex flex-wrap gap-2">
        <li v-for="s in stepsIn(lane.key)" :key="s.key" class="rounded-md bg-autobot-bg-card px-2 py-1 text-sm text-autobot-text-secondary">{{ s.label }}</li>
      </ul>
    </div>

    <div v-if="handoffs.length" class="my-3">
      <h4 class="text-sm font-semibold text-autobot-text-primary">{{ t('llc.workflowPlanner.map.handoffs', { count: handoffs.length }) }}</h4>
      <ul>
        <li v-for="h in handoffs" :key="h.key" class="flex flex-wrap items-center gap-2 py-1 text-sm text-autobot-text-secondary">
          <span>{{ laneName(plan, h.from_lane) }} &rarr; {{ laneName(plan, h.to_lane) }}</span>
          <input
            :value="h.wait_note ?? ''"
            class="min-w-48 flex-1 rounded-md border border-autobot-border bg-autobot-bg-card px-2 py-1 text-sm text-autobot-text-primary"
            :aria-label="t('llc.workflowPlanner.map.waitNote')"
            :placeholder="t('llc.workflowPlanner.map.waitNote')"
            :disabled="busy"
            @change="emit('waitNote', h.key, noteOf($event))"
          />
        </li>
      </ul>
    </div>

    <ul v-if="warnings.length" class="my-2 text-sm text-autobot-warning" data-testid="map-warnings">
      <li v-for="w in warnings" :key="w">{{ w }}</li>
    </ul>

    <div class="mt-3 flex flex-wrap items-end gap-3">
      <BaseInput v-model="newLane" size="sm" :label="t('llc.workflowPlanner.map.laneName')" />
      <BaseButton size="sm" variant="secondary" :disabled="busy || !newLane.trim()" data-testid="add-lane" @click="addLane">
        {{ t('llc.workflowPlanner.map.addLane') }}
      </BaseButton>
      <BaseInput v-model="newStep" size="sm" :label="t('llc.workflowPlanner.map.stepLabel')" />
      <select
        v-model="stepLane"
        class="rounded-md border border-autobot-border bg-autobot-bg-card px-2 py-1.5 text-sm text-autobot-text-primary"
        :aria-label="t('llc.workflowPlanner.map.stepLane')"
      >
        <option v-for="l in lanes" :key="l.key" :value="l.key">{{ l.name }}</option>
      </select>
      <BaseButton size="sm" variant="secondary" :disabled="busy || !newStep.trim() || !targetLane" data-testid="add-step" @click="addStep">
        {{ t('llc.workflowPlanner.map.addStep') }}
      </BaseButton>
    </div>
  </section>
</template>
