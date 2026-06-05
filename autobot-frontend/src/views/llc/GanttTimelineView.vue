<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="gantt-timeline-view">
    <!-- Header with zoom controls -->
    <div class="timeline-header" v-if="sprint">
      <div class="header-info">
        <h2 class="sprint-title">{{ sprint.name }} - Timeline</h2>
        <span class="sprint-dates">{{ formatDate(sprint.start_date) }} – {{ formatDate(sprint.end_date) }}</span>
        <button class="view-toggle-btn" @click="switchToBoard" title="Switch to Board View">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <rect x="2" y="2" width="4" height="12" rx="1" stroke="currentColor" stroke-width="1.5" fill="none" />
            <rect x="7" y="2" width="4" height="12" rx="1" stroke="currentColor" stroke-width="1.5" fill="none" />
            <rect x="12" y="2" width="2" height="12" rx="1" stroke="currentColor" stroke-width="1.5" fill="none" />
          </svg>
          Board
        </button>
      </div>
      <div class="header-controls">
        <div class="zoom-controls">
          <button
            v-for="level in zoomLevels"
            :key="level.value"
            :class="['zoom-btn', { active: zoomLevel === level.value }]"
            @click="setZoomLevel(level.value)"
          >
            {{ level.label }}
          </button>
        </div>
        <button class="toggle-btn" @click="showDependencies = !showDependencies">
          <span v-if="showDependencies">Hide</span><span v-else>Show</span> Dependencies
        </button>
        <button class="toggle-btn" @click="showCriticalPath = !showCriticalPath">
          <span v-if="showCriticalPath">Hide</span><span v-else>Show</span> Critical Path
        </button>
      </div>
    </div>

    <!-- Timeline canvas -->
    <div class="timeline-container" ref="containerRef">
      <div class="timeline-grid">
        <!-- Date headers -->
        <div class="date-headers">
          <div class="item-label-column"></div>
          <div class="timeline-dates">
            <div
              v-for="(date, idx) in dateColumns"
              :key="idx"
              :style="{ width: `${columnWidth}px` }"
              class="date-column-header"
            >
              {{ formatDateHeader(date) }}
            </div>
          </div>
        </div>

        <!-- Work item rows -->
        <div class="timeline-rows">
          <div
            v-for="item in sortedItems"
            :key="item.id"
            class="timeline-row"
            @click="openDetail(item)"
          >
            <div class="item-label">
              <span class="item-identifier">{{ item.identifier }}</span>
              <span class="item-title">{{ item.title }}</span>
              <span v-if="item.story_points" class="item-points">{{ item.story_points }}pt</span>
            </div>
            <div class="timeline-track">
              <svg :viewBox="`0 0 ${timelineWidth} ${rowHeight}`" class="timeline-svg">
                <!-- Grid lines -->
                <line
                  v-for="(date, idx) in dateColumns"
                  :key="`grid-${idx}`"
                  :x1="idx * columnWidth"
                  :y1="0"
                  :x2="idx * columnWidth"
                  :y2="rowHeight"
                  class="grid-line"
                />

                <!-- Work item bar -->
                <rect
                  :x="getItemX(item)"
                  :y="6"
                  :width="getItemWidth(item)"
                  :height="rowHeight - 12"
                  :class="['item-bar', `priority-${item.priority}`, { critical: isOnCriticalPath(item.id) && showCriticalPath }]"
                  @click.stop="openDetail(item)"
                />

                <!-- Item label on bar -->
                <text
                  :x="getItemX(item) + 8"
                  :y="rowHeight / 2 + 4"
                  class="bar-label"
                >
                  {{ item.identifier }}
                </text>
              </svg>
            </div>
          </div>
        </div>

        <!-- Dependencies overlay -->
        <svg
          v-if="showDependencies && dependencies.length > 0"
          class="dependencies-overlay"
          :viewBox="`0 0 ${timelineWidth} ${totalHeight}`"
          :style="{ height: `${totalHeight}px` }"
        >
          <defs>
            <marker
              id="arrowhead"
              markerWidth="10"
              markerHeight="10"
              refX="9"
              refY="3"
              orient="auto"
            >
              <polygon points="0 0, 10 3, 0 6" fill="#6b7280" />
            </marker>
          </defs>
          <path
            v-for="(dep, idx) in dependencies"
            :key="`dep-${idx}`"
            :d="getDepPath(dep)"
            class="dependency-arrow"
            marker-end="url(#arrowhead)"
          />
        </svg>
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
import WorkItemDetail from './WorkItemDetail.vue'

const logger = createLogger('GanttTimelineView')
const api = useApiClient()
const route = useRoute()
const router = useRouter()

const companyId = computed(() => route.params.companyId as string)
const boardId = computed(() => route.params.boardId as string)

// Constants
const rowHeight = 40
const columnWidth = 60
const headerHeight = 100

