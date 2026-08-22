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
import { useRoute, useRouter } from 'vue-router'
import WorkflowCanvas from '@/components/workflow/WorkflowCanvas.vue'
import type { CanvasNode, CanvasTab } from '@/components/workflow/canvasNode'
import {
  buildOrgCanvasGraph,
  buildProcessCanvasNodes,
  buildTeamCanvasNodes,
  buildToolCanvasNodes,
  canvasBottom,
  flattenOrgNodes,
  orgLayoutKey,
  orgUnitRoots,
  teamMemberOrgNodeId,
  workflowIdFromProcessNode,
  ORG_GROUP_PREFIX,
} from '@/composables/llc/orgCanvasGraph'
import type { ProcessNodeSource, ToolNodeSource } from '@/composables/llc/orgCanvasGraph'
import { WORKFLOW_QUERY_KEY } from '@/composables/workflow/workflowDeepLink'
import { canvasNodeIdFromQuery } from '@/composables/workflow/canvasNodeDeepLink'
import OrgPeopleList from '@/components/llc/OrgPeopleList.vue'
import CanvasNodeSidebar from '@/components/llc/CanvasNodeSidebar.vue'
import {
  buildOrgPeople,
  countByKind,
  groupPeopleByTeam,
  UNGROUPED_TEAM_ID,
} from '@/composables/llc/orgPeople'
import type { CompanyTeam, ContactSource } from '@/composables/llc/orgPeople'
import ExecutorRollupPanel from '@/components/llc/ExecutorRollupPanel.vue'
import { buildExecutorRollupMatrix } from '@/composables/llc/executorRollup'
import type { ExecutorRollupCell, ExecutorRollupMatrix } from '@/composables/llc/executorRollup'
import { availableLensRoles, roleLensCounts } from '@/composables/llc/orgRoleLens'
import type { CanvasFilterState, CanvasFilterContext } from '@/composables/llc/orgCanvasFilters'
import {
  applyHierarchyFilters,
  applyTeamSectionFilter,
  applyProcessToolFilter,
  applyToolSectionFilter,
  buildTeamIdsByOrgNodeId,
  buildToolRoleIndex,
  teamFilterCounts,
  toolFilterCounts,
} from '@/composables/llc/orgCanvasFilters'
import { describeApiError } from '@/composables/llc/apiErrorMessage'
import BaseButton from '@/components/base/BaseButton.vue'

const logger = createLogger('OrgChart')
const api = useApiClient()
const { t, locale } = useI18n()
const router = useRouter()
// #14611: cast to allow `undefined` — several existing tests mount this view
// with no router plugin installed at all, and `useRoute()` (like `useRouter()`
// above) simply returns `undefined` there rather than throwing; `route?.query`
// below must tolerate that exactly the same way.
const route = useRoute() as ReturnType<typeof useRoute> | undefined
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
// #14596: distinguishes "the teams request has not answered yet" from "it
// answered with zero teams" — `teams.value` is `[]` in both cases, and the
// canvas must never say "this company has no teams" before the request that
// would prove it has actually completed (#14064's failure shape).
const teamsAttempted = ref(false)
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

// #14597: the tools this company's roles carry — the sibling of
// `processNodes` above, same reasoning: its own ref so a failed fetch cannot
// blank anything else, and its own loaded guard so the canvas fetches once
// per visit.
const toolNodes = ref<ToolNodeSource[]>([])
const toolNodesLoaded = ref(false)
/** The tool-nodes request did not answer — distinct from answering "none"
 *  (#14064, #13617, #14556: this exact conflation has been a real defect
 *  three times in this area already). */
const toolNodesFailed = ref(false)
/** Whether the tool-nodes request has been tried at all, so the "no tools"
 *  banner cannot appear before there is anything to report. */
const toolNodesAttempted = ref(false)

// #14549: the canvas can now change the attachment it displays, not just show
// it. `roles` backs the "choose a role" picker for attach; fetched lazily like
// `processNodes`, on the same canvas-open trigger, since neither is needed in
// tree or people mode.
interface AttachableRole {
  id: string
  name: string
}
const attachableRoles = ref<AttachableRole[]>([])
/** The roles request did not answer — distinct from answering "none" (#14064). */
const attachRolesFailed = ref(false)
const rolesLoaded = ref(false)
const attachRoleId = ref('')
const attachWorkflowId = ref('')
// One flag for both mutations, mirroring RolesView.vue's `isMutating`: a
// second attach/detach cannot fire while the first is still in flight.
const processMutationInFlight = ref(false)
const processMutationError = ref<string | null>(null)

