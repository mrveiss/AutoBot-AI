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
        <span class="sprint-status-badge" :class="`status-${sprint.status}`">{{ sprint.status }}</span>
      </div>
      <div class="sprint-stats">
        <div class="stat">
          <span class="stat-label">Goal</span>
          <span class="stat-value sprint-goal">{{ sprint.goal ?? 'No goal set' }}</span>
        </div>
        <div class="stat">
          <span class="stat-label">Committed</span>
          <span class="stat-value">{{ sprint.committed_points ?? 0 }} pts</span>
        </div>
        <div class="stat">
          <span class="stat-label">Completed</span>
          <span class="stat-value">{{ sprint.completed_points ?? 0 }} pts</span>
        </div>
      </div>
    </div>
    <div v-else-if="isLoading" class="sprint-header-skeleton">Loading sprint...</div>

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
            <span class="column-title">{{ col.title }}</span>
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
                <span class="card-type-badge" :class="`type-${item.type}`">{{ item.type }}</span>
              </div>
              <p class="card-title">{{ item.title }}</p>
              <div class="card-footer">
                <span class="priority-dot" :class="`priority-${item.priority}`" :title="item.priority" />
                <span v-if="item.story_points" class="card-points">{{ item.story_points }}</span>
                <span v-if="item.assignee_name" class="card-assignee" :title="item.assignee_name">
                  {{ initials(item.assignee_name) }}
                </span>
              </div>
            </div>
            <div v-if="itemsByColumn(col.id).length === 0" class="column-empty">
              Drop items here
            </div>
          </div>
        </div>
      </div>

      <!-- Burndown sidebar -->
      <div class="burndown-sidebar">
        <h4 class="sidebar-title">Burndown</h4>
        <div v-if="burndown.length > 0" class="burndown-chart">
          <svg :viewBox="`0 0 ${CHART_W} ${CHART_H}`" class="burndown-svg">
            <!-- Ideal line -->
            <line
              :x1="0" :y1="0"
              :x2="CHART_W" :y2="CHART_H"
              stroke="#d1d5db" stroke-width="1" stroke-dasharray="4 4"
            />
            <!-- Actual line -->
            <polyline
              :points="burndownPoints"
              fill="none"
              stroke="#3b82f6"
              stroke-width="2"
              stroke-linejoin="round"
            />
          </svg>
          <div class="burndown-legend">
            <span class="legend-ideal">Ideal</span>
            <span class="legend-actual">Actual</span>
          </div>
        </div>
        <div v-else class="chart-empty">No burndown data</div>
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
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import WorkItemDetail from './WorkItemDetail.vue'

const logger = createLogger('SprintBoardView')
const api = useApiClient()
const route = useRoute()

const companyId = computed(() => route.params.companyId as string)
const boardId = computed(() => route.params.boardId as string)

const CHART_W = 200
const CHART_H = 100

interface WorkItem {
  id: string
  identifier: string
  type: string
  title: string
  priority: string
  story_points: number | null
  assignee_name: string | null
  column_id: string
  status: string
  labels: string[]
  acceptance_criteria: string[]
  description: string
}

interface BoardColumn {
  id: string
  title: string
  status_mapping: string[]
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
let ws: WebSocket | null = null

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
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
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

function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const host = location.hostname
  const port = import.meta.env.VITE_BACKEND_PORT ?? '8001'
  ws = new WebSocket(`${proto}://${host}:${port}/ws/llc/board/${boardId.value}`)

  ws.onmessage = (evt) => {
    try {
      const msg = JSON.parse(evt.data)
      if (msg.type === 'card_moved') {
        const item = items.value.find(i => i.id === msg.work_item_id)
        if (item) item.column_id = msg.column_id
      }
    } catch {
      // ignore malformed frames
    }
  }

  ws.onerror = () => logger.error('Board WS error')
  ws.onclose = () => logger.info('Board WS closed')
}

async function fetchBoard() {
  isLoading.value = true
  try {
    const [boardData, sprintData] = await Promise.all([
      api.get<{ columns: BoardColumn[]; sprint: Sprint; burndown: BurndownPoint[] }>(`/api/llc/boards/${boardId.value}`),
      api.get<{ items: WorkItem[] }>(`/api/llc/boards/${boardId.value}/items`),
    ])
    columns.value = boardData.columns ?? []
    sprint.value = boardData.sprint ?? null
    burndown.value = boardData.burndown ?? []
    items.value = sprintData.items ?? []
  } catch (err) {
    logger.error('Failed to load board', err)
  } finally {
    isLoading.value = false
  }
}

