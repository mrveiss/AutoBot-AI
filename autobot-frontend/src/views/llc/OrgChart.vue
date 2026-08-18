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
import { useRouter } from 'vue-router'
import WorkflowCanvas from '@/components/workflow/WorkflowCanvas.vue'
import type { CanvasNode, CanvasTab } from '@/components/workflow/canvasNode'
import {
  buildOrgCanvasGraph,
  buildProcessCanvasNodes,
  canvasBottom,
  flattenOrgNodes,
  orgLayoutKey,
  orgUnitRoots,
  workflowIdFromProcessNode,
  ORG_GROUP_PREFIX,
} from '@/composables/llc/orgCanvasGraph'
import type { ProcessNodeSource } from '@/composables/llc/orgCanvasGraph'
import { WORKFLOW_QUERY_KEY } from '@/composables/workflow/workflowDeepLink'
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
import { availableLensRoles, applyRoleLens, roleLensCounts } from '@/composables/llc/orgRoleLens'

const logger = createLogger('OrgChart')
const api = useApiClient()
const { t, locale } = useI18n()
const router = useRouter()
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
// #13998: ids of contacts this department carries with no role to explain them.
// Kept separate from `contacts` so the list the org chart builds stays one
// list, while the People view can still label the difference honestly.
const unassignedContactIds = ref<Set<string>>(new Set())
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
// #13963: workflows the company's roles run. Kept in its own ref so a failed
// process fetch cannot blank the people graph — an absent source must never
// render as "this company has no org chart".
const processNodes = ref<ProcessNodeSource[]>([])
const processNodesLoaded = ref(false)

/**
 * Explicit, shallow layout source (#13996): ids, nesting and labels — never
 * `status`. `toggleAgentPause` writes `status` on the tree node in place, and
 * the previous `watchEffect` subscribed to it, so pause/resume — the primary
 * canvas-mode action — rebuilt the graph and threw away every dragged position.
 */
const layoutKey = computed(() => `${locale.value}
${orgLayoutKey(visibleRoots.value)}`)

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

// GH#13943: "View As: role" lens — a presentation filter over the canvas
// already on screen. '' means "no lens" (every role shown); a select bound to
// this ref never needs a null/'' branch of its own. The option list is drawn
// from the whole company, not `visibleRoots` — a role can then stay selected
// across a unit-tab change even when the new tab has none of it, so the tab
// switch cannot silently drop the filter out from under the reader; it
// reports zero matches instead (see `roleLens.value && lensCounts...` below).
const roleLens = ref<string>('')
const availableRoles = computed<string[]>(() => availableLensRoles(tree.value))
/**
 * Process nodes, derived rather than stored in `canvasNodes` (#13963).
 *
 * `canvasNodes` holds dragged positions and must only change when the drawn
 * forest changes (#13996). Merging processes into it — or adding them to
 * `layoutKey` — rebuilt the graph when they arrived and threw away every
 * position the user had dragged.
 */
const processCanvasNodes = computed<CanvasNode[]>(() =>
  buildProcessCanvasNodes(processNodes.value, canvasBottom(canvasNodes.value)),
)

const lensedCanvasNodes = computed<CanvasNode[]>(() => [
  ...applyRoleLens(canvasNodes.value, roleLens.value || null),
  // Not lensed: the role lens filters *people* by role, and a process is not a
  // person. Hiding processes when a lens is active would remove them for a
  // reason that does not apply to them.
  ...processCanvasNodes.value,
])
const lensCounts = computed(() => roleLensCounts(canvasNodes.value, roleLens.value || null))

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
    api.get<{ with_role: ContactSource[]; unassigned: ContactSource[] }>(
      `/api/llc/contacts/${cid}/involved`,
    ),
    api.get<{ teams: CompanyTeam[] }>(`/api/llc/companies/${cid}/teams`),
  ])
  if (contactsResult.status === 'fulfilled') {
    // Two groups, one list to draw: people whose presence a role explains, and
    // people the department carries from before the directory was shared.
    // Merging them here would assert an involvement nobody recorded, so the
    // second group is tracked by id and labelled rather than blended in.
    const withRole = Array.isArray(contactsResult.value?.with_role)
      ? contactsResult.value.with_role
      : []
    const unassigned = Array.isArray(contactsResult.value?.unassigned)
      ? contactsResult.value.unassigned
      : []
    contacts.value = [...withRole, ...unassigned]
    unassignedContactIds.value = new Set(unassigned.map((c) => c.id))
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
  // #13963: process nodes only render on the canvas, so they are fetched when
  // the canvas is opened — same principle the People list already encodes. A
  // reader who stays in tree mode should not pay for a request they never see.
  if (mode === 'canvas') void fetchProcessNodes()
}

/** A People-list selection opens the same drawer the tree and canvas open. */
function onPersonSelected(orgNodeId: string) {
  const node = flattenOrgNodes(tree.value).get(orgNodeId)
  if (node) openDrawer(node)
}

