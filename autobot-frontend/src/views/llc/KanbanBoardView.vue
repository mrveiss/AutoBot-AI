<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="kanban-board-view">
    <div class="kanban-header">
      <h2 class="view-title">Kanban Board</h2>
      <div class="header-controls">
        <label class="swimlane-toggle">
          <input type="checkbox" v-model="swimlaneEnabled" />
          <span>Group by assignee type</span>
        </label>
      </div>
    </div>

    <div class="board-layout">
      <div
        v-for="col in columns"
        :key="col.id"
        class="kanban-column"
        @dragover.prevent
        @drop="onDrop(col.id)"
      >
        <div
          class="column-header"
          :class="{
            'wip-warn': isWipWarn(col),
            'wip-exceeded': isWipExceeded(col),
          }"
        >
          <span class="column-title">{{ col.title }}</span>
          <div class="column-meta">
            <span class="column-count">{{ itemsByColumn(col.id).length }}</span>
            <span v-if="col.wip_limit" class="wip-limit" :title="`WIP limit: ${col.wip_limit}`">
              / {{ col.wip_limit }}
            </span>
          </div>
        </div>

        <template v-if="swimlaneEnabled">
          <!-- Human swimlane -->
          <div class="swimlane">
            <div class="swimlane-label">
              <svg class="lane-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
              </svg>
              Human
            </div>
            <div class="lane-cards">
              <div
                v-for="item in humanItems(col.id)"
                :key="item.id"
                class="work-card"
                draggable="true"
                @dragstart="onDragStart(item)"
                @click="openDetail(item)"
              >
                <KanbanCard :item="item" />
              </div>
              <div v-if="humanItems(col.id).length === 0" class="lane-empty">—</div>
            </div>
          </div>

          <!-- Agent swimlane -->
          <div class="swimlane">
            <div class="swimlane-label">
              <svg class="lane-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
              Agent
            </div>
            <div class="lane-cards">
              <div
                v-for="item in agentItems(col.id)"
                :key="item.id"
                class="work-card"
                draggable="true"
                @dragstart="onDragStart(item)"
                @click="openDetail(item)"
              >
                <KanbanCard :item="item" />
              </div>
              <div v-if="agentItems(col.id).length === 0" class="lane-empty">—</div>
            </div>
          </div>
        </template>

        <template v-else>
          <div class="column-cards">
            <div
              v-for="item in itemsByColumn(col.id)"
              :key="item.id"
              class="work-card"
              draggable="true"
              @dragstart="onDragStart(item)"
              @click="openDetail(item)"
            >
              <KanbanCard :item="item" />
            </div>
            <div v-if="itemsByColumn(col.id).length === 0" class="column-empty">
              Drop items here
            </div>
          </div>
        </template>
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
import { ref, computed, onMounted, onUnmounted, defineComponent, h } from 'vue'
import { useRoute } from 'vue-router'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import WorkItemDetail from './WorkItemDetail.vue'

const logger = createLogger('KanbanBoardView')
const api = useApiClient()
const route = useRoute()

const companyId = computed(() => route.params.companyId as string)
const boardId = computed(() => route.params.boardId as string)

import type { WorkItem } from './workItemTypes'

interface BoardColumn {
  id: string
  title: string
  wip_limit: number | null
}

const columns = ref<BoardColumn[]>([])
const items = ref<WorkItem[]>([])
const isLoading = ref(false)
const detailItem = ref<WorkItem | null>(null)
const draggedItem = ref<WorkItem | null>(null)
const swimlaneEnabled = ref(false)
let ws: WebSocket | null = null

function itemsByColumn(colId: string) {
  return items.value.filter(i => i.column_id === colId)
}

function humanItems(colId: string) {
  return items.value.filter(i => i.column_id === colId && i.assignee_type === 'human')
}

function agentItems(colId: string) {
  return items.value.filter(i => i.column_id === colId && i.assignee_type === 'agent')
}

function isWipWarn(col: BoardColumn) {
  if (!col.wip_limit) return false
  const count = itemsByColumn(col.id).length
  return count >= col.wip_limit * 0.8 && count < col.wip_limit
}

function isWipExceeded(col: BoardColumn) {
  if (!col.wip_limit) return false
  return itemsByColumn(col.id).length >= col.wip_limit
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
}

async function fetchBoard() {
  isLoading.value = true
  try {
    const [boardData, itemsData] = await Promise.all([
      api.get<{ columns: BoardColumn[] }>(`/api/llc/boards/${boardId.value}`),
      api.get<{ items: WorkItem[] }>(`/api/llc/boards/${boardId.value}/items`),
    ])
    columns.value = boardData.columns ?? []
    items.value = itemsData.items ?? []
  } catch (err) {
    logger.error('Failed to load board', err)
  } finally {
    isLoading.value = false
  }
}