onMounted(async () => {
  await fetchBoard()
  connectWS()
})

onUnmounted(() => {
  ws?.close()
})
</script>

<style scoped>
.sprint-board-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 1.5rem;
  gap: 1rem;
  background: var(--color-background);
  color: var(--color-text);
}

.sprint-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1.5rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--color-border, #e5e7eb);
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
  color: var(--color-text-secondary, #6b7280);
}

.sprint-status-badge {
  padding: 0.125rem 0.5rem;
  border-radius: 9999px;
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: capitalize;
}

.status-planning { background: #fef9c3; color: #713f12; }
.status-active { background: #d1fae5; color: #065f46; }
.status-review { background: #ddd6fe; color: #5b21b6; }
.status-closed { background: #f3f4f6; color: #374151; }

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
  color: var(--color-text-secondary, #9ca3af);
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
  color: var(--color-text-secondary, #9ca3af);
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
  overflow-x: auto;
  align-items: flex-start;
}

.board-column {
  flex: 0 0 260px;
  background: var(--color-surface-elevated, #f9fafb);
  border-radius: 0.5rem;
  border: 1px solid var(--color-border, #e5e7eb);
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 220px);
}

.column-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  font-weight: 600;
  font-size: 0.875rem;
  border-bottom: 1px solid var(--color-border, #e5e7eb);
}

.column-count {
  background: var(--color-surface, #fff);
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: 9999px;
  padding: 0 0.5rem;
  font-size: 0.75rem;
  font-weight: 500;
}

.column-cards {
  flex: 1;
  overflow-y: auto;
  padding: 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.work-card {
  background: var(--color-surface, #fff);
  border: 1px solid var(--color-border, #e5e7eb);
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
  color: var(--color-text-secondary, #9ca3af);
}

.card-type-badge {
  font-size: 0.65rem;
  padding: 0.1rem 0.4rem;
  border-radius: 9999px;
  font-weight: 500;
  text-transform: capitalize;
}

.type-epic { background: #ddd6fe; color: #5b21b6; }
.type-feature { background: #bfdbfe; color: #1d4ed8; }
.type-pbi { background: #d1fae5; color: #065f46; }
.type-task { background: #e0f2fe; color: #0369a1; }
.type-bug { background: #fee2e2; color: #991b1b; }
.type-spike { background: #fef3c7; color: #92400e; }
.type-subtask { background: #f3f4f6; color: #374151; }
.type-risk { background: #fce7f3; color: #9d174d; }

.card-title {
  margin: 0;
  font-size: 0.8rem;
  line-height: 1.4;
  color: var(--color-text);
}

.card-footer {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.125rem;
}

.priority-dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  flex-shrink: 0;
}

.priority-critical { background: #ef4444; }
.priority-high { background: #f97316; }
.priority-medium { background: #eab308; }
.priority-low { background: #22c55e; }

.card-points {
  font-size: 0.7rem;
  font-weight: 600;
  background: var(--color-surface-elevated, #f3f4f6);
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
  background: var(--color-primary, #3b82f6);
  color: white;
  font-size: 0.6rem;
  font-weight: 600;
}

.column-empty {
  text-align: center;
  padding: 1.5rem 0.5rem;
  font-size: 0.75rem;
  color: var(--color-text-secondary, #9ca3af);
  border: 2px dashed var(--color-border, #e5e7eb);
  border-radius: 0.375rem;
}

.burndown-sidebar {
  width: 220px;
  flex-shrink: 0;
  background: var(--color-surface-elevated, #f9fafb);
  border: 1px solid var(--color-border, #e5e7eb);
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

.burndown-legend {
  display: flex;
  gap: 1rem;
  font-size: 0.7rem;
}

.legend-ideal::before {
  content: '- ';
  color: #d1d5db;
}

.legend-actual::before {
  content: '— ';
  color: #3b82f6;
}

.chart-empty {
  font-size: 0.75rem;
  color: var(--color-text-secondary, #9ca3af);
  text-align: center;
  padding: 1rem 0;
}
</style>
