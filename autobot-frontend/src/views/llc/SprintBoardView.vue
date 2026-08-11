<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="sprint-board-view">
    <!-- Sprint Header -->
    <div class="sprint-header" v-if="sprint">
      <div class="sprint-info">
        <h2 class="sprint-title">{{ sprint.name }}</h2>
        <span class="sprint-dates">{{ formatDate(sprint.start_date) }} – {{ formatDate(sprint.end_date) }}</span>
        <span class="sprint-status-badge" :class="`status-${sprint.status}`">{{ sprintStatusLabel(sprint.status) }}</span>
        <button
          class="view-toggle-btn"
          :title="$t('llc.sprint.switchToTimeline')"
          @click="switchToTimeline"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <rect x="2" y="4" width="6" height="2" fill="currentColor" />
            <rect x="2" y="8" width="10" height="2" fill="currentColor" />
            <rect x="2" y="12" width="4" height="2" fill="currentColor" />
          </svg>
          {{ $t('llc.sprint.timelineView') }}
        </button>
      </div>
      <div class="sprint-stats">
        <div class="stat">
          <span class="stat-label">{{ $t('llc.sprint.goal') }}</span>
          <span class="stat-value sprint-goal">{{ sprint.goal ?? $t('llc.sprint.noGoal') }}</span>
        </div>
        <div class="stat">
          <span class="stat-label">{{ $t('llc.sprint.committed') }}</span>
          <span class="stat-value">{{ $t('llc.sprint.points', { count: sprint.committed_points ?? 0 }) }}</span>
        </div>
        <div class="stat">
          <span class="stat-label">{{ $t('llc.sprint.completed') }}</span>
          <span class="stat-value">{{ $t('llc.sprint.points', { count: sprint.completed_points ?? 0 }) }}</span>
        </div>
      </div>
    </div>
    <div v-else-if="isLoading" class="sprint-header-skeleton">{{ $t('llc.sprint.loadingSprint') }}</div>

    <div class="board-layout">
      <!-- Columns -->
      <div class="board-columns">
        <div
          v-for="col in columns"
          :key="col.id"
          class="board-column"
          @dragover.prevent
          @drop="onDrop(col.id)"
        >
          <div class="column-header">
            <span class="column-title">{{ col.name }}</span>
            <span class="column-count">{{ itemsByColumn(col.id).length }}</span>
          </div>
          <div class="column-cards">
            <div
              v-for="item in itemsByColumn(col.id)"
              :key="item.id"
              class="work-card"
              draggable="true"
              @dragstart="onDragStart(item)"
              @click="openDetail(item)"
            >
              <div class="card-header">
                <span class="card-identifier">{{ item.identifier }}</span>
                <WorkItemBadge kind="type" :value="item.type" size="sm" />
              </div>
              <p class="card-title">{{ item.title }}</p>
              <div class="card-footer">
                <WorkItemBadge kind="priority" :value="item.priority" variant="dot" />
                <span v-if="item.story_points" class="card-points">{{ item.story_points }}</span>
                <span v-if="item.assignee_name" class="card-assignee" :title="item.assignee_name">
                  {{ initials(item.assignee_name) }}
                </span>
              </div>
            </div>
            <div v-if="itemsByColumn(col.id).length === 0" class="column-empty">
              {{ $t('llc.sprint.dropHere') }}
            </div>
          </div>
        </div>
      </div>

      <!-- Burndown sidebar -->
      <div class="burndown-sidebar">
        <h4 class="sidebar-title">{{ $t('llc.sprint.burndown') }}</h4>
        <div v-if="burndown.length > 0" class="burndown-chart">
          <svg :viewBox="`0 0 ${CHART_W} ${CHART_H}`" class="burndown-svg">
            <!-- Ideal line -->
            <line
              class="burndown-ideal-line"
              :x1="0" :y1="0"
              :x2="CHART_W" :y2="CHART_H"
              stroke-width="1" stroke-dasharray="4 4"
            />
            <!-- Actual line -->
            <polyline
              class="burndown-actual-line"
              :points="burndownPoints"
              fill="none"
              stroke-width="2"
              stroke-linejoin="round"
            />
          </svg>
          <div class="burndown-legend">
            <span class="legend-ideal">{{ $t('llc.sprint.ideal') }}</span>
            <span class="legend-actual">{{ $t('llc.sprint.actual') }}</span>
          </div>
        </div>
        <div v-else class="chart-empty">{{ $t('llc.sprint.noBurndown') }}</div>
      </div>
    </div>

    <WorkItemDetail
      v-if="detailItem"
      :item="detailItem"
      :company-id="companyId"
      @close="detailItem = null"
      @updated="onItemUpdated"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import { useWorkItemLabels } from '@/composables/useWorkItemLabels'
