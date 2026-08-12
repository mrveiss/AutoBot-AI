<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { computed, ref, onMounted, watch } from 'vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import { useI18n } from 'vue-i18n'
import { useLlcCompanyContext } from '@/composables/llc/useLlcCompanyContext'
import OrgTreeNode from './OrgTreeNode.vue'
import type { OrgNode } from './OrgTreeNode.vue'
import HireAgentModal from '@/components/llc/HireAgentModal.vue'
import WorkflowCanvas from '@/components/workflow/WorkflowCanvas.vue'
import type { CanvasNode, CanvasTab } from '@/components/workflow/canvasNode'
import {
  buildOrgCanvasGraph,
  flattenOrgNodes,
  orgLayoutKey,
  orgUnitRoots,
  ORG_GROUP_PREFIX,
} from '@/composables/llc/orgCanvasGraph'

const logger = createLogger('OrgChart')
const api = useApiClient()
const { t, locale } = useI18n()
const { companyId, resolveCompanyId } = useLlcCompanyContext()

const tree = ref<OrgNode[]>([])
const isLoading = ref(false)
const error = ref<string | null>(null)
const selectedNode = ref<OrgNode | null>(null)
const drawerOpen = ref(false)
const showHire = ref(false) // GH#10219
const terminating = ref(false) // in-flight guard — terminate is irreversible

// GH#13939: second render of the same data — the nested tree stays the default.
const ALL_UNITS_TAB = 'all'
type OrgViewMode = 'tree' | 'canvas'
const viewMode = ref<OrgViewMode>('tree')
const activeTabId = ref<string>(ALL_UNITS_TAB)

/**
 * One tab per unit, plus an "all units" tab — and no strip at all when nothing
 * is grouped. GH#13994: this used to be one tab per *root*, which gave a
 * company of twelve people twelve person-named tabs. `orgUnitRoots` is the same
 * predicate the canvas draws its containers from, so the strip and the canvas
 * can never disagree about what a unit is.
 */
const canvasTabs = computed<CanvasTab[]>(() => {
  const units = orgUnitRoots(tree.value)
  if (units.length === 0) return []
  return [
    { id: ALL_UNITS_TAB, label: t('llc.orgChart.canvasTabAll') },
    ...units.map((node) => ({ id: node.id, label: node.name })),
  ]
})

// A selected unit can stop being one between reloads (its last report leaves).
// Falling back to "all units" keeps the canvas populated instead of blank.
const effectiveTabId = computed<string>(() =>
  canvasTabs.value.some((tab) => tab.id === activeTabId.value) ? activeTabId.value : ALL_UNITS_TAB,
)

/** Roots the canvas draws: the whole forest, or the one unit the tab selects. */
const visibleRoots = computed<OrgNode[]>(() =>
  effectiveTabId.value === ALL_UNITS_TAB
    ? tree.value
    : tree.value.filter((node) => node.id === effectiveTabId.value),
)

// A ref (not a computed) so node drags stay put: the canvas reports a drag as
// `node-moved` and `onCanvasNodeMoved` writes the new position here, where it
// must survive until the drawn forest itself changes.
const canvasNodes = ref<CanvasNode[]>([])

/**
 * Explicit, shallow layout source (#13996): ids, nesting and labels — never
 * `status`. `toggleAgentPause` writes `status` on the tree node in place, and
 * the previous `watchEffect` subscribed to it, so pause/resume — the primary
 * canvas-mode action — rebuilt the graph and threw away every dragged position.
 */
const layoutKey = computed(() => `${locale.value}\n${orgLayoutKey(visibleRoots.value)}`)

watch(
  layoutKey,
  () => {
    canvasNodes.value = buildOrgCanvasGraph(visibleRoots.value, (name) =>
      t('llc.orgChart.canvasUnit', { name }),
    )
  },
  { immediate: true },
)

/** Current status per agent id — the one field that changes without a reload. */
const statusById = computed<Record<string, string>>(() => {
  const byId: Record<string, string> = {}
  for (const [id, node] of flattenOrgNodes(tree.value)) byId[id] = node.status
  return byId
})

