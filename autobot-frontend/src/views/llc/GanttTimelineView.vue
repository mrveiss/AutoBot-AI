<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025-2026 mrveiss -->
<!-- Author: mrveiss -->
<!--
  GanttTimelineView (GH#9020) — project timeline / Gantt chart for sprint
  planning and roadmaps. Renders work items as horizontal bars from a custom
  SVG (no external Gantt library), with blocked-by dependency arrows, critical
  path highlighting, drag-to-reschedule, zoom levels, and PNG export.
-->
<template>
  <div class="gantt-view">
    <header class="gantt-toolbar">
      <h2 class="gantt-title">Timeline</h2>
      <div class="gantt-controls">
        <label class="gantt-field">
          <span class="gantt-field-label">Project</span>
          <select v-model="selectedProjectId" class="gantt-select" @change="loadTimeline">
            <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </label>
        <label class="gantt-field">
          <span class="gantt-field-label">Zoom</span>
          <select v-model="zoom" class="gantt-select">
            <option value="day">Day</option>
            <option value="week">Week</option>
            <option value="month">Month</option>
            <option value="quarter">Quarter</option>
          </select>
        </label>
        <button class="gantt-btn" :disabled="!items.length" @click="exportPng">Export PNG</button>
      </div>
    </header>

    <div v-if="loading" class="gantt-state">Loading timeline…</div>
    <div v-else-if="!projects.length" class="gantt-state">No projects in this company yet.</div>
    <div v-else-if="!items.length" class="gantt-state">This project has no work items to schedule.</div>

    <div v-else class="gantt-scroll">
      <svg
        ref="svgEl"
        class="gantt-svg"
        :width="chartWidth + LABEL_W"
        :height="chartHeight + HEADER_H"
        role="img"
        aria-label="Project timeline Gantt chart"
      >
        <defs>
          <marker
            id="gantt-arrow"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--gantt-arrow, #94a3b8)" />
          </marker>
        </defs>

        <!-- Time axis -->
        <g class="gantt-axis">
          <line
            v-for="(t, i) in axisTicks"
            :key="'tick' + i"
            :x1="LABEL_W + t.x"
            :y1="HEADER_H"
            :x2="LABEL_W + t.x"
            :y2="HEADER_H + chartHeight"
            class="gantt-gridline"
          />
          <text
            v-for="(t, i) in axisTicks"
            :key="'lbl' + i"
            :x="LABEL_W + t.x + 4"
            :y="HEADER_H - 6"
            class="gantt-axis-label"
          >
            {{ t.label }}
          </text>
        </g>

        <!-- Dependency arrows -->
        <path
          v-for="(arrow, i) in dependencyArrows"
          :key="'arrow' + i"
          :d="arrow"
          class="gantt-dep"
          marker-end="url(#gantt-arrow)"
          fill="none"
        />

        <!-- Rows -->
        <g v-for="(row, idx) in rows" :key="row.id" class="gantt-row">
          <text :x="8" :y="rowY(idx) + BAR_H / 2 + 4" class="gantt-row-label" :title="row.title">
            {{ row.identifier }}
          </text>
          <rect
            v-if="row.scheduled"
            :x="LABEL_W + row.x"
            :y="rowY(idx)"
            :width="row.width"
            :height="BAR_H"
            rx="4"
            class="gantt-bar"
            :class="{ 'gantt-bar--critical': row.onCriticalPath }"
            @mousedown.prevent="startMove($event, row)"
          >
            <title>{{ row.title }} ({{ row.status }})</title>
          </rect>
          <!-- resize handle (right edge) -->
          <rect
            v-if="row.scheduled"
            :x="LABEL_W + row.x + row.width - 5"
            :y="rowY(idx)"
            :width="6"
            :height="BAR_H"
            class="gantt-handle"
            @mousedown.prevent.stop="startResize($event, row)"
          />
          <text
            v-else
            :x="LABEL_W + 4"
            :y="rowY(idx) + BAR_H / 2 + 4"
            class="gantt-unscheduled"
          >
            unscheduled
          </text>
        </g>
      </svg>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import { useI18n } from 'vue-i18n'
import { useNotificationBus } from '@/composables/useNotificationBus'

const logger = createLogger('GanttTimelineView')
const api = useApiClient()
const route = useRoute()
const { t } = useI18n()
const { showToast } = useNotificationBus()

const LABEL_W = 120
const HEADER_H = 32
const ROW_H = 34
const BAR_H = 20
const DAY_MS = 86_400_000

const ZOOM_PX_PER_DAY: Record<string, number> = { day: 40, week: 14, month: 5, quarter: 2 }

interface Project {
  id: string
  name: string
}
interface TimelineItem {
  id: string
  identifier: string
  title: string
  type: string
  status: string
  scheduled_start: string | null
  scheduled_end: string | null
  started_at: string | null
  completed_at: string | null
  on_critical_path: boolean
}
interface TimelineEdge {
  from_id: string
  to_id: string
}
interface Timeline {
  project_id: string
  items: TimelineItem[]
  edges: TimelineEdge[]
}

const companyId = computed(() => route.params.companyId as string)
const projects = ref<Project[]>([])
const selectedProjectId = ref<string>('')
const items = ref<TimelineItem[]>([])
const edges = ref<TimelineEdge[]>([])
const zoom = ref<'day' | 'week' | 'month' | 'quarter'>('week')
const loading = ref(false)
const svgEl = ref<SVGSVGElement | null>(null)

const pxPerDay = computed(() => ZOOM_PX_PER_DAY[zoom.value])

// --- date helpers ---------------------------------------------------------
function barDates(it: TimelineItem): { start: number; end: number } | null {
  const startStr = it.scheduled_start ?? it.started_at
  const endStr = it.scheduled_end ?? it.completed_at
  if (!startStr || !endStr) return null
  const start = Date.parse(startStr)
  const end = Date.parse(endStr)
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return null
  return { start, end }
}

const rangeStart = computed(() => {
  const starts = items.value.map(barDates).filter(Boolean).map((d) => d!.start)
  return starts.length ? Math.min(...starts) : Date.now()
})
const rangeEnd = computed(() => {
  const ends = items.value.map(barDates).filter(Boolean).map((d) => d!.end)
  const max = ends.length ? Math.max(...ends) : Date.now() + 30 * DAY_MS
  return Math.max(max, rangeStart.value + 7 * DAY_MS)
})

function xForMs(ms: number): number {
  return ((ms - rangeStart.value) / DAY_MS) * pxPerDay.value
}

const chartWidth = computed(() => Math.max(xForMs(rangeEnd.value) + 40, 320))
const chartHeight = computed(() => Math.max(items.value.length * ROW_H, ROW_H))

function rowY(idx: number): number {
  return HEADER_H + idx * ROW_H + (ROW_H - BAR_H) / 2
}

interface Row extends TimelineItem {
  x: number
  width: number
  scheduled: boolean
  onCriticalPath: boolean
}

const rows = computed<Row[]>(() =>
  items.value.map((it) => {
    const d = barDates(it)
    return {
      ...it,
      x: d ? xForMs(d.start) : 0,
      width: d ? Math.max(xForMs(d.end) - xForMs(d.start), 6) : 0,
      scheduled: !!d,
      onCriticalPath: it.on_critical_path,
    }
  })
)

const rowIndexById = computed(() => {
  const m = new Map<string, number>()
  items.value.forEach((it, i) => m.set(it.id, i))
  return m
})

const dependencyArrows = computed<string[]>(() => {
  const out: string[] = []
  for (const edge of edges.value) {
    const fromIdx = rowIndexById.value.get(edge.from_id)
    const toIdx = rowIndexById.value.get(edge.to_id)
    if (fromIdx === undefined || toIdx === undefined) continue
    const from = rows.value[fromIdx]
    const to = rows.value[toIdx]
    if (!from.scheduled || !to.scheduled) continue
    const x1 = LABEL_W + from.x + from.width
    const y1 = rowY(fromIdx) + BAR_H / 2
    const x2 = LABEL_W + to.x
    const y2 = rowY(toIdx) + BAR_H / 2
    const midX = (x1 + x2) / 2
    out.push(`M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`)
  }
  return out
})

// --- axis ticks -----------------------------------------------------------
const axisTicks = computed(() => {
  const ticks: { x: number; label: string }[] = []
  const step = zoom.value === 'day' ? 1 : zoom.value === 'week' ? 7 : zoom.value === 'month' ? 30 : 91
  for (let ms = rangeStart.value; ms <= rangeEnd.value; ms += step * DAY_MS) {
    const d = new Date(ms)
    const label =
      zoom.value === 'quarter'
        ? `Q${Math.floor(d.getMonth() / 3) + 1} ${d.getFullYear()}`
        : zoom.value === 'month'
          ? d.toLocaleDateString(undefined, { month: 'short', year: '2-digit' })
          : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
    ticks.push({ x: xForMs(ms), label })
  }
  return ticks
})

// --- drag to reschedule ---------------------------------------------------
interface DragState {
  row: Row
  startX: number
  origStart: number
  origEnd: number
  mode: 'move' | 'resize'
}
let drag: DragState | null = null

function itemDates(row: Row): { start: number; end: number } {
  const d = barDates(row)
  return d ?? { start: rangeStart.value, end: rangeStart.value + DAY_MS }
}

function startMove(ev: MouseEvent, row: Row) {
  const { start, end } = itemDates(row)
  drag = { row, startX: ev.clientX, origStart: start, origEnd: end, mode: 'move' }
  window.addEventListener('mousemove', onDragMove)
  window.addEventListener('mouseup', onDragEnd)
}

function startResize(ev: MouseEvent, row: Row) {
  const { start, end } = itemDates(row)
  drag = { row, startX: ev.clientX, origStart: start, origEnd: end, mode: 'resize' }
  window.addEventListener('mousemove', onDragMove)
  window.addEventListener('mouseup', onDragEnd)
}

function onDragMove(ev: MouseEvent) {
  if (!drag) return
  const deltaDays = Math.round((ev.clientX - drag.startX) / pxPerDay.value)
  if (!deltaDays) return
  const target = items.value.find((i) => i.id === drag!.row.id)
  if (!target) return
  if (drag.mode === 'move') {
    target.scheduled_start = new Date(drag.origStart + deltaDays * DAY_MS).toISOString()
    target.scheduled_end = new Date(drag.origEnd + deltaDays * DAY_MS).toISOString()
  } else {
    const newEnd = Math.max(drag.origEnd + deltaDays * DAY_MS, drag.origStart + DAY_MS)
    target.scheduled_start = new Date(drag.origStart).toISOString()
    target.scheduled_end = new Date(newEnd).toISOString()
  }
}

async function onDragEnd() {
  window.removeEventListener('mousemove', onDragMove)
  window.removeEventListener('mouseup', onDragEnd)
  if (!drag) return
  const target = items.value.find((i) => i.id === drag!.row.id)
  drag = null
  if (!target) return
  try {
    await api.patch(`/api/llc/work-items/${target.id}`, {
      scheduled_start: target.scheduled_start,
      scheduled_end: target.scheduled_end,
    })
  } catch (err) {
    logger.error('Failed to persist reschedule', err)
    showToast(t('llcBrowser.timeline.rescheduleError'), 'error')
    await loadTimeline()
  }
}

// --- PNG export -----------------------------------------------------------
async function exportPng() {
  const svg = svgEl.value
  if (!svg) return
  try {
    const xml = new XMLSerializer().serializeToString(svg)
    const blob = new Blob([xml], { type: 'image/svg+xml;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const img = new Image()
    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve()
      img.onerror = () => reject(new Error('SVG render failed'))
      img.src = url
    })
    const canvas = document.createElement('canvas')
    canvas.width = svg.width.baseVal.value
    canvas.height = svg.height.baseVal.value
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.fillStyle = '#ffffff'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(img, 0, 0)
    URL.revokeObjectURL(url)
    const link = document.createElement('a')
    link.download = `timeline-${selectedProjectId.value}.png`
    link.href = canvas.toDataURL('image/png')
    link.click()
  } catch (err) {
    logger.error('PNG export failed', err)
  }
}

// --- data loading ---------------------------------------------------------
async function loadProjects() {
  try {
    projects.value = await api.get<Project[]>(`/api/llc/companies/${companyId.value}/projects`)
    if (projects.value.length && !selectedProjectId.value) {
      selectedProjectId.value = projects.value[0].id
    }
  } catch (err) {
    logger.error('Failed to load projects', err)
  }
}

async function loadTimeline() {
  if (!selectedProjectId.value) return
  loading.value = true
  try {
    const data = await api.get<Timeline>(`/api/llc/projects/${selectedProjectId.value}/timeline`)
    items.value = data.items
    edges.value = data.edges
  } catch (err) {
    logger.error('Failed to load timeline', err)
    items.value = []
    edges.value = []
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  loading.value = true
  await loadProjects()
  await loadTimeline()
})

onBeforeUnmount(() => {
  window.removeEventListener('mousemove', onDragMove)
  window.removeEventListener('mouseup', onDragEnd)
})
</script>

<style scoped>
.gantt-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 1rem;
  gap: 0.75rem;
}