// Inline card component to avoid extra file
const KanbanCard = defineComponent({
  props: { item: { type: Object as () => WorkItem, required: true } },
  setup(props) {
    function initials(name: string) {
      return name.split(' ').map((w: string) => w[0]).join('').slice(0, 2).toUpperCase()
    }
    return () => h('div', { class: 'kanban-card-inner' }, [
      h('div', { class: 'card-header-row' }, [
        h('span', { class: 'card-id' }, props.item.identifier),
        h('span', { class: `card-type type-${props.item.type}` }, props.item.type),
        props.item.linked_pr_urls?.length
          ? h('span', { class: 'pr-badge', title: `${props.item.linked_pr_urls.length} PR(s) linked` }, '🔗')
          : null,
      ]),
      h('p', { class: 'card-title' }, props.item.title),
      h('div', { class: 'card-footer-row' }, [
        h('span', { class: `priority-dot priority-${props.item.priority}`, title: props.item.priority }),
        props.item.story_points ? h('span', { class: 'card-pts' }, String(props.item.story_points)) : null,
        props.item.assignee_name
          ? h('span', { class: 'card-avatar', title: props.item.assignee_name }, initials(props.item.assignee_name))
          : null,
      ]),
    ])
  },
})

onMounted(async () => {
  await fetchBoard()
  connectWS()
})

onUnmounted(() => ws?.close())
</script>

<style scoped>
.kanban-board-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 1.5rem;
  gap: 1rem;
  background: var(--bg-primary);
  color: var(--text-primary);
}

.kanban-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.view-title {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 600;
}

.swimlane-toggle {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  cursor: pointer;
  user-select: none;
}

.board-layout {
  display: flex;
  gap: 0.75rem;
  flex: 1;
  min-height: 0;
  overflow-x: auto;
  align-items: flex-start;
}

.kanban-column {
  flex: 0 0 240px;
  background: var(--bg-elevated, #f9fafb);
  border-radius: 0.5rem;
  border: 1px solid var(--border-default, #e5e7eb);
  display: flex;
  flex-direction: column;
  /* #10750 C2: bounded by .board-layout height, not the viewport */
  min-height: 0;
  max-height: 100%;
}

.column-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.625rem 0.875rem;
  font-weight: 600;
  font-size: 0.875rem;
  border-bottom: 1px solid var(--border-default, #e5e7eb);
  border-radius: 0.5rem 0.5rem 0 0;
  transition: background 0.15s;
}

.column-header.wip-warn {
  background: #fef9c3;
  color: #713f12;
}

.column-header.wip-exceeded {
  background: #fee2e2;
  color: #991b1b;
}

.column-meta {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.column-count {
  font-size: 0.75rem;
  font-weight: 700;
}

.wip-limit {
  font-size: 0.7rem;
  color: var(--text-secondary, #9ca3af);
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

.swimlane {
  border-bottom: 1px solid var(--border-default, #e5e7eb);
  padding: 0.5rem;
}

.swimlane:last-child {
  border-bottom: none;
}

.swimlane-label {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-secondary, #6b7280);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 0.375rem;
}

.lane-icon {
  width: 0.875rem;
  height: 0.875rem;
}

.lane-cards {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.lane-empty {
  font-size: 0.75rem;
  color: var(--text-secondary, #9ca3af);
  text-align: center;
  padding: 0.5rem;
}

.work-card {
  cursor: grab;
}

.work-card:active {
  cursor: grabbing;
}

.kanban-card-inner {
  background: var(--bg-surface, #fff);
  border: 1px solid var(--border-default, #e5e7eb);
  border-radius: 0.375rem;
  padding: 0.5rem 0.625rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  transition: box-shadow 0.15s;
}

.kanban-card-inner:hover {
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
}

.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-id {
  font-family: monospace;
  font-size: 0.65rem;
  color: var(--text-secondary, #9ca3af);
}

.card-type {
  font-size: 0.6rem;
  padding: 0.1rem 0.35rem;
  border-radius: 9999px;
  font-weight: 500;
  text-transform: capitalize;
}

.pr-badge {
  font-size: 0.7rem;
  cursor: help;
  opacity: 0.8;
  transition: opacity 0.15s;
}

.pr-badge:hover {
  opacity: 1;
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
  font-size: 0.78rem;
  line-height: 1.35;
}

.card-footer-row {
  display: flex;
  align-items: center;
  gap: 0.375rem;
}

.priority-dot {
  width: 0.45rem;
  height: 0.45rem;
  border-radius: 50%;
  flex-shrink: 0;
}

.priority-critical { background: #ef4444; }
.priority-high { background: #f97316; }
.priority-medium { background: #eab308; }
.priority-low { background: #22c55e; }

.card-pts {
  font-size: 0.65rem;
  font-weight: 600;
  background: var(--bg-elevated, #f3f4f6);
  padding: 0.1rem 0.35rem;
  border-radius: 0.2rem;
}

.card-avatar {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.4rem;
  height: 1.4rem;
  border-radius: 50%;
  background: var(--color-primary, #3b82f6);
  color: white;
  font-size: 0.55rem;
  font-weight: 600;
}

.column-empty {
  text-align: center;
  padding: 1.5rem 0.5rem;
  font-size: 0.75rem;
  color: var(--text-secondary, #9ca3af);
  border: 2px dashed var(--border-default, #e5e7eb);
  border-radius: 0.375rem;
  margin: 0.5rem;
}
</style>