/** Canvas selection opens the same drawer the tree opens. */
function onCanvasNodeSelected(nodeId: string | null) {
  if (!nodeId) return closeDrawer()
  // #13963: a process node is the contextual entrance to the absorbed
  // automation module — it opens the workflow it names rather than a drawer.
  const workflowId = workflowIdFromProcessNode(nodeId)
  if (workflowId) {
    void router.push({
      name: 'automation-section',
      params: { companyId: companyId.value, section: 'runner' },
      query: { [WORKFLOW_QUERY_KEY]: workflowId },
    })
    return
  }
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

/**
 * Load the workflows this company's roles run (#13963).
 *
 * Failures are logged and left as an empty list rather than surfaced as a page
 * error: the org chart is still correct without the process nodes, and blocking
 * the whole view on a secondary panel is the #14104 `peopleUnavailable`
 * precedent in reverse.
 */
async function fetchProcessNodes() {
  if (processNodesLoaded.value) return
  try {
    const cid = await resolveCompanyIdOnce()
    if (!cid) {
      processNodes.value = []
      return
    }
    const resp = await api.get<{ nodes: ProcessNodeSource[] }>(
      `/api/llc/companies/${cid}/process-nodes`,
    )
    // Accept only rows that actually carry the three strings a process node is
    // made of. A response of another shape — a misrouted mock, a changed
    // contract — would otherwise be rendered as nonsense nodes on the canvas
    // rather than as nothing.
    const rows = Array.isArray(resp?.nodes) ? resp.nodes : []
    processNodes.value = rows.filter(
      (row): row is ProcessNodeSource =>
        typeof row?.role_id === 'string' &&
        typeof row?.role_name === 'string' &&
        typeof row?.workflow_id === 'string',
    )
    processNodesLoaded.value = true
  } catch (err: unknown) {
    logger.error('Failed to fetch process nodes:', err instanceof Error ? err.message : String(err))
    processNodes.value = []
  }
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

        <!-- GH#13943: "View As: role" lens — a presentation filter of the
             canvas already on screen, never an access boundary (umbrella
             #13935's hard condition). Rendered only in canvas mode, next to
             the view-mode toggle: outside canvas mode there is nothing for it
             to filter, so a dangling non-functional control never appears. -->
        <div
          v-if="viewMode === 'canvas' && availableRoles.length > 0"
          class="flex items-center gap-2 pl-3 border-l border-autobot-border"
          data-testid="role-lens-control"
        >
          <label
            for="org-role-lens"
            class="text-sm text-autobot-text-secondary"
            :title="t('llc.orgChart.roleLensHint')"
          >
            {{ t('llc.orgChart.roleLensLabel') }}
          </label>
          <select
            id="org-role-lens"
            v-model="roleLens"
            class="text-sm rounded-md border border-autobot-border bg-autobot-bg-card px-2 py-1 text-autobot-text-primary"
            data-testid="role-lens-select"
            :aria-label="t('llc.orgChart.roleLensLabel')"
          >
            <option value="">{{ t('llc.orgChart.roleLensAll') }}</option>
            <option v-for="role in availableRoles" :key="role" :value="role">{{ role }}</option>
          </select>
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
        :unassigned-contact-ids="unassignedContactIds"
        :contacts-failed="contactsFailed"
        @select="onPersonSelected"
      />
    </div>

    <!-- GH#13939: same data on the existing workflow canvas — pan/zoom, no graph library -->
    <div
      v-else
      class="h-[70vh] rounded-lg border border-autobot-border overflow-hidden flex flex-col"
      data-testid="org-canvas"
    >
      <!-- GH#13943: the lens's own affordance. Shown whenever a role is
           selected, independent of whether it still matches anything, so a
           reduced (or emptied) canvas reads as "filtered by view", never as
           "no data" (#14064's failure shape) — and its copy states plainly
           that access is unchanged, so it cannot be mistaken for a
           permission boundary. -->
      <div
        v-if="roleLens"
        class="flex items-center justify-between gap-3 border-b border-autobot-border bg-autobot-bg-secondary px-3 py-2 text-sm"
        role="status"
        data-testid="role-lens-banner"
      >
        <span class="text-autobot-text-primary">
          {{ t('llc.orgChart.roleLensBanner', { role: roleLens, shown: lensCounts.shown, total: lensCounts.total }) }}
        </span>
        <button
          class="shrink-0 underline text-autobot-text-secondary hover:text-autobot-text-primary"
          data-testid="role-lens-clear"
          @click="roleLens = ''"
        >
          {{ t('llc.orgChart.roleLensClear') }}
        </button>
      </div>

      <!-- Only when the lens leaves literally nothing — no matching person AND
           no unit container to stand in for one (an ungrouped roster, #13994)
           — is WorkflowCanvas replaced outright: mounting it with an empty
           `nodes` array would fall through to its own empty-state, which
           speaks workflow-authoring vocabulary ("Empty workflow") and reads
           as "no data" rather than "filtered by view". Whenever at least one
           `org-group` container survives, WorkflowCanvas stays mounted and
           renders that (now person-less) box — the emptied box is itself the
           "filtered, not missing" cue, so it is the stronger default. -->
      <div
        v-if="roleLens && lensedCanvasNodes.length === 0"
        class="flex-1 flex items-center justify-center text-center px-6 text-sm text-autobot-text-muted"
        data-testid="role-lens-empty-canvas"
      >
        {{ t('llc.orgChart.roleLensEmpty', { role: roleLens }) }}
      </div>
      <WorkflowCanvas
        v-else
        readonly
        :nodes="lensedCanvasNodes"
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