import WorkItemDetail from './WorkItemDetail.vue'
import WorkItemBadge from '@/components/llc/WorkItemBadge.vue'
import { useLiveEvents } from '@/composables/useLiveEvents'
import { formatDate as fmtDate } from '@/utils/formatHelpers'

const logger = createLogger('SprintBoardView')
const api = useApiClient()
const route = useRoute()
const router = useRouter()
const live = useLiveEvents()
const { sprintStatusLabel } = useWorkItemLabels()

const companyId = computed(() => route.params.companyId as string)
const boardId = computed(() => route.params.boardId as string)

const CHART_W = 200
const CHART_H = 100

import type { WorkItem } from './workItemTypes'

interface BoardColumn {
  id: string
  // GH#13993: the board endpoint (`_board_response` in llc/api/boards.py) emits
  // `name`/`status_filter`, never `title`/`status_mapping`. The old names
  // rendered a blank header on every column.
  name: string
  status_filter: string[]
}

interface Sprint {
  id: string
  name: string
  goal: string | null
  start_date: string
  end_date: string
  status: string
  committed_points: number
  completed_points: number
}

interface BurndownPoint {
  day: number
  remaining: number
}

const columns = ref<BoardColumn[]>([])
const items = ref<WorkItem[]>([])
const sprint = ref<Sprint | null>(null)
const burndown = ref<BurndownPoint[]>([])
const isLoading = ref(false)
const detailItem = ref<WorkItem | null>(null)
const draggedItem = ref<WorkItem | null>(null)

const burndownPoints = computed(() => {
  if (!burndown.value.length) return ''
  const maxDay = burndown.value[burndown.value.length - 1].day
  const maxRem = burndown.value[0].remaining || 1
  return burndown.value
    .map(pt => `${(pt.day / maxDay) * CHART_W},${CHART_H - (pt.remaining / maxRem) * CHART_H}`)
    .join(' ')
})

function itemsByColumn(colId: string) {
  return items.value.filter(i => i.column_id === colId)
}

function initials(name: string) {
  return name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
}

function formatDate(iso: string) {
  return fmtDate(iso, { month: 'short', day: 'numeric' })
}

function switchToTimeline() {
  // #11701: preserve the current board/sprint context so the Gantt scopes to
  // this board's work items instead of jumping to the company-wide roadmap.
  router.push({
    name: 'llc-timeline',
    params: { companyId: companyId.value },
    query: { board: boardId.value },
  })
}

function openDetail(item: WorkItem) {
  detailItem.value = item
}

function onItemUpdated(updated: WorkItem) {
  const idx = items.value.findIndex(i => i.id === updated.id)
  if (idx !== -1) items.value[idx] = updated
}

function onDragStart(item: WorkItem) {
  draggedItem.value = item
}

async function onDrop(colId: string) {
  if (!draggedItem.value || draggedItem.value.column_id === colId) return
  const item = draggedItem.value
  draggedItem.value = null
  const prevCol = item.column_id
  item.column_id = colId
  try {
    await api.post<unknown>(`/api/llc/boards/${boardId.value}/move`, {
      work_item_id: item.id,
      column_id: colId,
    })
  } catch (err) {
    logger.error('Move failed', err)
    item.column_id = prevCol
  }
}

// Live board updates via the canonical /ws/live event bus (channel board:{id}).
// Backend publishes board moves through LiveEventManager (llc/services/board.py).
function subscribeBoard() {
  live.subscribe(`board:${boardId.value}`, (ev) => {
    const wid = ev.payload?.work_item_id as string | undefined
    const col = ev.payload?.column_id as string | undefined
    if (!wid || !col) return
    const item = items.value.find(i => i.id === wid)
    if (item) item.column_id = col
  })
}

async function fetchBoard() {
  isLoading.value = true
  try {
    const [boardData, sprintData] = await Promise.all([
      api.get<{ columns: BoardColumn[]; sprint: Sprint; burndown: BurndownPoint[] }>(`/api/llc/boards/${boardId.value}`),
      // GH#13993: the board-items endpoint nests items inside each column —
      // there is no top-level `items` key. Flatten before storing.
      api.get<{ columns: Array<{ id: string; items: WorkItem[] }> }>(`/api/llc/boards/${boardId.value}/items`),
    ])
    columns.value = boardData.columns ?? []
    sprint.value = boardData.sprint ?? null
    burndown.value = boardData.burndown ?? []
    items.value = (sprintData.columns ?? []).flatMap(col => col.items ?? [])
  } catch (err) {
    logger.error('Failed to load board', err)
  } finally {
    isLoading.value = false
  }
}

onMounted(async () => {
  await fetchBoard()
  subscribeBoard()
})
// useLiveEvents auto-unsubscribes on unmount — no manual teardown needed.
</script>