interface WorkItem {
  id: string
  identifier: string
  type: string
  title: string
  priority: string
  story_points: number | null
  assignee_name: string | null
  status: string
  sprint_id: string | null
  // Date fields (to be added to backend)
  planned_start_date?: string
  planned_end_date?: string
  dependencies?: string[] // IDs of items this depends on (blocked_by)
}

interface Sprint {
  id: string
  name: string
  start_date: string
  end_date: string
  status: string
}

interface Dependency {
  from: string
  to: string
}

type ZoomLevel = 'day' | 'week' | 'month' | 'quarter'

// State
const sprint = ref<Sprint | null>(null)
const items = ref<WorkItem[]>([])
const isLoading = ref(false)
const detailItem = ref<WorkItem | null>(null)
const containerRef = ref<HTMLElement | null>(null)

// Timeline controls
const zoomLevel = ref<ZoomLevel>('week')
const showDependencies = ref(true)
const showCriticalPath = ref(false)
const criticalPathIds = ref<Set<string>>(new Set())

const zoomLevels = [
  { value: 'day' as ZoomLevel, label: 'Day' },
  { value: 'week' as ZoomLevel, label: 'Week' },
  { value: 'month' as ZoomLevel, label: 'Month' },
  { value: 'quarter' as ZoomLevel, label: 'Quarter' },
]

// Computed
const dateColumns = computed(() => {
  if (!sprint.value) return []
  const start = new Date(sprint.value.start_date)
  const end = new Date(sprint.value.end_date)
  const columns: Date[] = []

  let current = new Date(start)
  while (current <= end) {
    columns.push(new Date(current))

    // Increment based on zoom level
    switch (zoomLevel.value) {
      case 'day':
        current.setDate(current.getDate() + 1)
        break
      case 'week':
        current.setDate(current.getDate() + 7)
        break
      case 'month':
        current.setMonth(current.getMonth() + 1)
        break
      case 'quarter':
        current.setMonth(current.getMonth() + 3)
        break
    }
  }

  return columns
})

const timelineWidth = computed(() => dateColumns.value.length * columnWidth)
const totalHeight = computed(() => items.value.length * rowHeight + headerHeight)

const sortedItems = computed(() => {
  // Sort by backlog position or dependency order
  return [...items.value].sort((a, b) => {
    // Put items on critical path first if shown
    if (showCriticalPath.value) {
      const aOnPath = isOnCriticalPath(a.id)
      const bOnPath = isOnCriticalPath(b.id)
      if (aOnPath && !bOnPath) return -1
      if (!aOnPath && bOnPath) return 1
    }
    return a.identifier.localeCompare(b.identifier)
  })
})

const dependencies = computed((): Dependency[] => {
  const deps: Dependency[] = []
  items.value.forEach(item => {
    if (item.dependencies) {
      item.dependencies.forEach(depId => {
        deps.push({ from: depId, to: item.id })
      })
    }
  })
  return deps
})

// Methods
function setZoomLevel(level: ZoomLevel) {
  zoomLevel.value = level
}

function switchToBoard() {
  router.push({
    name: 'llc-sprint-board',
    params: {
      companyId: companyId.value,
      boardId: boardId.value,
    },
  })
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function formatDateHeader(date: Date) {
  switch (zoomLevel.value) {
    case 'day':
      return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
    case 'week':
      return `W${getWeekNumber(date)}`
    case 'month':
      return date.toLocaleDateString(undefined, { month: 'short' })
    case 'quarter':
      return `Q${Math.floor(date.getMonth() / 3) + 1} ${date.getFullYear()}`
  }
}

function getWeekNumber(date: Date): number {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()))
  const dayNum = d.getUTCDay() || 7
  d.setUTCDate(d.getUTCDate() + 4 - dayNum)
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1))
  return Math.ceil((((d.getTime() - yearStart.getTime()) / 86400000) + 1) / 7)
}

function getItemX(item: WorkItem): number {
  if (!sprint.value) return 0

  // Use planned_start_date if available, otherwise use sprint start
  const itemStart = item.planned_start_date
    ? new Date(item.planned_start_date)
    : new Date(sprint.value.start_date)
  const sprintStart = new Date(sprint.value.start_date)

  const daysDiff = Math.floor((itemStart.getTime() - sprintStart.getTime()) / (1000 * 60 * 60 * 24))

  // Calculate column index based on zoom level
  let columnIndex = 0
  switch (zoomLevel.value) {
    case 'day':
      columnIndex = daysDiff
      break
    case 'week':
      columnIndex = Math.floor(daysDiff / 7)
      break
    case 'month':
      columnIndex = Math.floor(daysDiff / 30)
      break
    case 'quarter':
      columnIndex = Math.floor(daysDiff / 90)
      break
  }

  return Math.max(0, columnIndex * columnWidth)
}

