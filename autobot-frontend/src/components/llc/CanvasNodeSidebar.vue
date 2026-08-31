<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Author: mrveiss -->
<!--
  GH#13940: the Org Chart node sidebar (tree, canvas and People list all open
  this same drawer via `OrgChart.vue`'s `openDrawer`) gets a fixed slot order
  — owner -> tools -> notes (overview/checklist/output) -> attributes — plus a
  right icon rail (info / checklist / cost / activity / handoff; `comments` is
  omitted, see `orgNodeSidebar.ts`'s module docstring for why).

  Extracted out of `OrgChart.vue` rather than left inline so the fixed order
  is one component, not a template block duplicated the next time a canvas
  node type needs the same sidebar. Not a fork of `WorkItemDetail.vue`: that
  drawer describes one work item; this one describes an org-chart node (an
  agent or a person) and reuses `WorkItemBadge`/`HandoffModal` rather than
  re-declaring them.
-->
<script setup lang="ts">
import { computed, onMounted, ref, useId } from 'vue'
import { useI18n } from 'vue-i18n'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import { formatTimeAgo } from '@/utils/formatHelpers'
import type { components } from '@/types/generated/api'
import type { OrgNode } from '@/views/llc/OrgTreeNode.vue'
import type { WorkItem } from '@/views/llc/workItemTypes'
import WorkItemBadge from './WorkItemBadge.vue'
import HandoffModal from './HandoffModal.vue'
import { useFocusTrap, useFocusRestore, useInitialFocus } from '@autobot/ui'
import {
  SIDEBAR_RAIL_ICONS,
  NOTE_TABS,
  emptySlotState,
  canFetchAssignedItems,
  canHandoffAssignedItems,
  assignedItemsUrl,
  partitionAssignedItems,
  costUrl,
  findAgentCost,
  activityUrl,
  type SidebarRailIcon,
  type NoteTab,
  type SlotState,
  type AgentCostRow,
} from '@/composables/llc/orgNodeSidebar'

type ActivityEntry = components['schemas']['ActivityLogEntry']

const props = defineProps<{
  node: OrgNode
  companyId: string
  terminating: boolean
}>()

const emit = defineEmits<{
  close: []
  pause: [OrgNode]
  terminate: [OrgNode]
}>()

const logger = createLogger('CanvasNodeSidebar')
const api = useApiClient()
const { t } = useI18n()

// #14609: the drawer traps Tab/Shift+Tab, moves focus into itself on open,
// and restores focus to whatever was focused before it mounted — the
// canvas/tree/people-list row that triggered it — on close. Mount-based:
// this component only ever exists while the parent's `v-if` is true.
const panelRef = ref<HTMLElement | null>(null)
const { onKeydown: onFocusTrapKeydown } = useFocusTrap(panelRef)
useFocusRestore()
const { focusFirst } = useInitialFocus(panelRef)
const _uid = useId()
const titleId = `canvas-node-sidebar-title-${_uid}`

const RAIL_ICON_CLASS: Record<SidebarRailIcon, string> = {
  info: 'fa-circle-info',
  checklist: 'fa-list-check',
  cost: 'fa-coins',
  activity: 'fa-clock-rotate-left',
  handoff: 'fa-right-left',
}

const RAIL_LABEL_KEY: Record<SidebarRailIcon, string> = {
  info: 'llc.orgChart.sidebar.railInfo',
  checklist: 'llc.orgChart.sidebar.railChecklist',
  cost: 'llc.orgChart.sidebar.railCost',
  activity: 'llc.orgChart.sidebar.railActivity',
  handoff: 'llc.orgChart.sidebar.railHandoff',
}

const NOTE_TAB_LABEL_KEY: Record<NoteTab, string> = {
  overview: 'llc.orgChart.sidebar.notesOverview',
  checklist: 'llc.orgChart.sidebar.notesChecklist',
  output: 'llc.orgChart.sidebar.notesOutput',
}

const noteTab = ref<NoteTab>('overview')
const activeRail = ref<SidebarRailIcon>('info')

const assignedItems = ref<SlotState<WorkItem>>(emptySlotState())
const costRows = ref<SlotState<AgentCostRow>>(emptySlotState())
const activityEntries = ref<SlotState<ActivityEntry>>(emptySlotState())
const handoffItem = ref<WorkItem | null>(null)

const partitioned = computed(() => partitionAssignedItems(assignedItems.value.items))
const agentCost = computed(() => findAgentCost(costRows.value.items, props.node))

/**
 * Checklist and output both read this one fetch, and so does the handoff
 * panel's item list (#13940's module docstring). Since #14192 this also
 * succeeds for a human node — `canFetchAssignedItems` no longer excludes
 * `is_human` — so only a node missing `node_id` (a structural gap, not a
 * failure) sets `notApplicable` with no request in flight, staying distinct
 * from `unavailable` (#14064/#14104's precedent: absence of data and
 * absence of an answer are different claims).
 */
async function ensureAssignedItems(): Promise<void> {
  if (assignedItems.value.status !== 'idle') return
  if (!canFetchAssignedItems(props.node)) {
    assignedItems.value = { status: 'notApplicable', items: [] }
    return
  }
  assignedItems.value = { status: 'loading', items: [] }
  try {
    const items = await api.get<WorkItem[]>(assignedItemsUrl(props.companyId, props.node))
    assignedItems.value = { status: 'loaded', items: Array.isArray(items) ? items : [] }
  } catch (err) {
    logger.error('Failed to fetch assigned items', err)
    assignedItems.value = { status: 'unavailable', items: [] }
  }
}

async function ensureCost(): Promise<void> {
  if (costRows.value.status !== 'idle') return
  if (props.node.is_human) {
    costRows.value = { status: 'notApplicable', items: [] }
    return
  }
  costRows.value = { status: 'loading', items: [] }
  try {
    const rows = await api.get<AgentCostRow[]>(costUrl(props.companyId))
    costRows.value = { status: 'loaded', items: Array.isArray(rows) ? rows : [] }
  } catch (err) {
    logger.error('Failed to fetch cost data', err)
    costRows.value = { status: 'unavailable', items: [] }
  }
}

async function ensureActivity(): Promise<void> {
  if (activityEntries.value.status !== 'idle') return
  if (props.node.is_human) {
    activityEntries.value = { status: 'notApplicable', items: [] }
    return
  }
  activityEntries.value = { status: 'loading', items: [] }
  try {
    const res = await api.get<{ items: ActivityEntry[] }>(activityUrl(props.companyId, props.node))
    activityEntries.value = { status: 'loaded', items: res?.items ?? [] }
  } catch (err) {
    logger.error('Failed to fetch activity', err)
    activityEntries.value = { status: 'unavailable', items: [] }
  }
}

function selectNoteTab(tab: NoteTab): void {
  noteTab.value = tab
  if (tab !== 'overview') void ensureAssignedItems()
}

function selectRail(icon: SidebarRailIcon): void {
  activeRail.value = icon
  if (icon === 'info') noteTab.value = 'overview'
  else if (icon === 'checklist') {
    noteTab.value = 'checklist'
    void ensureAssignedItems()
  } else if (icon === 'cost') void ensureCost()
  else if (icon === 'activity') void ensureActivity()
  else if (icon === 'handoff') {
    // Never fetch just to show a panel that will report notApplicable — the
    // action itself is agent-only (see `canHandoffAssignedItems`), so a
    // human node's handoff rail must behave like cost/activity: no request.
    if (canHandoffAssignedItems(props.node)) void ensureAssignedItems()
  }
}

function openHandoff(item: WorkItem): void {
  handoffItem.value = item
}

function onHandoffDone(): void {
  handoffItem.value = null
  // The item just moved off this agent — refetch rather than trust a stale list.
  assignedItems.value = emptySlotState()
  void ensureAssignedItems()
}

function formatTime(ts: string | null): string {
  if (!ts) return t('llc.orgChart.never')
  return new Date(ts).toLocaleString()
}

// #14609: fires after this component's own onMounted registration above
// (useFocusRestore's save-focus onMounted), so the origin element is
// captured before focus moves in here.
onMounted(() => {
  void focusFirst()
})
</script>

<template>
  <div
    ref="panelRef"
    class="flex flex-col h-full"
    data-testid="node-sidebar"
    role="dialog"
    aria-modal="true"
    :aria-labelledby="titleId"
    tabindex="-1"
    @keydown="onFocusTrapKeydown"
    @keydown.escape="emit('close')"
  >
    <div class="flex items-center justify-between px-5 py-4 border-b border-autobot-border">
      <h2 :id="titleId" class="text-lg font-semibold text-autobot-text-primary">
        {{ node.is_human ? t('llc.orgChart.personDetail') : t('llc.orgChart.agentDetail') }}
      </h2>
      <button
        class="text-autobot-text-muted hover:text-autobot-text-secondary"
        :aria-label="t('common.close')"
        @click="emit('close')"
      >
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>

    <div class="flex flex-1 min-h-0">
      <!-- Fixed slot order (#13940): owner -> tools -> notes -> attributes. -->
      <div class="flex-1 overflow-y-auto px-5 py-4 space-y-5">
        <section data-testid="sidebar-slot-owner">
          <h3 class="text-xs font-semibold uppercase tracking-wide text-autobot-text-muted mb-2">
            {{ t('llc.orgChart.sidebar.owner') }}
          </h3>
          <div class="flex items-center gap-3">
            <div
              class="w-12 h-12 rounded-full flex items-center justify-center text-lg font-bold"
              :class="node.is_human ? 'bg-blue-100 text-blue-700' : 'bg-indigo-100 text-indigo-700'"
            >
              {{ node.name.charAt(0).toUpperCase() }}
            </div>
            <div>
              <p class="font-semibold text-autobot-text-primary">{{ node.name }}</p>
              <p class="text-sm text-autobot-text-muted">{{ node.title }}</p>
              <p class="text-xs text-autobot-text-muted">
                {{ node.is_human ? t('llc.orgChart.human') : t('llc.orgChart.aiAgent') }}
              </p>
            </div>
          </div>
        </section>

        <section data-testid="sidebar-slot-tools">
          <h3 class="text-xs font-semibold uppercase tracking-wide text-autobot-text-muted mb-2">
            {{ t('llc.orgChart.sidebar.tools') }}
          </h3>
          <p v-if="!node.is_human" class="text-sm text-autobot-text-primary">
            {{ t('llc.orgChart.adapter') }}: <span class="font-medium">{{ node.adapter_type }}</span>
          </p>
          <p v-else class="text-sm text-autobot-text-muted italic">
            {{ t('llc.orgChart.sidebar.toolsNotApplicable') }}
          </p>
        </section>

        <section data-testid="sidebar-slot-notes">
          <h3 class="text-xs font-semibold uppercase tracking-wide text-autobot-text-muted mb-2">
            {{ t('llc.orgChart.sidebar.notes') }}
          </h3>
          <div class="flex gap-1 border-b border-autobot-border mb-3" role="tablist">
            <button
              v-for="tab in NOTE_TABS"
              :key="tab"
              class="px-2 py-1 text-xs font-medium border-b-2 -mb-px"
              :class="noteTab === tab
                ? 'border-autobot-primary text-autobot-primary'
                : 'border-transparent text-autobot-text-muted hover:text-autobot-text-secondary'"
              :data-testid="`sidebar-notes-tab-${tab}`"
              role="tab"
              :aria-selected="noteTab === tab"
              @click="selectNoteTab(tab)"
            >
              {{ t(NOTE_TAB_LABEL_KEY[tab]) }}
            </button>
          </div>

          <div data-testid="sidebar-notes-content">
            <p v-if="noteTab === 'overview'" class="text-sm text-autobot-text-secondary">
              {{ node.title }} · {{ node.is_human ? t('llc.orgChart.human') : t('llc.orgChart.aiAgent') }}
            </p>

            <template v-else-if="noteTab === 'checklist'">
              <p v-if="assignedItems.status === 'notApplicable'" class="text-sm text-autobot-text-muted italic">
                {{ t('llc.orgChart.sidebar.itemsNotApplicable') }}
              </p>
              <p v-else-if="assignedItems.status === 'loading'" class="text-sm text-autobot-text-muted">
                {{ t('llc.orgChart.loading') }}
              </p>
              <p v-else-if="assignedItems.status === 'unavailable'" class="text-sm text-autobot-error" role="alert">
                {{ t('llc.orgChart.sidebar.itemsUnavailable') }}
              </p>
              <p
                v-else-if="assignedItems.status === 'loaded' && partitioned.open.length === 0"
                class="text-sm text-autobot-text-muted"
              >
                {{ t('llc.orgChart.sidebar.itemsEmpty') }}
              </p>
              <ul v-else-if="assignedItems.status === 'loaded'" class="space-y-1.5">
                <li
                  v-for="item in partitioned.open"
                  :key="item.id"
                  class="flex items-center gap-2 text-sm text-autobot-text-primary"
                >
                  <WorkItemBadge kind="status" :value="item.status" size="xs" />
                  <span class="truncate">{{ item.title }}</span>
                </li>
              </ul>
            </template>

            <template v-else>
              <p v-if="assignedItems.status === 'notApplicable'" class="text-sm text-autobot-text-muted italic">
                {{ t('llc.orgChart.sidebar.itemsNotApplicable') }}
              </p>
              <p v-else-if="assignedItems.status === 'loading'" class="text-sm text-autobot-text-muted">
                {{ t('llc.orgChart.loading') }}
              </p>
              <p v-else-if="assignedItems.status === 'unavailable'" class="text-sm text-autobot-error" role="alert">
                {{ t('llc.orgChart.sidebar.itemsUnavailable') }}
              </p>
              <p
                v-else-if="assignedItems.status === 'loaded' && partitioned.done.length === 0"
                class="text-sm text-autobot-text-muted"
              >
                {{ t('llc.orgChart.sidebar.outputEmpty') }}
              </p>
              <ul v-else-if="assignedItems.status === 'loaded'" class="space-y-1.5">
                <li
                  v-for="item in partitioned.done"
                  :key="item.id"
                  class="flex items-center gap-2 text-sm text-autobot-text-primary"
                >
                  <WorkItemBadge kind="status" :value="item.status" size="xs" />
                  <span class="truncate">{{ item.title }}</span>
                </li>
              </ul>
            </template>
          </div>
        </section>

        <section data-testid="sidebar-slot-attributes">
          <h3 class="text-xs font-semibold uppercase tracking-wide text-autobot-text-muted mb-2">
            {{ t('llc.orgChart.sidebar.attributes') }}
          </h3>
          <dl class="space-y-2 text-sm">
            <div class="flex justify-between">
              <dt class="text-autobot-text-muted">{{ t('llc.orgChart.type') }}</dt>
              <dd class="text-autobot-text-primary">
                {{ node.is_human ? t('llc.orgChart.human') : t('llc.orgChart.aiAgent') }}
              </dd>
            </div>
            <!-- #13945 added a labelled Role row for people, and #13940's first
                 draft dropped it while moving the drawer into this component.
                 A person's role is the one attribute that is *theirs* — the
                 other three rows all read "not applicable" for a human, so
                 without this the Attributes slot says nothing about a person at
                 all. `node.title` also appears unlabelled in the Owner header;
                 that is not a substitute for the semantic dt/dd pair. -->
            <div v-if="node.is_human" class="flex justify-between" data-testid="sidebar-attr-role">
              <dt class="text-autobot-text-muted">{{ t('llc.orgChart.role') }}</dt>
              <dd class="text-autobot-text-primary">{{ node.title }}</dd>
            </div>
            <div class="flex justify-between">
              <dt class="text-autobot-text-muted">{{ t('llc.orgChart.lastHeartbeat') }}</dt>
              <dd class="text-autobot-text-primary">
                {{ node.is_human ? t('llc.orgChart.sidebar.toolsNotApplicable') : formatTime(node.last_heartbeat) }}
              </dd>
            </div>
            <div class="flex justify-between">
              <dt class="text-autobot-text-muted">{{ t('llc.orgChart.budget') }}</dt>
              <dd class="text-autobot-text-primary">
                {{ node.is_human
                  ? t('llc.orgChart.sidebar.toolsNotApplicable')
                  : `${node.budget_spent} / ${node.budget_total}` }}
              </dd>
            </div>
            <div class="flex justify-between">
              <dt class="text-autobot-text-muted">{{ t('llc.orgChart.assignedItems') }}</dt>
              <dd class="text-autobot-text-primary">{{ node.assigned_item_count }}</dd>
            </div>
          </dl>
        </section>

        <!-- Cost / activity / handoff panels: additive content the rail exposes
             beyond the four fixed slots (they have no place in owner/tools/
             notes/attributes — see the module docstring). -->
        <section v-if="activeRail === 'cost'" data-testid="sidebar-panel-cost">
          <h3 class="text-xs font-semibold uppercase tracking-wide text-autobot-text-muted mb-2">
            {{ t('llc.orgChart.sidebar.railCost') }}
          </h3>
          <p v-if="costRows.status === 'notApplicable'" class="text-sm text-autobot-text-muted italic">
            {{ t('llc.orgChart.sidebar.costNotApplicableHuman') }}
          </p>
          <p v-else-if="costRows.status === 'loading'" class="text-sm text-autobot-text-muted">
            {{ t('llc.orgChart.loading') }}
          </p>
          <p v-else-if="costRows.status === 'unavailable'" class="text-sm text-autobot-error" role="alert">
            {{ t('llc.orgChart.sidebar.costUnavailable') }}
          </p>
          <p v-else-if="costRows.status === 'loaded' && !agentCost" class="text-sm text-autobot-text-muted">
            {{ t('llc.orgChart.sidebar.costEmpty') }}
          </p>
          <dl v-else-if="agentCost" class="space-y-2 text-sm">
            <div class="flex justify-between">
              <dt class="text-autobot-text-muted">{{ t('llc.orgChart.sidebar.costTotalTokens') }}</dt>
              <dd class="text-autobot-text-primary">{{ agentCost.total_tokens }}</dd>
            </div>
            <div class="flex justify-between">
              <dt class="text-autobot-text-muted">{{ t('llc.orgChart.sidebar.costUsd') }}</dt>
              <dd class="text-autobot-text-primary">{{ agentCost.cost_usd }}</dd>
            </div>
          </dl>
        </section>

        <section v-if="activeRail === 'activity'" data-testid="sidebar-panel-activity">
          <h3 class="text-xs font-semibold uppercase tracking-wide text-autobot-text-muted mb-2">
            {{ t('llc.orgChart.sidebar.railActivity') }}
          </h3>
          <p v-if="activityEntries.status === 'notApplicable'" class="text-sm text-autobot-text-muted italic">
            {{ t('llc.orgChart.sidebar.activityNotApplicableHuman') }}
          </p>
          <p v-else-if="activityEntries.status === 'loading'" class="text-sm text-autobot-text-muted">
            {{ t('llc.orgChart.loading') }}
          </p>
          <p v-else-if="activityEntries.status === 'unavailable'" class="text-sm text-autobot-error" role="alert">
            {{ t('llc.orgChart.sidebar.activityUnavailable') }}
          </p>
          <p
            v-else-if="activityEntries.status === 'loaded' && activityEntries.items.length === 0"
            class="text-sm text-autobot-text-muted"
          >
            {{ t('llc.orgChart.sidebar.activityEmpty') }}
          </p>
          <ul v-else-if="activityEntries.status === 'loaded'" class="space-y-1.5">
            <li v-for="entry in activityEntries.items" :key="entry.id" class="text-sm">
              <span class="text-autobot-text-muted text-xs">{{ formatTimeAgo(entry.occurred_at) }}</span>
              <span class="text-autobot-text-primary ml-2">{{ entry.action }}</span>
            </li>
          </ul>
        </section>

        <section v-if="activeRail === 'handoff'" data-testid="sidebar-panel-handoff">
          <h3 class="text-xs font-semibold uppercase tracking-wide text-autobot-text-muted mb-2">
            {{ t('llc.orgChart.sidebar.railHandoff') }}
          </h3>
          <!-- #14192: gated on the ACTION's own predicate, not just the fetch
               — canFetchAssignedItems is now true for a human node, but the
               handoff verb stays agent-only, so this check must run first and
               independently of `assignedItems.status` (see
               `canHandoffAssignedItems`'s docstring). -->
          <p v-if="!canHandoffAssignedItems(node)" class="text-sm text-autobot-text-muted italic">
            {{ t('llc.orgChart.sidebar.handoffNotApplicableHuman') }}
          </p>
          <p v-else-if="assignedItems.status === 'loading'" class="text-sm text-autobot-text-muted">
            {{ t('llc.orgChart.loading') }}
          </p>
          <p v-else-if="assignedItems.status === 'unavailable'" class="text-sm text-autobot-error" role="alert">
            {{ t('llc.orgChart.sidebar.itemsUnavailable') }}
          </p>
          <p
            v-else-if="assignedItems.status === 'loaded' && partitioned.open.length === 0"
            class="text-sm text-autobot-text-muted"
          >
            {{ t('llc.orgChart.sidebar.handoffEmpty') }}
          </p>
          <ul v-else-if="assignedItems.status === 'loaded'" class="space-y-1.5">
            <li
              v-for="item in partitioned.open"
              :key="item.id"
              class="flex items-center justify-between gap-2 text-sm text-autobot-text-primary"
            >
              <span class="truncate">{{ item.title }}</span>
              <button
                class="text-xs text-autobot-primary hover:underline shrink-0"
                :data-testid="`sidebar-handoff-item-${item.id}`"
                @click="openHandoff(item)"
              >
                {{ t('llc.orgChart.sidebar.handoffButton') }}
              </button>
            </li>
          </ul>
        </section>
      </div>

      <!-- Right icon rail (#13940): fixed order, `comments` intentionally
           absent — see `orgNodeSidebar.ts`'s module docstring. -->
      <nav
        class="flex flex-col items-center gap-1 w-12 border-l border-autobot-border py-3 shrink-0"
        role="tablist"
        :aria-label="t('llc.orgChart.sidebar.railLabel')"
      >
        <button
          v-for="icon in SIDEBAR_RAIL_ICONS"
          :key="icon"
          class="w-9 h-9 rounded-md flex items-center justify-center text-sm transition-colors"
          :class="activeRail === icon
            ? 'bg-autobot-primary text-white'
            : 'text-autobot-text-muted hover:bg-autobot-bg-elevated hover:text-autobot-text-secondary'"
          :data-testid="`sidebar-rail-${icon}`"
          role="tab"
          :aria-pressed="activeRail === icon"
          :title="t(RAIL_LABEL_KEY[icon])"
          @click="selectRail(icon)"
        >
          <i class="fas" :class="RAIL_ICON_CLASS[icon]" aria-hidden="true" />
        </button>
      </nav>
    </div>

    <!-- Agent lifecycle controls — unchanged behavior, moved verbatim out of
         the former inline drawer (#13936/#13996). -->
    <div
      v-if="node.is_human"
      class="px-5 py-4 border-t border-autobot-border text-sm text-autobot-text-muted"
    >
      {{ t('llc.orgChart.humanNoAgentControls') }}
    </div>
    <div v-else-if="node.status !== 'terminated'" class="px-5 py-4 border-t border-autobot-border space-y-2">
      <button
        class="w-full py-2 rounded-lg text-sm font-medium transition-colors"
        :class="node.status === 'paused'
          ? 'bg-green-600 text-white hover:bg-green-700'
          : 'bg-amber-500 text-white hover:bg-amber-600'"
        data-testid="org-drawer-pause"
        @click="emit('pause', node)"
      >
        {{ node.status === 'paused' ? t('llc.orgChart.resumeAgent') : t('llc.orgChart.pauseAgent') }}
      </button>
      <button
        class="w-full py-2 rounded-lg text-sm font-medium transition-colors bg-red-600 text-white hover:bg-red-700 disabled:opacity-50"
        :disabled="terminating"
        data-testid="org-drawer-terminate"
        @click="emit('terminate', node)"
      >
        {{ t('llc.orgChart.terminateAgent') }}
      </button>
    </div>
    <div v-else class="px-5 py-4 border-t border-autobot-border text-sm text-autobot-text-muted">
      {{ t('llc.orgChart.terminatedNote') }}
    </div>

    <HandoffModal
      v-if="handoffItem"
      :work-item-id="handoffItem.id"
      :company-id="companyId"
      direction="to_human"
      :agent-assignee-id="node.node_id"
      @close="handoffItem = null"
      @done="onHandoffDone"
    />
  </div>
</template>