.gantt-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.gantt-title {
  font-size: 1.1rem;
  font-weight: 600;
  margin: 0;
}

.gantt-controls {
  display: flex;
  align-items: flex-end;
  gap: 0.75rem;
}

.gantt-field {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.gantt-field-label {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-secondary, #9ca3af);
}

.gantt-select {
  padding: 0.3rem 0.5rem;
  border-radius: 6px;
  border: 1px solid var(--border-default, #d1d5db);
  background: var(--bg-surface, #fff);
  color: var(--text-primary, #111827);
}

.gantt-btn {
  padding: 0.4rem 0.8rem;
  border-radius: 6px;
  border: 1px solid var(--border-default, #d1d5db);
  background: var(--bg-surface, #fff);
  cursor: pointer;
  font-size: 0.8rem;
}

.gantt-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.gantt-state {
  padding: 2rem;
  text-align: center;
  color: var(--text-secondary, #9ca3af);
}

.gantt-scroll {
  /* #10750 C2: fill remaining height of the flex-column view and scroll internally */
  flex: 1;
  min-height: 0;
  overflow: auto;
  border: 1px solid var(--border-default, #e5e7eb);
  border-radius: 8px;
  background: var(--bg-surface, #fff);
}

.gantt-gridline {
  stroke: var(--border-default, #e5e7eb);
  stroke-width: 1;
}

.gantt-axis-label {
  font-size: 10px;
  fill: var(--text-secondary, #9ca3af);
}

.gantt-row-label {
  font-size: 10px;
  font-family: monospace;
  fill: var(--text-secondary, #6b7280);
}

.gantt-bar {
  fill: var(--color-primary, #3b82f6);
  cursor: grab;
}

.gantt-bar--critical {
  fill: var(--color-error, #ef4444);
}

.gantt-handle {
  fill: rgba(0, 0, 0, 0.25);
  cursor: ew-resize;
}

.gantt-dep {
  stroke: var(--gantt-arrow, #94a3b8);
  stroke-width: 1.5;
  stroke-dasharray: 3 2;
}

.gantt-unscheduled {
  font-size: 10px;
  fill: var(--text-secondary, #9ca3af);
  font-style: italic;
}
</style>