function getItemWidth(item: WorkItem): number {
  if (!sprint.value) return columnWidth

  // Use planned dates if available
  if (item.planned_start_date && item.planned_end_date) {
    const start = new Date(item.planned_start_date)
    const end = new Date(item.planned_end_date)
    const days = Math.floor((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24))

    switch (zoomLevel.value) {
      case 'day':
        return Math.max(columnWidth, days * columnWidth)
      case 'week':
        return Math.max(columnWidth, Math.ceil(days / 7) * columnWidth)
      case 'month':
        return Math.max(columnWidth, Math.ceil(days / 30) * columnWidth)
      case 'quarter':
        return Math.max(columnWidth, Math.ceil(days / 90) * columnWidth)
    }
  }

  // Default: use story points to estimate width
  const estimatedDays = (item.story_points || 1) * 2 // 2 days per story point
  switch (zoomLevel.value) {
    case 'day':
      return Math.max(columnWidth, estimatedDays * columnWidth)
    case 'week':
      return Math.max(columnWidth, Math.ceil(estimatedDays / 7) * columnWidth)
    case 'month':
      return Math.max(columnWidth, Math.ceil(estimatedDays / 30) * columnWidth)
    case 'quarter':
      return Math.max(columnWidth, Math.ceil(estimatedDays / 90) * columnWidth)
  }

  return columnWidth
}

function getDepPath(dep: Dependency): string {
  const fromIdx = items.value.findIndex(i => i.id === dep.from)
  const toIdx = items.value.findIndex(i => i.id === dep.to)

  if (fromIdx === -1 || toIdx === -1) return ''

  const fromItem = items.value[fromIdx]
  const toItem = items.value[toIdx]

  const x1 = getItemX(fromItem) + getItemWidth(fromItem)
  const y1 = (fromIdx * rowHeight) + (rowHeight / 2) + headerHeight
  const x2 = getItemX(toItem)
  const y2 = (toIdx * rowHeight) + (rowHeight / 2) + headerHeight

  // Create a curved arrow path
  const midX = (x1 + x2) / 2
  return `M ${x1} ${y1} Q ${midX} ${y1}, ${midX} ${(y1 + y2) / 2} T ${x2} ${y2}`
}

function isOnCriticalPath(itemId: string): boolean {
  return criticalPathIds.value.has(itemId)
}

function calculateCriticalPath() {
  // Simple critical path: longest dependency chain
  // TODO: Implement proper critical path algorithm
  const visited = new Set<string>()
  const pathLengths = new Map<string, number>()

  function getPathLength(itemId: string): number {
    if (visited.has(itemId)) return pathLengths.get(itemId) || 0
    visited.add(itemId)

    const item = items.value.find(i => i.id === itemId)
    if (!item || !item.dependencies || item.dependencies.length === 0) {
      pathLengths.set(itemId, item?.story_points || 1)
      return item?.story_points || 1
    }

    const maxDepLength = Math.max(...item.dependencies.map(depId => getPathLength(depId)))
    const length = maxDepLength + (item.story_points || 1)
    pathLengths.set(itemId, length)
    return length
  }

  // Calculate path lengths for all items
  items.value.forEach(item => getPathLength(item.id))

  // Find maximum path length
  const maxLength = Math.max(...Array.from(pathLengths.values()))

  // Mark items on critical path
  const critical = new Set<string>()
  items.value.forEach(item => {
    if (pathLengths.get(item.id) === maxLength) {
      critical.add(item.id)
      // Add all dependencies in the chain
      function addDeps(id: string) {
        const i = items.value.find(x => x.id === id)
        if (i?.dependencies) {
          i.dependencies.forEach(depId => {
            critical.add(depId)
            addDeps(depId)
          })
        }
      }
      addDeps(item.id)
    }
  })

  criticalPathIds.value = critical
}

function openDetail(item: WorkItem) {
  detailItem.value = item
}

function onItemUpdated(updated: WorkItem) {
  const idx = items.value.findIndex(i => i.id === updated.id)
  if (idx !== -1) items.value[idx] = updated
}

async function fetchData() {
  isLoading.value = true
  try {
    const [boardData, itemsData] = await Promise.all([
      api.get<{ sprint: Sprint }>(`/api/llc/boards/${boardId.value}`),
      api.get<{ items: WorkItem[] }>(`/api/llc/boards/${boardId.value}/items`),
    ])

    sprint.value = boardData.sprint ?? null
    items.value = itemsData.items ?? []

    calculateCriticalPath()
  } catch (err) {
    logger.error('Failed to load timeline data', err)
  } finally {
    isLoading.value = false
  }
}

onMounted(async () => {
  await fetchData()
})
</script>

<style scoped>
.gantt-timeline-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--color-background);
  color: var(--color-text);
}