// #14597: the tool attach form's own state, mirroring the process attach
// form above exactly (same `attachableRoles` picker, a name field instead of
// a workflow-id field) and its own in-flight/error pair — a tool mutation and
// a process mutation are independent actions and must not block each other.
const attachToolRoleId = ref('')
const attachToolName = ref('')
const toolMutationInFlight = ref(false)
const toolMutationError = ref<string | null>(null)

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

// #14608: team and tool filters — the two axes `orgCanvasFilters.ts` adds
// beside the role lens above. Same '' == "no filter" convention as `roleLens`.
const teamFilter = ref<string>('')
const toolFilter = ref<string>('')

/**
 * Team filter options, drawn from `groupPeopleByTeam` — the exact grouping
 * `buildTeamCanvasNodes` already renders the roster section from — so the
 * picker can never offer a bucket the canvas itself would not draw. Reuses
 * `people.value`/`teams.value` (#13938/#14596), no new fetch.
 */
const availableTeamFilters = computed<{ id: string; name: string }[]>(() =>
  groupPeopleByTeam(people.value, teams.value).map((group) => ({
    id: group.id,
    name: group.id === UNGROUPED_TEAM_ID ? t('llc.orgChart.peopleNoTeam') : group.name,
  })),
)

/** Tool filter options — distinct tool names, alphabetised, mirroring `availableLensRoles`. */
const availableToolFilters = computed<string[]>(() =>
  [...new Set(toolNodes.value.map((row) => row.tool_name))].sort((a, b) => a.localeCompare(b)),
)
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

/** Everyone in the company, of all three kinds, in one list (#13938). */
const people = computed(() => buildOrgPeople(tree.value, contacts.value))

const peopleGroups = computed(() => groupPeopleByTeam(people.value, teams.value))

const peopleCounts = computed(() => countByKind(people.value))

/**
 * Teams, drawn as their own section below the units/ungrouped/process areas
 * (#14596, parent #13938) — a team answers a different question than the
 * reporting hierarchy `canvasNodes` draws, so it gets a visually separate
 * area rather than nesting inside a reporting unit's `org-group`.
 *
 * Derived, like `processCanvasNodes`, rather than stored in `canvasNodes`
 * (#13996): a status change flows straight through because this recomputes
 * from `tree.value` (via `flattenOrgNodes`) on every render, with nothing
 * dragged here to lose.
 */
const teamCanvasNodes = computed<CanvasNode[]>(() =>
  buildTeamCanvasNodes(
    flattenOrgNodes(tree.value),
    people.value,
    teams.value,
    canvasBottom([...canvasNodes.value, ...processCanvasNodes.value]),
    (name) => t('llc.orgChart.canvasTeam', { name }),
    t('llc.orgChart.peopleNoTeam'),
  ),
)

/**
 * Tool nodes, laid out below every other section (#14597) — same derived-not-
 * stored reasoning as `processCanvasNodes`/`teamCanvasNodes`: nothing here is
 * ever dragged, so recomputing on every render loses nothing.
 */
const toolCanvasNodes = computed<CanvasNode[]>(() =>
  buildToolCanvasNodes(
    toolNodes.value,
    processNodes.value,
    canvasBottom([...canvasNodes.value, ...processCanvasNodes.value, ...teamCanvasNodes.value]),
  ),
)

// #14608: the multi-filter's current selection and the lookups its team/tool
// predicates need — see `orgCanvasFilters.ts`'s module docstring for why each
// axis touches the sections it touches.
const canvasFilters = computed<CanvasFilterState>(() => ({
  role: roleLens.value || null,
  team: teamFilter.value || null,
  tool: toolFilter.value || null,
}))
const canvasFilterContext = computed<CanvasFilterContext>(() => {
  const { names, ids } = buildToolRoleIndex(toolNodes.value)
  return {
    teamIdsByOrgNodeId: buildTeamIdsByOrgNodeId(people.value, teams.value),
    toolRoleNames: names,
    toolRoleIds: ids,
  }
})