// #13996: a status change is merged into the nodes already on the canvas
// instead of relaying out, so a drag survives pause/resume.
watch(statusById, (statuses) => {
  for (const node of canvasNodes.value) {
    const status = statuses[node.id]
    if (status !== undefined) (node.data as Record<string, unknown>).status = status
  }
})

function setViewMode(mode: OrgViewMode) {
  viewMode.value = mode
}

/** Canvas selection opens the same drawer the tree opens. */
function onCanvasNodeSelected(nodeId: string | null) {
  if (!nodeId) return closeDrawer()
  const node = flattenOrgNodes(tree.value).get(nodeId)
  if (node) openDrawer(node)
}

async function fetchTree() {
  isLoading.value = true
  error.value = null
  try {
    const cid = await resolveCompanyId()
    if (!cid) {
      tree.value = []
      return
    }
    const resp = await api.get<{ nodes: OrgNode[] }>(`/api/llc/companies/${cid}/org-chart`)
    tree.value = resp?.nodes ?? []
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    logger.error('Failed to fetch org chart:', msg)
    error.value = msg
  } finally {
    isLoading.value = false
  }
}

async function toggleAgentPause(node: OrgNode) {
  if (!companyId.value) return
  const willPause = node.status !== 'paused'
  const cid = companyId.value
  try {
    // Explicit literal paths (not a template action) so each resolves to the
    // canonical /controls/agents/{id}/pause | /resume endpoint.
    if (willPause) {
      await api.post(`/api/llc/companies/${cid}/controls/agents/${node.id}/pause`, {})
    } else {
      await api.post(`/api/llc/companies/${cid}/controls/agents/${node.id}/resume`, {})
    }
    // #13996: mutate the tree node itself — the drawer reads through
    // `selectedNode`, so replacing it with a detached copy left a second
    // toggle updating the copy while the canvas kept the stale status.
    node.status = willPause ? 'paused' : 'idle'
    if (selectedNode.value?.id === node.id) selectedNode.value = node
  } catch (err: unknown) {
    logger.error('Toggle pause failed', err)
  }
}

async function terminateAgent(node: OrgNode) {
  if (!companyId.value || terminating.value) return
  if (!window.confirm(t('llc.orgChart.confirmTerminate', { name: node.name }))) return
  terminating.value = true
  try {
    // Permanent stop — canonical /controls/agents/{id}/terminate endpoint.
    await api.post(`/api/llc/companies/${companyId.value}/controls/agents/${node.id}/terminate`, {})
    await fetchTree() // reload from source of truth (backend sets status=terminated)
    closeDrawer()
  } catch (err: unknown) {
    logger.error('Terminate agent failed', err)
  } finally {
    terminating.value = false
  }
}

function openDrawer(node: OrgNode) {
  selectedNode.value = node
  drawerOpen.value = true
}

function closeDrawer() {
  drawerOpen.value = false
  selectedNode.value = null
}

function formatTime(ts: string | null): string {
  if (!ts) return t('llc.orgChart.never')
  return new Date(ts).toLocaleString()
}

function onCanvasNodeMoved(nodeId: string, position: { x: number; y: number }) {
  // Containers stay anchored to the subtree they enclose.
  if (nodeId.startsWith(ORG_GROUP_PREFIX)) return
  const node = canvasNodes.value.find((candidate) => candidate.id === nodeId)
  if (node) node.position = position
}

onMounted(fetchTree)
</script>