.timeline-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--color-border, #e5e7eb);
  background: var(--color-surface-elevated, #f9fafb);
}

.header-info {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
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

.view-toggle-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.375rem 0.75rem;
  border: 1px solid var(--color-border, #e5e7eb);
  background: var(--color-surface, #fff);
  color: var(--color-text);
  font-size: 0.8125rem;
  font-weight: 500;
  border-radius: 0.375rem;
  cursor: pointer;
  transition: all 0.15s;
}

.view-toggle-btn:hover {
  border-color: var(--color-primary, #3b82f6);
  background: var(--color-primary-light, #eff6ff);
}

.view-toggle-btn svg {
  flex-shrink: 0;
}

.header-controls {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.zoom-controls {
  display: flex;
  gap: 0.25rem;
  background: var(--color-surface, #fff);
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: 0.375rem;
  padding: 0.125rem;
}

.zoom-btn {
  padding: 0.375rem 0.75rem;
  border: none;
  background: transparent;
  color: var(--color-text-secondary, #6b7280);
  font-size: 0.8125rem;
  font-weight: 500;
  border-radius: 0.25rem;
  cursor: pointer;
  transition: all 0.15s;
}

.zoom-btn:hover {
  background: var(--color-surface-elevated, #f3f4f6);
}

.zoom-btn.active {
  background: var(--color-primary, #3b82f6);
  color: white;
}

.toggle-btn {
  padding: 0.375rem 0.75rem;
  border: 1px solid var(--color-border, #e5e7eb);
  background: var(--color-surface, #fff);
  color: var(--color-text);
  font-size: 0.8125rem;
  font-weight: 500;
  border-radius: 0.375rem;
  cursor: pointer;
  transition: all 0.15s;
}

.toggle-btn:hover {
  border-color: var(--color-primary, #3b82f6);
  background: var(--color-primary-light, #eff6ff);
}

.timeline-container {
  flex: 1;
  overflow: auto;
  padding: 1rem;
}

.timeline-grid {
  position: relative;
  min-width: fit-content;
}

.date-headers {
  display: flex;
  align-items: stretch;
  position: sticky;
  top: 0;
  background: var(--color-surface-elevated, #f9fafb);
  z-index: 10;
  border-bottom: 2px solid var(--color-border, #e5e7eb);
}

.item-label-column {
  width: 280px;
  flex-shrink: 0;
  border-right: 1px solid var(--color-border, #e5e7eb);
}

.timeline-dates {
  display: flex;
  flex: 1;
}

.date-column-header {
  flex-shrink: 0;
  padding: 0.5rem 0.25rem;
  text-align: center;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-text-secondary, #6b7280);
  border-left: 1px solid var(--color-border-light, #f3f4f6);
}

.timeline-rows {
  position: relative;
}

.timeline-row {
  display: flex;
  align-items: stretch;
  border-bottom: 1px solid var(--color-border-light, #f3f4f6);
  cursor: pointer;
  transition: background 0.15s;
}

.timeline-row:hover {
  background: var(--color-surface-elevated, #fafbfc);
}

.item-label {
  width: 280px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  border-right: 1px solid var(--color-border, #e5e7eb);
}

.item-identifier {
  font-family: monospace;
  font-size: 0.7rem;
  color: var(--color-text-secondary, #9ca3af);
  flex-shrink: 0;
}

.item-title {
  flex: 1;
  font-size: 0.8125rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-points {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--color-text-secondary, #9ca3af);
  flex-shrink: 0;
}

.timeline-track {
  flex: 1;
  position: relative;
}

.timeline-svg {
  display: block;
  width: 100%;
  height: 100%;
}

.grid-line {
  stroke: var(--color-border-light, #f3f4f6);
  stroke-width: 1;
}

.item-bar {
  fill: var(--color-primary, #3b82f6);
  opacity: 0.8;
  rx: 3;
  cursor: pointer;
  transition: opacity 0.15s;
}

.item-bar:hover {
  opacity: 1;
}

.item-bar.priority-critical {
  fill: #ef4444;
}

.item-bar.priority-high {
  fill: #f97316;
}

.item-bar.priority-medium {
  fill: #3b82f6;
}

.item-bar.priority-low {
  fill: #22c55e;
}

.item-bar.critical {
  stroke: #dc2626;
  stroke-width: 2;
  filter: drop-shadow(0 2px 4px rgba(220, 38, 38, 0.3));
}

.bar-label {
  fill: white;
  font-size: 0.7rem;
  font-weight: 600;
  pointer-events: none;
}

.dependencies-overlay {
  position: absolute;
  top: 100px;
  left: 0;
  width: 100%;
  pointer-events: none;
  z-index: 5;
}

.dependency-arrow {
  stroke: #6b7280;
  stroke-width: 2;
  fill: none;
  opacity: 0.6;
}
</style>
