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
import PlannerMapEdges from './PlannerMapEdges.vue'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { laneName, buildLane, buildStep, withStep, type Edge, type EdgePatch, type Lane, type LanePatch, type MapBody, type Plan, type Step, type StepPatch } from '@/composables/llc/workflowPlanTypes'

const props = defineProps<{ plan: Plan; busy: boolean; warnings: string[] }>()
const emit = defineEmits<{
  map: [body: MapBody]
  addLane: [body: Lane]
  addStep: [body: Step]
  patchLane: [laneKey: string, body: LanePatch]
  deleteLane: [laneKey: string]
  patchStep: [stepKey: string, body: StepPatch]
  deleteStep: [stepKey: string]
  addEdge: [body: Edge]
  patchEdge: [from: string, to: string, body: EdgePatch]
  deleteEdge: [from: string, to: string]
  waitNote: [handoffKey: string, note: string | null]
}>()
const { t } = useI18n()
const { confirm } = useConfirmDialog()

const newLane = ref('')
const newStep = ref('')
const looseStep = ref('')
const stepLane = ref('')
const lanes = computed(() => props.plan.lanes ?? [])
const handoffs = computed(() => props.plan.handoffs ?? [])
const targetLane = computed(() => stepLane.value || lanes.value[0]?.key || '')

function addLane() {
  const name = newLane.value.trim()
  if (!name) return
  emit('addLane', buildLane(props.plan, name))
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

/** A step on its own: nothing connects it until the owner draws an edge to or from it. */
function addLooseStep() {
  const label = looseStep.value.trim()
  if (!label || !targetLane.value) return
  emit('addStep', buildStep(props.plan, label, targetLane.value))
  looseStep.value = ''
}

/** A rename is sent only when the text really changed and is not blank. */
function renamed(e: Event, current: string): string | null {
  const next = (e.target as HTMLInputElement).value.trim()
  return next && next !== current ? next : null
}

function renameLane(key: string, current: string, e: Event) {
  const name = renamed(e, current)
  if (name) emit('patchLane', key, { name })
}

function renameStep(key: string, current: string, e: Event) {
  const label = renamed(e, current)
  if (label) emit('patchStep', key, { label })
}

async function removeLane(key: string, name: string) {
  const ok = await confirm({ title: t('llc.workflowPlanner.map.deleteLaneTitle'), message: t('llc.workflowPlanner.map.deleteLaneMessage', { name }) })
  if (ok) emit('deleteLane', key)
}

async function removeStep(key: string, label: string) {
  const ok = await confirm({ title: t('llc.workflowPlanner.map.deleteStepTitle'), message: t('llc.workflowPlanner.map.deleteStepMessage', { label }) })
  if (ok) emit('deleteStep', key)
}

function noteOf(e: Event): string | null {
  return (e.target as HTMLInputElement).value.trim() || null
}
</script>

<template>
  <section :aria-label="t('llc.workflowPlanner.steps.map')">
    <EmptyState v-if="!lanes.length" :title="t('llc.workflowPlanner.map.empty')" :description="t('llc.workflowPlanner.map.emptyHint')" />
    <div v-for="lane in lanes" :key="lane.key" class="mb-2 flex gap-3 rounded-md border border-autobot-border p-3" :data-testid="`lane-${lane.key}`">
      <div class="flex w-48 shrink-0 flex-col gap-1">
        <BaseInput
          :model-value="lane.name"
          size="sm"
          :aria-label="t('llc.workflowPlanner.map.renameLane')"
          :disabled="busy"
          :data-testid="`rename-lane-${lane.key}`"
          @change="renameLane(lane.key, lane.name, $event)"
        />
        <BaseButton size="xs" variant="ghost" :disabled="busy" :data-testid="`delete-lane-${lane.key}`" @click="removeLane(lane.key, lane.name)">
          {{ t('llc.workflowPlanner.map.deleteLane') }}
        </BaseButton>
      </div>
      <ul class="flex flex-wrap gap-2">
        <li v-for="s in stepsIn(lane.key)" :key="s.key" class="flex items-center gap-1 rounded-md bg-autobot-bg-card px-2 py-1 text-sm text-autobot-text-secondary">
          <BaseInput
            :model-value="s.label"
            size="sm"
            :aria-label="t('llc.workflowPlanner.map.renameStep')"
            :disabled="busy"
            :data-testid="`rename-step-${s.key}`"
            @change="renameStep(s.key, s.label, $event)"
          />
          <BaseButton size="xs" variant="ghost" :disabled="busy" :data-testid="`delete-step-${s.key}`" @click="removeStep(s.key, s.label)">
            {{ t('llc.workflowPlanner.map.deleteStep') }}
          </BaseButton>
        </li>
      </ul>
    </div>

    <PlannerMapEdges
      :plan="plan"
      :busy="busy"
      @add-edge="(b) => emit('addEdge', b)"
      @patch-edge="(f, to, b) => emit('patchEdge', f, to, b)"
      @delete-edge="(f, to) => emit('deleteEdge', f, to)"
    />

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
      <BaseInput v-model="looseStep" size="sm" :label="t('llc.workflowPlanner.map.looseStepLabel')" />
      <BaseButton size="sm" variant="outline" :disabled="busy || !looseStep.trim() || !targetLane" data-testid="add-loose-step" @click="addLooseStep">
        {{ t('llc.workflowPlanner.map.addLooseStep') }}
      </BaseButton>
    </div>
  </section>
</template>