<style scoped>
.sprint-board-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 1.5rem;
  gap: 1rem;
  background: var(--bg-primary);
  color: var(--text-primary);
}

.sprint-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1.5rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--border-default);
}

.sprint-info {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.sprint-title {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
}

.sprint-dates {
  font-size: 0.875rem;
  color: var(--text-secondary);
}

.sprint-status-badge {
  padding: 0.125rem 0.5rem;
  border-radius: 9999px;
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: capitalize;
}

.view-toggle-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.375rem 0.75rem;
  border: 1px solid var(--border-default);
  background: var(--bg-surface);
  color: var(--text-primary);
  font-size: 0.8125rem;
  font-weight: 500;
  border-radius: 0.375rem;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s, background 0.15s;
}

.view-toggle-btn:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
  background: var(--bg-elevated);
}

.view-toggle-btn:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

/* sprint status palette — theme-adaptive (GH#10868) */
.status-planning { background: var(--badge-sprint-planning-bg); color: var(--badge-sprint-planning-fg); }
.status-active { background: var(--badge-sprint-active-bg); color: var(--badge-sprint-active-fg); }
.status-review { background: var(--badge-sprint-review-bg); color: var(--badge-sprint-review-fg); }
.status-closed { background: var(--badge-sprint-closed-bg); color: var(--badge-sprint-closed-fg); }

.sprint-stats {
  display: flex;
  gap: 1.5rem;
}

.stat {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.125rem;
}

.stat-label {
  font-size: 0.7rem;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.stat-value {
  font-size: 0.9rem;
  font-weight: 600;
}

.sprint-goal {
  max-width: 20rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 400;
  font-size: 0.85rem;
}

.sprint-header-skeleton {
  color: var(--text-secondary);
  font-size: 0.875rem;
}

.board-layout {
  display: flex;
  flex: 1;
  gap: 1rem;
  min-height: 0;
}

.board-columns {
  display: flex;
  gap: 0.75rem;
  flex: 1;
  min-height: 0;
  overflow-x: auto;
  align-items: flex-start;
}

.board-column {
  flex: 0 0 260px;
  background: var(--bg-elevated);
  border-radius: 0.5rem;
  border: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  /* #10750 C2: bounded by .board-columns height, not the viewport (unify w/ Kanban) */
  min-height: 0;
  max-height: 100%;
}

.column-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  font-weight: 600;
  font-size: 0.875rem;
  border-bottom: 1px solid var(--border-default);
}

.column-count {
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: 9999px;
  padding: 0 0.5rem;
  font-size: 0.75rem;
  font-weight: 500;
}

.column-cards {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.work-card {
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
  padding: 0.625rem 0.75rem;
  cursor: grab;
  transition: box-shadow 0.15s;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.work-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.work-card:active {
  cursor: grabbing;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-identifier {
  font-family: monospace;
  font-size: 0.7rem;
  color: var(--text-secondary);
}

.card-title {
  margin: 0;
  font-size: 0.8rem;
  line-height: 1.4;
  color: var(--text-primary);
}

.card-footer {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.125rem;
}

.card-points {
  font-size: 0.7rem;
  font-weight: 600;
  background: var(--bg-elevated);
  padding: 0.1rem 0.4rem;
  border-radius: 0.25rem;
}

.card-assignee {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.5rem;
  height: 1.5rem;
  border-radius: 50%;
  background: var(--color-primary);
  color: white;
  font-size: 0.6rem;
  font-weight: 600;
}

.column-empty {
  text-align: center;
  padding: 1.5rem 0.5rem;
  font-size: 0.75rem;
  color: var(--text-secondary);
  border: 2px dashed var(--border-default);
  border-radius: 0.375rem;
}

.burndown-sidebar {
  width: 220px;
  flex-shrink: 0;
  background: var(--bg-elevated);
  border: 1px solid var(--border-default);
  border-radius: 0.5rem;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.sidebar-title {
  margin: 0;
  font-size: 0.875rem;
  font-weight: 600;
}

.burndown-svg {
  width: 100%;
  height: auto;
}

/* stroke via CSS (not SVG presentation attr) so var() resolves cross-browser incl. Safari */
.burndown-ideal-line {
  stroke: var(--text-secondary);
}

.burndown-actual-line {
  stroke: var(--color-primary);
}

.burndown-legend {
  display: flex;
  gap: 1rem;
  font-size: 0.7rem;
}

.legend-ideal::before {
  content: '- ';
  color: var(--text-secondary);
}

.legend-actual::before {
  content: '— ';
  color: var(--color-primary);
}

.chart-empty {
  font-size: 0.75rem;
  color: var(--text-secondary);
  text-align: center;
  padding: 1rem 0;
}
</style>