<template>
  <div class="p-4 max-w-7xl mx-auto">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold text-autobot-text-primary">{{ t('llc.orgChart.title') }}</h1>
      <div class="flex items-center gap-3">
        <!-- GH#13939: view-mode toggle — tree stays the default render -->
        <div
          class="inline-flex rounded-md border border-autobot-border overflow-hidden"
          role="group"
          :aria-label="t('llc.orgChart.viewMode')"
        >
          <button
            v-for="mode in (['tree', 'canvas'] as const)"
            :key="mode"
            class="px-3 py-1.5 text-sm transition-colors"
            :class="viewMode === mode
              ? 'bg-autobot-primary text-white'
              : 'bg-autobot-bg-card text-autobot-text-secondary hover:text-autobot-text-primary'"
            :data-testid="`org-view-${mode}`"
            :aria-pressed="viewMode === mode"
            @click="setViewMode(mode)"
          >
            {{ mode === 'tree' ? t('llc.orgChart.viewTree') : t('llc.orgChart.viewCanvas') }}
          </button>
        </div>
        <button
          v-if="companyId"
          class="px-3 py-1.5 rounded-md bg-indigo-600 text-white text-sm hover:bg-indigo-700"
          @click="showHire = true"
        >
          {{ t('llc.orgChart.hireAgent') }}
        </button>
      </div>
    </div>

    <HireAgentModal
      v-if="showHire && companyId"
      :company-id="companyId"
      @close="showHire = false"
      @hired="fetchTree"
    />

    <div v-if="error" class="rounded-lg bg-red-50 border border-red-200 p-4 text-red-700 text-sm mb-4">
      {{ error }}
      <button class="ml-4 underline" @click="fetchTree">{{ t('llc.orgChart.retry') }}</button>
    </div>

    <div v-if="isLoading" class="text-center py-12 text-autobot-text-muted">{{ t('llc.orgChart.loading') }}</div>

    <div v-else-if="tree.length === 0 && !error" class="text-center py-12 text-autobot-text-muted">{{ t('llc.orgChart.empty') }}</div>

    <div v-else-if="viewMode === 'tree'" class="overflow-x-auto">
      <div class="min-w-max flex gap-6 items-start">
        <OrgTreeNode
          v-for="node in tree"
          :key="node.id"
          :node="node"
          :depth="0"
          @select="openDrawer"
        />
      </div>
    </div>

    <!-- GH#13939: same data on the existing workflow canvas — pan/zoom, no graph library -->
    <div v-else class="h-[70vh] rounded-lg border border-autobot-border overflow-hidden" data-testid="org-canvas">
      <WorkflowCanvas
        readonly
        :nodes="canvasNodes"
        :selected-node-id="selectedNode?.id ?? null"
        :tabs="canvasTabs"
        :active-tab-id="effectiveTabId"
        @node-selected="onCanvasNodeSelected"
        @node-moved="onCanvasNodeMoved"
        @tab-selected="activeTabId = $event"
      />
    </div>
    <p v-if="viewMode === 'canvas' && !isLoading && tree.length > 0" class="mt-2 text-xs text-autobot-text-muted">
      {{ t('llc.orgChart.canvasHint') }}
    </p>

    <!-- Agent Detail Drawer -->
    <transition name="slide">
      <div
        v-if="drawerOpen && selectedNode"
        class="fixed inset-y-0 right-0 w-80 bg-autobot-bg-card shadow-2xl border-l border-autobot-border z-50 flex flex-col"
      >
        <div class="flex items-center justify-between px-5 py-4 border-b border-autobot-border">
          <h2 class="text-lg font-semibold text-autobot-text-primary">
            {{ selectedNode.is_human ? t('llc.orgChart.personDetail') : t('llc.orgChart.agentDetail') }}
          </h2>
          <button class="text-autobot-text-muted hover:text-autobot-text-secondary" @click="closeDrawer">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div class="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          <div class="flex items-center gap-3">
            <div
              class="w-12 h-12 rounded-full flex items-center justify-center text-lg font-bold"
              :class="selectedNode.is_human ? 'bg-blue-100 text-blue-700' : 'bg-indigo-100 text-indigo-700'"
            >
              {{ selectedNode.name.charAt(0).toUpperCase() }}
            </div>
            <div>
              <p class="font-semibold text-autobot-text-primary">{{ selectedNode.name }}</p>
              <p class="text-sm text-autobot-text-muted">{{ selectedNode.title }}</p>
            </div>
          </div>

          <dl class="space-y-2 text-sm">
            <!-- "Adapter: lead" is nonsense for a person — the Type row below
                 already says Human, so the adapter row is agent-only. -->
            <div v-if="!selectedNode.is_human" class="flex justify-between">
              <dt class="text-autobot-text-muted">{{ t('llc.orgChart.adapter') }}</dt>
              <dd class="text-autobot-text-primary font-medium">{{ selectedNode.adapter_type }}</dd>
            </div>
            <div v-if="selectedNode.is_human" class="flex justify-between">
              <dt class="text-autobot-text-muted">{{ t('llc.orgChart.role') }}</dt>
              <dd class="text-autobot-text-primary font-medium">{{ selectedNode.title }}</dd>
            </div>
            <div class="flex justify-between">
              <dt class="text-autobot-text-muted">{{ t('llc.orgChart.type') }}</dt>
              <dd class="text-autobot-text-primary">{{ selectedNode.is_human ? t('llc.orgChart.human') : t('llc.orgChart.aiAgent') }}</dd>
            </div>
            <div class="flex justify-between">
              <dt class="text-autobot-text-muted">{{ t('llc.orgChart.lastHeartbeat') }}</dt>
              <dd class="text-autobot-text-primary">{{ formatTime(selectedNode.last_heartbeat) }}</dd>
            </div>
            <div class="flex justify-between">
              <dt class="text-autobot-text-muted">{{ t('llc.orgChart.budget') }}</dt>
              <dd class="text-autobot-text-primary">
                {{ selectedNode.budget_spent }} / {{ selectedNode.budget_total }}
              </dd>
            </div>
            <div class="flex justify-between">
              <dt class="text-autobot-text-muted">{{ t('llc.orgChart.assignedItems') }}</dt>
              <dd class="text-autobot-text-primary">{{ selectedNode.assigned_item_count }}</dd>
            </div>
          </dl>
        </div>
        <!-- Agent lifecycle controls. Gated on !is_human (#13936): people are not
             hired agents — /controls/agents/{id} has no meaning for a membership,
             so the buttons must not be offered for a human node. -->
        <div v-if="selectedNode.is_human" class="px-5 py-4 border-t border-autobot-border text-sm text-autobot-text-muted">
          {{ t('llc.orgChart.humanNoAgentControls') }}
        </div>
        <div v-else-if="selectedNode.status !== 'terminated'" class="px-5 py-4 border-t border-autobot-border space-y-2">
          <button
            class="w-full py-2 rounded-lg text-sm font-medium transition-colors"
            :class="selectedNode.status === 'paused'
              ? 'bg-green-600 text-white hover:bg-green-700'
              : 'bg-amber-500 text-white hover:bg-amber-600'"
            data-testid="org-drawer-pause"
            @click="toggleAgentPause(selectedNode)"
          >
            {{ selectedNode.status === 'paused' ? t('llc.orgChart.resumeAgent') : t('llc.orgChart.pauseAgent') }}
          </button>
          <button
            class="w-full py-2 rounded-lg text-sm font-medium transition-colors bg-red-600 text-white hover:bg-red-700 disabled:opacity-50"
            :disabled="terminating"
            data-testid="org-drawer-terminate"
            @click="terminateAgent(selectedNode)"
          >
            {{ t('llc.orgChart.terminateAgent') }}
          </button>
        </div>
        <div v-else class="px-5 py-4 border-t border-autobot-border text-sm text-autobot-text-muted">
          {{ t('llc.orgChart.terminatedNote') }}
        </div>
      </div>
    </transition>
    <div v-if="drawerOpen" class="fixed inset-0 bg-black/20 z-40" @click="closeDrawer" />
  </div>
</template>

<style scoped>
.slide-enter-active, .slide-leave-active { transition: transform 0.25s ease; }
.slide-enter-from, .slide-leave-to { transform: translateX(100%); }
</style>