const lensedCanvasNodes = computed<CanvasNode[]>(() => [
  ...applyHierarchyFilters(canvasNodes.value, canvasFilters.value, canvasFilterContext.value),
  ...applyProcessToolFilter(processCanvasNodes.value, canvasFilters.value.tool, canvasFilterContext.value),
  ...applyTeamSectionFilter(teamCanvasNodes.value, canvasFilters.value.team),
  ...applyToolSectionFilter(toolCanvasNodes.value, canvasFilters.value.tool),
])
const lensCounts = computed(() => roleLensCounts(canvasNodes.value, roleLens.value || null))
const teamLensCounts = computed(() =>
  teamFilterCounts(canvasNodes.value, teamFilter.value || null, canvasFilterContext.value),
)
const toolLensCounts = computed(() =>
  toolFilterCounts(canvasNodes.value, toolFilter.value || null, canvasFilterContext.value),
)
/** The selected team's display name, for the banner copy. */
const teamFilterName = computed(
  () => availableTeamFilters.value.find((team) => team.id === teamFilter.value)?.name ?? teamFilter.value,
)

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
  teamsAttempted.value = true
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
  if (mode === 'canvas') {
    void fetchProcessNodes()
    // #14549: the attach picker needs the role list, same lazy trigger.
    void fetchRolesForAttach()
    // #14596: teams render on the canvas too, sharing the same lazy fetch
    // and the same guard the People list already uses — a second entry into
    // canvas mode does not re-request them.
    void loadPeopleSources()
    // #14597: tools render on the canvas too, same lazy-on-canvas-open trigger.
    void fetchToolNodes()
  }
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
  // #14596: a team roster card carries a composite id (team + real person),
  // never the bare org-chart id, so it opens the same drawer the person's
  // reporting-hierarchy node opens rather than silently doing nothing.
  const realNodeId = teamMemberOrgNodeId(nodeId) ?? nodeId
  const node = flattenOrgNodes(tree.value).get(realNodeId)
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

/**
 * Load the roles this company has, for the canvas attach picker (#14549).
 *
 * A failure is not surfaced as a page error — the org chart is still correct
 * without the picker. But it is recorded in `attachRolesFailed`, because an
 * empty picker and a picker that could not load are different claims: the
 * first says this company has no roles, the second says we do not know. The
 * People tab already refuses to conflate those (#14064), and a silent empty
 * dropdown would tell someone their roles are gone when the request merely
 * failed.
 */
async function fetchRolesForAttach() {
  if (rolesLoaded.value) return
  try {
    const cid = await resolveCompanyIdOnce()
    if (!cid) {
      attachableRoles.value = []
      return
    }
    const resp = await api.get<AttachableRole[]>(`/api/llc/roles/${cid}`)
    attachableRoles.value = Array.isArray(resp)
      ? resp.filter(
          (row): row is AttachableRole =>
            typeof row?.id === 'string' && typeof row?.name === 'string',
        )
      : []
    attachRolesFailed.value = false
    rolesLoaded.value = true
  } catch (err: unknown) {
    logger.error('Failed to fetch roles for the attach picker:', err)
    attachableRoles.value = []
    attachRolesFailed.value = true
  }
}

/**
 * Force the lazy process-node fetch to actually re-run (#14549).
 *
 * `processNodesLoaded` guards `fetchProcessNodes` so the canvas fetches once
 * per visit rather than on every render — a mutation has to clear that guard
 * first, or the "refetch" would hit it and silently keep showing the
 * pre-mutation list while looking like it worked.
 */
async function reloadProcessNodes(): Promise<void> {
  processNodesLoaded.value = false
  await fetchProcessNodes()
}

function describeError(error: unknown, fallbackKey: string): string {
  return describeApiError(error, t(fallbackKey))
}

/** Attach a workflow to a role from the canvas (#14549). */
async function onProcessAttach(): Promise<void> {
  const roleId = attachRoleId.value
  const workflowId = attachWorkflowId.value.trim()
  if (!companyId.value || !roleId || !workflowId || processMutationInFlight.value) return
  processMutationInFlight.value = true
  processMutationError.value = null
  try {
    await api.post(`/api/llc/roles/${companyId.value}/${roleId}/workflows`, {
      workflow_id: workflowId,
    })
    attachWorkflowId.value = ''
    // The canvas is the confirmation (#14549 issue body): a successful attach
    // must be visible on it, not just accepted by the server.
    await reloadProcessNodes()
  } catch (err: unknown) {
    logger.error('Failed to attach workflow:', err)
    processMutationError.value = describeError(err, 'llc.orgChart.attachError')
  } finally {
    processMutationInFlight.value = false
  }
}

