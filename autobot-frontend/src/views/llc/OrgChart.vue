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
import OrgPeopleList from '@/components/llc/OrgPeopleList.vue'
import CanvasNodeSidebar from '@/components/llc/CanvasNodeSidebar.vue'
import {
  buildOrgPeople,
  countByKind,
  groupPeopleByTeam,
} from '@/composables/llc/orgPeople'
import type { CompanyTeam, ContactSource } from '@/composables/llc/orgPeople'
import ExecutorRollupPanel from '@/components/llc/ExecutorRollupPanel.vue'
import { buildExecutorRollupMatrix } from '@/composables/llc/executorRollup'
import type { ExecutorRollupCell, ExecutorRollupMatrix } from '@/composables/llc/executorRollup'

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
// GH#13938: the People list is a third render of the company — the only one
// that shows contacts, which are not hierarchy members and so appear in
// neither the tree nor the canvas.
type OrgViewMode = 'tree' | 'canvas' | 'people'
const VIEW_MODES: readonly OrgViewMode[] = ['tree', 'canvas', 'people'] as const
const VIEW_MODE_LABEL_KEY: Record<OrgViewMode, string> = {
  tree: 'llc.orgChart.viewTree',
  canvas: 'llc.orgChart.viewCanvas',
  people: 'llc.orgChart.viewPeople',
}
const viewMode = ref<OrgViewMode>('tree')
const activeTabId = ref<string>(ALL_UNITS_TAB)

// GH#13938: contacts and teams are fetched only when the People list is first
// opened. The org chart's own mount stays a single request, and a terminate
// reload keeps reloading exactly the hierarchy it changed.
const contacts = ref<ContactSource[]>([])
const teams = ref<CompanyTeam[]>([])
const peopleLoaded = ref(false)
// A source that did not answer — kept apart from a source that answered
// "nothing", so the list never states a fact it does not know (#14064).
const contactsFailed = ref(false)
const teamsFailed = ref(false)
const peopleLoading = ref(false)

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

/** Everyone in the company, of all three kinds, in one list (#13938). */
const people = computed(() => buildOrgPeople(tree.value, contacts.value))

const peopleGroups = computed(() => groupPeopleByTeam(people.value, teams.value))

const peopleCounts = computed(() => countByKind(people.value))

/**
 * Load the two sources the People list needs beyond the org chart.
 *
 * Each is independent: a company with no contacts must still get its teams,
 * and a teams endpoint failure must not blank the people. `Promise.allSettled`
 * keeps a partial answer partial instead of turning it into an empty list.
 */
async function loadPeopleSources(): Promise<void> {
  if (peopleLoaded.value || peopleLoading.value) return
  // Claim the guard BEFORE the first await: two clicks in one tick would both
  // pass the check above and double-fire every request.
  peopleLoading.value = true
  const cid = await resolveCompanyIdOnce()
  if (!cid) {
    peopleLoading.value = false
    return
  }
  const [contactsResult, teamsResult] = await Promise.allSettled([
    api.get<ContactSource[]>(`/api/llc/contacts/${cid}`),
    api.get<{ teams: CompanyTeam[] }>(`/api/llc/companies/${cid}/teams`),
  ])
  if (contactsResult.status === 'fulfilled') {
    contacts.value = Array.isArray(contactsResult.value) ? contactsResult.value : []
    contactsFailed.value = false
  } else {
    // A failed fetch must never be reported as "this company has no people".
    // Absence of data and absence of an answer are different claims (#14064).
    contactsFailed.value = true
    logger.error('Failed to fetch contacts:', contactsResult.reason)
  }
  if (teamsResult.status === 'fulfilled') {
    teams.value = Array.isArray(teamsResult.value?.teams) ? teamsResult.value.teams : []
    teamsFailed.value = false
  } else {
    teamsFailed.value = true
    logger.error('Failed to fetch company teams:', teamsResult.reason)
  }
  // Only a complete answer is cached; a partial one retries on re-entry.
  peopleLoaded.value = !contactsFailed.value && !teamsFailed.value
  peopleLoading.value = false
}

function setViewMode(mode: OrgViewMode) {
  viewMode.value = mode
  if (mode === 'people') void loadPeopleSources()
}

/** A People-list selection opens the same drawer the tree and canvas open. */
function onPersonSelected(orgNodeId: string) {
  const node = flattenOrgNodes(tree.value).get(orgNodeId)
  if (node) openDrawer(node)
}

/** Canvas selection opens the same drawer the tree opens. */
function onCanvasNodeSelected(nodeId: string | null) {
  if (!nodeId) return closeDrawer()
  const node = flattenOrgNodes(tree.value).get(nodeId)
  if (node) openDrawer(node)
}

/**
 * De-duplicate the in-flight company resolution (#13942 review).
 *
 * `fetchTree` and `loadExecutorRollup` both start with `await resolveCompanyIdOnce()`
 * and `onMounted` fires them together. The composable has no in-flight
 * de-duplication, so on the path it exists for — reached from a top-level nav
 * entry carrying no company id — both raced into their own
 * `GET /api/llc/companies/` fallback, doubling that request on the view most
 * users land on. Harmless but wasteful, and invisible to CI: every test that
 * mounts this view stubs the composable with a static resolver, so the real
 * resolution path is never exercised.
 *
 * Only the *pending* promise is shared; it is released on settle, so a later
 * call still re-resolves.
 */
let pendingCompanyId: Promise<string | null> | null = null
function resolveCompanyIdOnce(): Promise<string | null> {
  if (!pendingCompanyId) {
    pendingCompanyId = Promise.resolve(resolveCompanyId()).finally(() => {
      pendingCompanyId = null
    })
  }
  return pendingCompanyId
}