/**
 * Detach a workflow from a role, reached from the process node's own control
 * on the canvas (#14549). No optimistic update: a failed call leaves
 * `processNodes` — and so the graph — exactly as it was.
 */
async function onProcessDetached(roleId: string, workflowId: string): Promise<void> {
  if (!companyId.value || processMutationInFlight.value) return
  processMutationInFlight.value = true
  processMutationError.value = null
  try {
    await api.delete(
      `/api/llc/roles/${companyId.value}/${roleId}/workflows/${encodeURIComponent(workflowId)}`,
    )
    await reloadProcessNodes()
  } catch (err: unknown) {
    logger.error('Failed to detach workflow:', err)
    processMutationError.value = describeError(err, 'llc.orgChart.detachError')
  } finally {
    processMutationInFlight.value = false
  }
}

/**
 * Load the tools this company's roles carry (#14597).
 *
 * Mirrors `fetchProcessNodes`, but — unlike that one — distinguishes a failed
 * fetch from an empty answer via `toolNodesFailed`/`toolNodesAttempted`,
 * because this exact conflation ("failed" reading as "this company has
 * none") has been a real defect three times in this area (#14064, #13617,
 * #14556) and the issue that added this surface calls it out by name.
 */
async function fetchToolNodes() {
  if (toolNodesLoaded.value) return
  try {
    const cid = await resolveCompanyIdOnce()
    if (!cid) {
      toolNodes.value = []
      return
    }
    const resp = await api.get<{ nodes: ToolNodeSource[] }>(`/api/llc/companies/${cid}/tool-nodes`)
    // Accept only rows that actually carry the three strings a tool node is
    // made of — same defensive filter `fetchProcessNodes` applies, so a
    // misrouted mock or a changed contract renders as nothing rather than as
    // nonsense nodes on the canvas.
    const rows = Array.isArray(resp?.nodes) ? resp.nodes : []
    toolNodes.value = rows.filter(
      (row): row is ToolNodeSource =>
        typeof row?.role_id === 'string' &&
        typeof row?.role_name === 'string' &&
        typeof row?.tool_name === 'string',
    )
    toolNodesFailed.value = false
    toolNodesLoaded.value = true
  } catch (err: unknown) {
    logger.error('Failed to fetch tool nodes:', err instanceof Error ? err.message : String(err))
    toolNodes.value = []
    toolNodesFailed.value = true
  } finally {
    toolNodesAttempted.value = true
  }
}

/**
 * Force the lazy tool-node fetch to actually re-run (#14597).
 *
 * Mirrors `reloadProcessNodes` — `toolNodesLoaded` guards the lazy fetch, so a
 * mutation has to clear it first or the "refetch" would hit the guard and
 * silently keep showing the pre-mutation list.
 */
async function reloadToolNodes(): Promise<void> {
  toolNodesLoaded.value = false
  await fetchToolNodes()
}

/** Attach a tool to a role from the canvas (#14597). */
async function onToolAttach(): Promise<void> {
  const roleId = attachToolRoleId.value
  const toolName = attachToolName.value.trim()
  if (!companyId.value || !roleId || !toolName || toolMutationInFlight.value) return
  toolMutationInFlight.value = true
  toolMutationError.value = null
  try {
    await api.post(`/api/llc/roles/${companyId.value}/${roleId}/tools`, { tool_name: toolName })
    attachToolName.value = ''
    // The canvas is the confirmation, same as the process attach form: a
    // successful attach must be visible on it, not just accepted by the
    // server (no optimistic update — the reload IS the confirmation).
    await reloadToolNodes()
  } catch (err: unknown) {
    logger.error('Failed to attach tool:', err)
    toolMutationError.value = describeError(err, 'llc.orgChart.toolAttachError')
  } finally {
    toolMutationInFlight.value = false
  }
}

/**
 * Detach a tool from a role, reached from the tool node's own per-role
 * control on the canvas (#14597). No optimistic update: a failed call leaves
 * `toolNodes` — and so the graph — exactly as it was.
 */