async function fetchTree() {
  isLoading.value = true
  error.value = null
  try {
    const cid = await resolveCompanyIdOnce()
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

// #13942: the executor rollup panel's own state — independent of `tree`
// (people/agent nodes), since it counts work items, not org-chart nodes.
const executorRollupMatrix = ref<ExecutorRollupMatrix>(buildExecutorRollupMatrix([]))
const executorRollupLoading = ref(false)
// A source that did not answer must never render as "zero work items"
// (#14064's family, #14104's `peopleUnavailable` precedent).
const executorRollupUnavailable = ref(false)

async function loadExecutorRollup(): Promise<void> {
  executorRollupLoading.value = true
  executorRollupUnavailable.value = false
  try {
    const cid = await resolveCompanyIdOnce()
    if (!cid) {
      executorRollupMatrix.value = buildExecutorRollupMatrix([])
      return
    }
    const resp = await api.get<{ cells: ExecutorRollupCell[] }>(
      `/api/llc/companies/${cid}/work-items/executor-rollup`,
    )
    executorRollupMatrix.value = buildExecutorRollupMatrix(resp?.cells ?? [])
  } catch (err: unknown) {
    logger.error('Failed to fetch executor rollup:', err)
    executorRollupUnavailable.value = true
  } finally {
    executorRollupLoading.value = false
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
    // Reload from source of truth: GET /org-chart now honors the persisted
    // "terminated" lifecycle state over a stale heartbeat run (#14108) — the
    // node the refetch returns carries status="terminated", not whatever the
    // latest heartbeat run would otherwise derive.
    await fetchTree()
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

function onCanvasNodeMoved(nodeId: string, position: { x: number; y: number }) {
  // Containers stay anchored to the subtree they enclose.
  if (nodeId.startsWith(ORG_GROUP_PREFIX)) return
  const node = canvasNodes.value.find((candidate) => candidate.id === nodeId)
  if (node) node.position = position
}

onMounted(() => {
  void fetchTree()
  // #13942: company-wide, independent of tree/view-mode — loads once, like fetchTree.
  void loadExecutorRollup()
})
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
            v-for="mode in VIEW_MODES"
            :key="mode"
            class="px-3 py-1.5 text-sm transition-colors"
            :class="viewMode === mode
              ? 'bg-autobot-primary text-white'
              : 'bg-autobot-bg-card text-autobot-text-secondary hover:text-autobot-text-primary'"
            :data-testid="`org-view-${mode}`"
            :aria-pressed="viewMode === mode"
            @click="setViewMode(mode)"
          >
            {{ t(VIEW_MODE_LABEL_KEY[mode]) }}
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

    <!-- #13942: the executor rollup panel — always visible, independent of the
         tree/canvas/people view mode below, since it counts work items rather
         than org-chart nodes. -->
    <div class="mb-4">
      <ExecutorRollupPanel
        :matrix="executorRollupMatrix"
        :loading="executorRollupLoading"
        :unavailable="executorRollupUnavailable"
      />
    </div>

    <div v-if="error" class="rounded-lg bg-red-50 border border-red-200 p-4 text-red-700 text-sm mb-4">
      {{ error }}
      <button class="ml-4 underline" @click="fetchTree">{{ t('llc.orgChart.retry') }}</button>
    </div>

    <div v-if="isLoading" class="text-center py-12 text-autobot-text-muted">{{ t('llc.orgChart.loading') }}</div>

    <!-- GH#13938: the People list carries its own empty state. An empty
         hierarchy does not mean an empty company — a company can have contacts
         and no agent or member at all, and short-circuiting here would report
         "no people" over a list that has some. -->
    <div
      v-else-if="tree.length === 0 && !error && viewMode !== 'people'"
      class="text-center py-12 text-autobot-text-muted"
    >
      {{ t('llc.orgChart.empty') }}
    </div>

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

    <!-- GH#13938: teams and people of all three kinds — the only render that
         shows contacts, which are not hierarchy members. -->
    <div v-else-if="viewMode === 'people'">
      <p v-if="peopleLoading" class="text-center py-6 text-autobot-text-muted">
        {{ t('llc.orgChart.loading') }}
      </p>
      <OrgPeopleList
        :groups="peopleGroups"
        :counts="peopleCounts"
        :has-teams="teams.length > 0"
        :teams-failed="teamsFailed"
        :contacts-failed="contactsFailed"
        @select="onPersonSelected"
      />
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

    <!-- Node sidebar (#13940): fixed slot order + icon rail, extracted to
         CanvasNodeSidebar.vue so it is one component for tree/canvas/People
         selections rather than a template block duplicated per surface. -->
    <transition name="slide">
      <div
        v-if="drawerOpen && selectedNode"
        class="fixed inset-y-0 right-0 w-96 bg-autobot-bg-card shadow-2xl border-l border-autobot-border z-50"
      >
        <CanvasNodeSidebar
          :node="selectedNode"
          :company-id="companyId ?? ''"
          :terminating="terminating"
          @close="closeDrawer"
          @pause="toggleAgentPause"
          @terminate="terminateAgent"
        />
      </div>
    </transition>
    <div v-if="drawerOpen" class="fixed inset-0 bg-black/20 z-40" @click="closeDrawer" />
  </div>
</template>

<style scoped>
.slide-enter-active, .slide-leave-active { transition: transform 0.25s ease; }
.slide-enter-from, .slide-leave-to { transform: translateX(100%); }
</style>