async function onToolDetached(roleId: string, toolName: string): Promise<void> {
  if (!companyId.value || toolMutationInFlight.value) return
  toolMutationInFlight.value = true
  toolMutationError.value = null
  try {
    await api.delete(`/api/llc/roles/${companyId.value}/${roleId}/tools/${encodeURIComponent(toolName)}`)
    await reloadToolNodes()
  } catch (err: unknown) {
    logger.error('Failed to detach tool:', err)
    toolMutationError.value = describeError(err, 'llc.orgChart.toolDetachError')
  } finally {
    toolMutationInFlight.value = false
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

/* ------------------------------------------------------------------ *
 * #14611: the inbound deep link — the counterpart to #13963's outbound
 * `?workflow=<id>` link. A `?node=<id>` query names a canvas node to open the
 * canvas already focused on, so a colleague can be sent a link to what the
 * sender is looking at rather than told to pan until they find it.
 * ------------------------------------------------------------------ */

/**
 * Read once via a computed rather than copied into plain state: only its
 * value at mount matters here (`deepLinkHandled` below claims the request
 * exactly once), so a later unrelated query change can never re-trigger a
 * jump the user has since panned away from.
 */
const deepLinkTargetId = computed<string | null>(() => canvasNodeIdFromQuery(route?.query))

/**
 * Every lazy source a deep-linked node could live in has answered (or
 * failed) — the tree itself, processes, tools, teams. Only once all four are
 * settled can "not found" be told apart from "not loaded yet"
 * (#14064/#13617/#14556's repeat conflation, the same reasoning every other
 * "unavailable" banner on this view already follows).
 */
const deepLinkSourcesReady = computed(
  () => !isLoading.value && processNodesLoaded.value && toolNodesLoaded.value && teamsAttempted.value,
)

/** The canvas node `deepLinkTargetId` names among the nodes the canvas is
 *  actually about to draw (`lensedCanvasNodes`) — including a team-roster
 *  alias of a real org-chart member, the same lookup `onCanvasNodeSelected`
 *  already performs for a click. */
const deepLinkResolvedNode = computed<CanvasNode | null>(() => {
  const targetId = deepLinkTargetId.value
  if (!targetId) return null
  return (
    lensedCanvasNodes.value.find(
      (node) => node.id === targetId || teamMemberOrgNodeId(node.id) === targetId,
    ) ?? null
  )
})

/** The id actually handed to `WorkflowCanvas`'s `focus-node-id` prop — only
 *  once resolution has confirmed the node is really drawn, so the canvas is
 *  never asked to jump to something it does not have. */
const canvasFocusNodeId = ref<string | null>(null)
/** A link that names a node this company does not have (removed, or the
 *  reader lacks access) must read as "not found", never as an empty or
 *  unresponsive canvas (#14611 acceptance; #14064/#13617/#14556's repeat
 *  defect). */
const deepLinkNodeNotFound = ref(false)

/** One attempt per link, not a retry loop re-firing on every unrelated
 *  reactive change once the sources are ready (mirrors `WorkflowCanvas.vue`'s
 *  own `focusNodeId` prop watcher, which makes the same one-shot choice for
 *  the same reason: a fixed jump must not fight a pan the user made since). */
let deepLinkHandled = false

watch(deepLinkSourcesReady, (ready) => {
  const targetId = deepLinkTargetId.value
  if (!ready || !targetId || deepLinkHandled) return
  deepLinkHandled = true
  const match = deepLinkResolvedNode.value
  if (!match) {
    deepLinkNodeNotFound.value = true
    return
  }
  canvasFocusNodeId.value = match.id
  // A process/tool node's "focus" is the pan/zoom alone — auto-opening the
  // sidebar, or (for a process node) navigating straight to the workflow
  // builder via `onCanvasNodeSelected`, would hijack a shared link before the
  // reader has looked at anything. A real org-chart member (bare, or a team-
  // roster alias of one) DOES open the same drawer a click on it would: for a
  // person, "focused on it" reasonably includes the detail a click shows.
  const realId = teamMemberOrgNodeId(match.id) ?? match.id
  const orgNode = flattenOrgNodes(tree.value).get(realId)
  if (orgNode) openDrawer(orgNode)
})

onMounted(() => {
  void fetchTree()
  // #13942: company-wide, independent of tree/view-mode — loads once, like fetchTree.
  void loadExecutorRollup()
  // #14611: a deep link opens straight onto the canvas, triggering the same
  // lazy fetches a manual click into it already does (`setViewMode`) — the
  // sources `deepLinkSourcesReady` above waits on would otherwise never load.
  if (deepLinkTargetId.value) setViewMode('canvas')
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

        <!-- #14608: team filter — same view-filter contract as the role lens
             above, combining with it rather than replacing it
             (`orgCanvasFilters.ts`). -->
        <div
          v-if="viewMode === 'canvas' && teams.length > 0"
          class="flex items-center gap-2 pl-3 border-l border-autobot-border"
          data-testid="team-filter-control"
        >
          <label
            for="org-team-filter"
            class="text-sm text-autobot-text-secondary"
            :title="t('llc.orgChart.roleLensHint')"
          >
            {{ t('llc.orgChart.teamFilterLabel') }}
          </label>
          <select
            id="org-team-filter"
            v-model="teamFilter"
            class="text-sm rounded-md border border-autobot-border bg-autobot-bg-card px-2 py-1 text-autobot-text-primary"
            data-testid="team-filter-select"
            :aria-label="t('llc.orgChart.teamFilterLabel')"
          >
            <option value="">{{ t('llc.orgChart.teamFilterAll') }}</option>
            <option v-for="team in availableTeamFilters" :key="team.id" :value="team.id">{{ team.name }}</option>
          </select>
        </div>

        <!-- #14608: tool filter — narrows the hierarchy, the process grid and
             the tool grid together (`orgCanvasFilters.ts`). -->
        <div
          v-if="viewMode === 'canvas' && availableToolFilters.length > 0"
          class="flex items-center gap-2 pl-3 border-l border-autobot-border"
          data-testid="tool-filter-control"
        >
          <label
            for="org-tool-filter"
            class="text-sm text-autobot-text-secondary"
            :title="t('llc.orgChart.roleLensHint')"
          >
            {{ t('llc.orgChart.toolFilterLabel') }}
          </label>
          <select
            id="org-tool-filter"
            v-model="toolFilter"
            class="text-sm rounded-md border border-autobot-border bg-autobot-bg-card px-2 py-1 text-autobot-text-primary"
            data-testid="tool-filter-select"
            :aria-label="t('llc.orgChart.toolFilterLabel')"
          >
            <option value="">{{ t('llc.orgChart.toolFilterAll') }}</option>
            <option v-for="tool in availableToolFilters" :key="tool" :value="tool">{{ tool }}</option>
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

    <div v-if="error" class="rounded-lg bg-autobot-error-bg border border-autobot-error p-4 text-autobot-error text-sm mb-4">
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
      <!-- #14549: the canvas shows the attachment (role, workflow) it draws a
           process node from, but could not change it — attach reaches from
           here, detach reaches from the node itself (below). Always shown in
           canvas mode, independent of the role lens: it is a mutation
           control, not a view filter. -->
      <div
        class="flex flex-wrap items-end gap-3 border-b border-autobot-border bg-autobot-bg-secondary px-3 py-2 text-sm"
        data-testid="process-attach-form"
      >
        <div class="flex flex-col gap-1">
          <label for="process-attach-role" class="text-xs text-autobot-text-secondary">
            {{ t('llc.orgChart.attachRoleLabel') }}
          </label>
          <select
            id="process-attach-role"
            v-model="attachRoleId"
            :disabled="processMutationInFlight"
            class="text-sm rounded-md border border-autobot-border bg-autobot-bg-card px-2 py-1 text-autobot-text-primary"
            data-testid="process-attach-role-select"
          >
            <option value="">{{ t('llc.orgChart.attachRolePlaceholder') }}</option>
            <option v-for="role in attachableRoles" :key="role.id" :value="role.id">
              {{ role.name }}
            </option>
          </select>
          <!-- Stated, not implied: an empty dropdown alone would read as "this
               company has no roles" when the request simply did not answer. -->
          <p
            v-if="attachRolesFailed"
            class="text-xs text-autobot-text-muted"
            data-testid="process-attach-roles-unavailable"
          >
            {{ t('llc.orgChart.attachRolesUnavailable') }}
          </p>
        </div>
        <div class="flex flex-col gap-1">
          <label for="process-attach-workflow" class="text-xs text-autobot-text-secondary">
            {{ t('llc.orgChart.attachWorkflowLabel') }}
          </label>
          <input
            id="process-attach-workflow"
            v-model="attachWorkflowId"
            type="text"
            :disabled="processMutationInFlight"
            :placeholder="t('llc.orgChart.attachWorkflowPlaceholder')"
            class="text-sm rounded-md border border-autobot-border bg-autobot-bg-card px-2 py-1 text-autobot-text-primary"
            data-testid="process-attach-workflow-input"
          />
        </div>
        <BaseButton
          variant="primary"
          data-testid="process-attach-submit"
          :disabled="!attachRoleId || !attachWorkflowId.trim() || processMutationInFlight"
          @click="onProcessAttach"
        >
          {{ t('llc.orgChart.attach') }}
        </BaseButton>
      </div>
      <div
        v-if="processMutationError"
        class="border-b border-autobot-border bg-autobot-error-bg text-autobot-error px-3 py-2 text-sm"
        role="alert"
        data-testid="process-mutation-error"
      >
        {{ processMutationError }}
      </div>

      <!-- #14597: the tool sibling of the process-attach form above — a role
           picker (reusing `attachableRoles`) plus a tool-name field. Attach
           reaches from here; detach reaches from each role chip on the tool
           node itself (WorkflowCanvas.vue). Always shown in canvas mode,
           independent of the role lens, for the same reason the process form
           is: it is a mutation control, not a view filter. -->
      <div
        class="flex flex-wrap items-end gap-3 border-b border-autobot-border bg-autobot-bg-secondary px-3 py-2 text-sm"
        data-testid="tool-attach-form"
      >
        <div class="flex flex-col gap-1">
          <label for="tool-attach-role" class="text-xs text-autobot-text-secondary">
            {{ t('llc.orgChart.attachRoleLabel') }}
          </label>
          <select
            id="tool-attach-role"
            v-model="attachToolRoleId"
            :disabled="toolMutationInFlight"
            class="text-sm rounded-md border border-autobot-border bg-autobot-bg-card px-2 py-1 text-autobot-text-primary"
            data-testid="tool-attach-role-select"
          >
            <option value="">{{ t('llc.orgChart.attachRolePlaceholder') }}</option>
            <option v-for="role in attachableRoles" :key="role.id" :value="role.id">
              {{ role.name }}
            </option>
          </select>
          <p
            v-if="attachRolesFailed"
            class="text-xs text-autobot-text-muted"
            data-testid="tool-attach-roles-unavailable"
          >
            {{ t('llc.orgChart.attachRolesUnavailable') }}
          </p>
        </div>
        <div class="flex flex-col gap-1">
          <label for="tool-attach-name" class="text-xs text-autobot-text-secondary">
            {{ t('llc.orgChart.attachToolNameLabel') }}
          </label>
          <input
            id="tool-attach-name"
            v-model="attachToolName"
            type="text"
            :disabled="toolMutationInFlight"
            :placeholder="t('llc.orgChart.attachToolNamePlaceholder')"
            class="text-sm rounded-md border border-autobot-border bg-autobot-bg-card px-2 py-1 text-autobot-text-primary"
            data-testid="tool-attach-name-input"
          />
        </div>
        <BaseButton
          variant="primary"
          data-testid="tool-attach-submit"
          :disabled="!attachToolRoleId || !attachToolName.trim() || toolMutationInFlight"
          @click="onToolAttach"
        >
          {{ t('llc.orgChart.attach') }}
        </BaseButton>
      </div>
      <div
        v-if="toolMutationError"
        class="border-b border-autobot-border bg-autobot-error-bg text-autobot-error px-3 py-2 text-sm"
        role="alert"
        data-testid="tool-mutation-error"
      >
        {{ toolMutationError }}
      </div>

      <!-- #14597: a failed tool-nodes fetch must read as "could not load",
           never as "this company uses no tools" — the exact conflation
           named in the issue as a repeat defect (#14064, #13617, #14556).
           Shown only once the request has actually answered (or failed), so
           the banner cannot appear before there is anything to report. -->
      <p
        v-if="toolNodesFailed"
        class="border-b border-autobot-border bg-autobot-bg-secondary px-3 py-2 text-xs text-autobot-text-muted"
        data-testid="canvas-tools-unavailable"
      >
        {{ t('llc.orgChart.canvasToolsUnavailable') }}
      </p>
      <p
        v-else-if="toolNodesAttempted && toolNodes.length === 0"
        class="border-b border-autobot-border bg-autobot-bg-secondary px-3 py-2 text-xs text-autobot-text-muted"
        data-testid="canvas-no-tools"
      >
        {{ t('llc.orgChart.canvasNoToolsDefined') }}
      </p>

      <!-- #14596: teams on the canvas carry the same honest-failure distinction
           the People list already makes (#14064, #13617, #14556) — a request
           that failed must never read as "this company has no teams". Shown
           only once the teams request has actually answered (or failed), so
           the banner cannot appear before there is anything to report. -->
      <p
        v-if="teamsFailed"
        class="border-b border-autobot-border bg-autobot-bg-secondary px-3 py-2 text-xs text-autobot-text-muted"
        data-testid="canvas-teams-unavailable"
      >
        {{ t('llc.orgChart.peopleTeamsUnavailable') }}
      </p>
      <p
        v-else-if="teamsAttempted && teams.length === 0"
        class="border-b border-autobot-border bg-autobot-bg-secondary px-3 py-2 text-xs text-autobot-text-muted"
        data-testid="canvas-no-teams"
      >
        {{ t('llc.orgChart.peopleNoTeamsDefined') }}
      </p>

      <!-- #14611: a `?node=` link that names a node this company does not
           have (removed, or the reader lacks access) must say so — never
           read as an unresponsive or empty canvas
           (#14064/#13617/#14556's repeat conflation). -->
      <div
        v-if="deepLinkNodeNotFound"
        class="border-b border-autobot-border bg-autobot-error-bg text-autobot-error px-3 py-2 text-sm"
        role="alert"
        data-testid="canvas-deeplink-not-found"
      >
        {{ t('llc.orgChart.deepLinkNodeNotFound') }}
      </div>

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

      <!-- #14608: the team filter's own affordance, alongside the role
           lens's (both can be visible at once — that IS "several filters
           combine, and the active set is visible" without opening a menu). -->
      <div
        v-if="teamFilter"
        class="flex items-center justify-between gap-3 border-b border-autobot-border bg-autobot-bg-secondary px-3 py-2 text-sm"
        role="status"
        data-testid="team-filter-banner"
      >
        <span class="text-autobot-text-primary">
          {{ t('llc.orgChart.teamFilterBanner', { team: teamFilterName, shown: teamLensCounts.shown, total: teamLensCounts.total }) }}
        </span>
        <button
          class="shrink-0 underline text-autobot-text-secondary hover:text-autobot-text-primary"
          data-testid="team-filter-clear"
          @click="teamFilter = ''"
        >
          {{ t('llc.orgChart.roleLensClear') }}
        </button>
      </div>

      <!-- #14608: the tool filter's own affordance, same pattern. -->
      <div
        v-if="toolFilter"
        class="flex items-center justify-between gap-3 border-b border-autobot-border bg-autobot-bg-secondary px-3 py-2 text-sm"
        role="status"
        data-testid="tool-filter-banner"
      >
        <span class="text-autobot-text-primary">
          {{ t('llc.orgChart.toolFilterBanner', { tool: toolFilter, shown: toolLensCounts.shown, total: toolLensCounts.total }) }}
        </span>
        <button
          class="shrink-0 underline text-autobot-text-secondary hover:text-autobot-text-primary"
          data-testid="tool-filter-clear"
          @click="toolFilter = ''"
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
           "filtered, not missing" cue, so it is the stronger default.

           Unchanged from #13943 — this condition still only names `roleLens`.
           #14608's team and tool axes never need a combined empty-state of
           their own: both are only ever selectable from a value that already
           exists in the fetched data (`availableTeamFilters`/
           `availableToolFilters`), and `applyTeamSectionFilter`/
           `applyToolSectionFilter` always keep that one team's or tool's own
           container node — never removing every last node the way role can.
           So `lensedCanvasNodes.length === 0` is only reachable when team and
           tool are BOTH inactive, at which point this condition is exactly
           the single-role lens's original one (proven, not assumed — see
           `OrgChart.canvasFilters.test.ts`'s team/tool "still shows the …
           box" tests, which pin that landmark for the new axes the same way
           #13943 already pinned it for units). -->
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
        :focus-node-id="canvasFocusNodeId"
        @node-selected="onCanvasNodeSelected"
        @node-moved="onCanvasNodeMoved"
        @tab-selected="activeTabId = $event"
        @process-detached="onProcessDetached"
        @tool-detached="onToolDetached"
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
