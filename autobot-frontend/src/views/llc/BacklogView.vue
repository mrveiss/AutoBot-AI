<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="llc-backlog-view">
    <div class="backlog-header">
      <div class="header-left">
        <h2 class="view-title">{{ t('llc.backlog.title') }}</h2>
        <span class="item-count">{{ t('llc.backlog.itemCount', { count: filteredItems.length }) }}</span>
      </div>
      <div class="header-actions">
        <button class="btn-primary" @click="showCreateForm = true">
          <svg class="btn-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
          </svg>
          {{ t('llc.backlog.createWorkItem') }}
        </button>
        <button
          v-if="selectedIds.size > 0"
          class="btn-secondary"
          @click="showBulkAssign = true"
        >
          {{ t('llc.backlog.assignSprint', { count: selectedIds.size }) }}
        </button>
      </div>
    </div>

    <!-- Filters -->
    <div class="backlog-filters">
      <select v-model="filters.type" class="filter-select">
        <option value="">{{ t('llc.backlog.allTypes') }}</option>
        <option v-for="wt in WORK_ITEM_TYPES" :key="wt.value" :value="wt.value">{{ wt.label }}</option>
      </select>
      <select v-model="filters.status" class="filter-select">
        <option value="">{{ t('llc.backlog.allStatuses') }}</option>
        <option value="backlog">{{ t('llc.backlog.statusBacklog') }}</option>
        <option value="ready">{{ t('llc.backlog.statusReady') }}</option>
      </select>
      <select v-model="filters.priority" class="filter-select">
        <option value="">{{ t('llc.backlog.allPriorities') }}</option>
        <option v-for="p in PRIORITIES" :key="p.value" :value="p.value">{{ p.label }}</option>
      </select>
      <input
        v-model="filters.search"
        class="filter-search"
        :placeholder="t('llc.backlog.searchPlaceholder')"
        type="text"
      />
    </div>

    <!-- Table -->
    <div class="backlog-table-wrapper">
      <table class="backlog-table">
        <thead>
          <tr>
            <th class="col-check">
              <input
                type="checkbox"
                :checked="allSelected"
                :indeterminate="someSelected"
                @change="toggleSelectAll"
              />
            </th>
            <th class="col-id">{{ t('llc.backlog.colId') }}</th>
            <th class="col-type">{{ t('llc.backlog.colType') }}</th>
            <th class="col-title">{{ t('llc.backlog.colTitle') }}</th>
            <th class="col-priority">{{ t('llc.backlog.colPriority') }}</th>
            <th class="col-points">{{ t('llc.backlog.colPoints') }}</th>
            <th class="col-assignee">{{ t('llc.backlog.colAssignee') }}</th>
            <th class="col-sprint">{{ t('llc.backlog.colSprint') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="item in filteredItems"
            :key="item.id"
            class="backlog-row"
            :class="{ selected: selectedIds.has(item.id) }"
            :draggable="true"
            @dragstart="onDragStart(item)"
            @dragover.prevent
            @drop="onDrop(item)"
            @click="openDetail(item)"
          >
            <td class="col-check" @click.stop>
              <input
                type="checkbox"
                :checked="selectedIds.has(item.id)"
                @change="toggleSelect(item.id)"
              />
            </td>
            <td class="col-id">
              <span class="item-identifier">{{ item.identifier }}</span>
            </td>
            <td class="col-type">
              <span class="type-badge" :class="`type-${item.type}`">{{ workItemTypeLabel(item.type) }}</span>
            </td>
            <td class="col-title">{{ item.title }}</td>
            <td class="col-priority">
              <span class="priority-badge" :class="`priority-${item.priority}`">
                {{ priorityLabel(item.priority) }}
              </span>
            </td>
            <td class="col-points">{{ item.story_points ?? '—' }}</td>
            <td class="col-assignee">
              <span v-if="item.assignee_name" class="assignee-avatar" :title="item.assignee_name">
                {{ initials(item.assignee_name) }}
              </span>
              <span v-else class="assignee-empty">—</span>
            </td>
            <td class="col-sprint">
              <span v-if="item.sprint_id" class="sprint-tag">{{ t('llc.backlog.sprintTag', { id: item.sprint_id.slice(0, 8) }) }}</span>
              <span v-else class="sprint-empty">—</span>
            </td>
          </tr>
          <tr v-if="filteredItems.length === 0 && !isLoading">
            <td colspan="8" class="empty-state">{{ t('llc.backlog.noMatch') }}</td>
          </tr>
          <tr v-if="isLoading">
            <td colspan="8" class="loading-state">{{ t('llc.backlog.loading') }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- AC Suggester create form -->
    <div v-if="showCreateForm" class="modal-overlay" @click.self="showCreateForm = false">
      <div class="modal-panel">
        <h3>{{ t('llc.backlog.createTitle') }}</h3>
        <div class="form-field">
          <label>{{ t('llc.backlog.fieldTitle') }}</label>
          <input v-model="newItem.title" type="text" class="form-input" :placeholder="t('llc.backlog.titlePlaceholder')" />
        </div>
        <div class="form-row">
          <div class="form-field">
            <label>{{ t('llc.backlog.fieldType') }}</label>
            <select v-model="newItem.type" class="form-select">
              <option v-for="wt in WORK_ITEM_TYPES" :key="wt.value" :value="wt.value">{{ wt.label }}</option>
            </select>
          </div>
          <div class="form-field">
            <label>{{ t('llc.backlog.fieldPriority') }}</label>
            <select v-model="newItem.priority" class="form-select">
              <option v-for="p in PRIORITIES" :key="p.value" :value="p.value">{{ p.label }}</option>
            </select>
          </div>
          <div class="form-field">
            <label>{{ t('llc.backlog.fieldStoryPoints') }}</label>
            <input v-model.number="newItem.story_points" type="number" class="form-input" min="0" />
          </div>
        </div>
        <div class="form-field">
          <label>{{ t('llc.backlog.fieldDescription') }}</label>
          <textarea v-model="newItem.description" class="form-textarea" rows="4" />
        </div>

        <!-- AC Suggester -->
        <div class="ac-suggester">
          <div class="ac-header">
            <label>{{ t('llc.backlog.acceptanceCriteria') }}</label>
            <button
              class="btn-suggest"
              :disabled="!newItem.title || isSuggestingAC"
              @click="suggestAC"
            >
              <span v-if="isSuggestingAC">{{ t('llc.backlog.suggesting') }}</span>
              <span v-else>✨ {{ t('llc.backlog.suggestAcs') }}</span>
            </button>
          </div>
          <div v-if="suggestedACs.length > 0" class="suggested-acs">
            <label
              v-for="(ac, i) in suggestedACs"
              :key="i"
              class="ac-item"
            >
              <input type="checkbox" v-model="ac.selected" />
              {{ ac.text }}
            </label>
          </div>
        </div>

        <div class="modal-actions">
          <button class="btn-secondary" @click="showCreateForm = false">{{ t('common.cancel') }}</button>
          <button class="btn-primary" :disabled="!newItem.title || isCreating" @click="createItem">
            {{ isCreating ? t('llc.backlog.creating') : t('common.create') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Bulk sprint assign drawer -->
    <div v-if="showBulkAssign" class="modal-overlay" @click.self="showBulkAssign = false">
      <div class="modal-panel">
        <h3>{{ t('llc.backlog.assignToSprint') }}</h3>
        <p>{{ t('llc.backlog.itemsSelected', { count: selectedIds.size }) }}</p>
        <div class="form-field">
          <label>{{ t('llc.backlog.sprintId') }}</label>
          <input v-model="bulkSprintId" type="text" class="form-input" :placeholder="t('llc.backlog.sprintIdPlaceholder')" />
        </div>
        <div class="modal-actions">
          <button class="btn-secondary" @click="showBulkAssign = false">{{ t('common.cancel') }}</button>
          <button class="btn-primary" :disabled="!bulkSprintId || isBulkAssigning" @click="bulkAssign">
            {{ isBulkAssigning ? t('llc.backlog.assigning') : t('llc.backlog.assign') }}
          </button>
        </div>
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
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useWorkItemLabels } from '@/composables/useWorkItemLabels'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import WorkItemDetail from './WorkItemDetail.vue'

const logger = createLogger('BacklogView')
const api = useApiClient()
const route = useRoute()
const { t } = useI18n()
const { workItemTypeLabel, priorityLabel } = useWorkItemLabels()

const companyId = computed(() => route.params.companyId as string)

const WORK_ITEM_TYPES = [
  { value: 'epic', label: 'Epic' },
  { value: 'feature', label: 'Feature' },
  { value: 'pbi', label: 'PBI' },
  { value: 'task', label: 'Task' },
  { value: 'bug', label: 'Bug' },
  { value: 'subtask', label: 'Subtask' },
  { value: 'spike', label: 'Spike' },
  { value: 'risk', label: 'Risk' },
]

const PRIORITIES = [
  { value: 'critical', label: 'Critical' },
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low', label: 'Low' },
]

import type { WorkItem } from './workItemTypes'

const items = ref<WorkItem[]>([])
const isLoading = ref(false)
const detailItem = ref<WorkItem | null>(null)
const selectedIds = ref<Set<string>>(new Set())
const draggedItem = ref<WorkItem | null>(null)

const filters = ref({ type: '', status: '', priority: '', search: '' })

const showCreateForm = ref(false)
const isCreating = ref(false)
const newItem = ref({ title: '', type: 'pbi', priority: 'medium', story_points: null as number | null, description: '' })
const isSuggestingAC = ref(false)
const suggestedACs = ref<{ text: string; selected: boolean }[]>([])

const showBulkAssign = ref(false)
const isBulkAssigning = ref(false)
const bulkSprintId = ref('')

const filteredItems = computed(() => {
  return items.value.filter(item => {
    if (filters.value.type && item.type !== filters.value.type) return false
    if (filters.value.status && item.status !== filters.value.status) return false
    if (filters.value.priority && item.priority !== filters.value.priority) return false
    if (filters.value.search) {
      const q = filters.value.search.toLowerCase()
      if (!item.title.toLowerCase().includes(q) && !item.identifier.toLowerCase().includes(q)) return false
    }
    return true
  })
})

const allSelected = computed(() =>
  filteredItems.value.length > 0 && filteredItems.value.every(i => selectedIds.value.has(i.id))
)
const someSelected = computed(() =>
  filteredItems.value.some(i => selectedIds.value.has(i.id)) && !allSelected.value
)

function initials(name: string) {
  return name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
}

function toggleSelect(id: string) {
  const next = new Set(selectedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selectedIds.value = next
}

function toggleSelectAll() {
  if (allSelected.value) {
    selectedIds.value = new Set()
  } else {
    selectedIds.value = new Set(filteredItems.value.map(i => i.id))
  }
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

async function onDrop(target: WorkItem) {
  if (!draggedItem.value || draggedItem.value.id === target.id) return
  const fromIdx = items.value.findIndex(i => i.id === draggedItem.value!.id)
  const toIdx = items.value.findIndex(i => i.id === target.id)
  if (fromIdx === -1 || toIdx === -1) return

  const previous = [...items.value]
  const reordered = [...items.value]
  const [moved] = reordered.splice(fromIdx, 1)
  reordered.splice(toIdx, 0, moved)
  items.value = reordered
  draggedItem.value = null

  await persistBacklogOrder(reordered, previous)
}

// Persist the new ordering (full desired order; backend assigns positions
// 0..n-1). On failure, revert to the pre-drag order so the UI never diverges
// from the server. Backend: POST /api/llc/companies/{id}/backlog/reorder (#9861).
async function persistBacklogOrder(ordered: WorkItem[], previous: WorkItem[]): Promise<void> {
  try {
    await api.post(`/api/llc/companies/${companyId.value}/backlog/reorder`, {
      work_item_ids: ordered.map(i => i.id),
    })
  } catch (err) {
    logger.error('Backlog reorder failed; reverting order', err)
    items.value = previous
  }
}

// Request advisory acceptance criteria for the in-progress new item. Company
// scope is derived from the org context server-side — never send company_id.
// Backend: POST /api/llc/work-items/suggest-ac (#9861); empty list on LLM-down.
async function suggestAC() {
  if (!newItem.value.title) return
  isSuggestingAC.value = true
  try {
    const res = await api.post<{ suggestions: string[] }>(`/api/llc/work-items/suggest-ac`, {
      title: newItem.value.title,
      description: newItem.value.description,
    })
    suggestedACs.value = (res.suggestions ?? []).map(text => ({ text, selected: true }))
  } catch (err) {
    logger.error('AC suggestion failed', err)
    suggestedACs.value = []
  } finally {
    isSuggestingAC.value = false
  }
}

async function createItem() {
  if (!newItem.value.title) return
  isCreating.value = true
  try {
    const ac = suggestedACs.value.filter(a => a.selected).map(a => a.text)
    const created = await api.post<WorkItem>(`/api/llc/work-items`, {
      company_id: companyId.value,
      ...newItem.value,
      acceptance_criteria: ac,
    })
    items.value.unshift(created)
    showCreateForm.value = false
    newItem.value = { title: '', type: 'pbi', priority: 'medium', story_points: null, description: '' }
    suggestedACs.value = []
  } catch (err) {
    logger.error('Create work item failed', err)
  } finally {
    isCreating.value = false
  }
}

async function bulkAssign() {
  if (!bulkSprintId.value) return
  isBulkAssigning.value = true
  try {
    await api.post<unknown>(`/api/llc/backlog/bulk-assign-sprint`, {
      work_item_ids: Array.from(selectedIds.value),
      sprint_id: bulkSprintId.value,
    })
    selectedIds.value = new Set()
    showBulkAssign.value = false
    bulkSprintId.value = ''
    await fetchBacklog()
  } catch (err) {
    logger.error('Bulk assign failed', err)
  } finally {
    isBulkAssigning.value = false
  }
}

async function fetchBacklog() {
  isLoading.value = true
  try {
    const result = await api.get<{ items: WorkItem[] }>(`/api/llc/backlog?company_id=${companyId.value}`)
    items.value = result.items ?? []
  } catch (err) {
    logger.error('Failed to load backlog', err)
  } finally {
    isLoading.value = false
  }
}

onMounted(fetchBacklog)
</script>

<style scoped>
.llc-backlog-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 1.5rem;
  gap: 1rem;
  background: var(--bg-primary);
  color: var(--text-primary);
}

.backlog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header-left {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
}

.view-title {
  font-size: 1.5rem;
  font-weight: 600;
  margin: 0;
}

.item-count {
  font-size: 0.875rem;
  color: var(--text-secondary, #6b7280);
}

.header-actions {
  display: flex;
  gap: 0.5rem;
}

.backlog-filters {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.filter-select,
.filter-search {
  padding: 0.4rem 0.75rem;
  border: 1px solid var(--border-default, #d1d5db);
  border-radius: 0.375rem;
  background: var(--bg-surface, #fff);
  color: var(--text-primary);
  font-size: 0.875rem;
}

.filter-search {
  flex: 1;
  min-width: 200px;
}

.backlog-table-wrapper {
  flex: 1;
  overflow: auto;
  border: 1px solid var(--border-default, #e5e7eb);
  border-radius: 0.5rem;
}

.backlog-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}

.backlog-table th {
  padding: 0.625rem 0.75rem;
  text-align: left;
  font-weight: 600;
  background: var(--bg-elevated, #f9fafb);
  border-bottom: 1px solid var(--border-default, #e5e7eb);
  white-space: nowrap;
}

.backlog-row {
  border-bottom: 1px solid var(--border-default, #f3f4f6);
  cursor: pointer;
  transition: background 0.1s;
}

.backlog-row:hover {
  background: var(--bg-hover, #f9fafb);
}

.backlog-row.selected {
  background: var(--color-primary-subtle, #eff6ff);
}

.backlog-table td {
  padding: 0.625rem 0.75rem;
}

.col-check { width: 2.5rem; }
.col-id { width: 6rem; }
.col-type { width: 6rem; }
.col-priority { width: 7rem; }
.col-points { width: 5rem; text-align: center; }
.col-assignee { width: 5rem; text-align: center; }
.col-sprint { width: 9rem; }

.item-identifier {
  font-family: monospace;
  font-size: 0.8rem;
  color: var(--text-secondary, #6b7280);
}

.type-badge,
.priority-badge {
  display: inline-block;
  padding: 0.125rem 0.5rem;
  border-radius: 9999px;
  font-size: 0.75rem;
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

.priority-critical { background: #fee2e2; color: #991b1b; }
.priority-high { background: #ffedd5; color: #9a3412; }
.priority-medium { background: #fef9c3; color: #713f12; }
.priority-low { background: #f0fdf4; color: #14532d; }

.assignee-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.75rem;
  height: 1.75rem;
  border-radius: 50%;
  background: var(--color-primary, #3b82f6);
  color: white;
  font-size: 0.65rem;
  font-weight: 600;
  cursor: default;
}

.sprint-tag {
  font-size: 0.75rem;
  padding: 0.125rem 0.5rem;
  background: #e0f2fe;
  color: #0369a1;
  border-radius: 0.25rem;
}

.empty-state,
.loading-state {
  text-align: center;
  padding: 2rem;
  color: var(--text-secondary, #9ca3af);
}

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
}

.modal-panel {
  background: var(--bg-surface, #fff);
  border-radius: 0.75rem;
  padding: 1.5rem;
  width: 100%;
  max-width: 560px;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  max-height: 90vh;
  overflow-y: auto;
}

.modal-panel h3 {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.form-field label {
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--text-secondary, #6b7280);
}

.form-row {
  display: flex;
  gap: 0.75rem;
}

.form-row .form-field {
  flex: 1;
}

.form-input,
.form-select,
.form-textarea {
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border-default, #d1d5db);
  border-radius: 0.375rem;
  background: var(--bg-surface, #fff);
  color: var(--text-primary);
  font-size: 0.875rem;
  width: 100%;
}

.form-textarea {
  resize: vertical;
}

.ac-suggester {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.ac-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.ac-header label {
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--text-secondary, #6b7280);
}

.btn-suggest {
  font-size: 0.8rem;
  padding: 0.25rem 0.75rem;
  border: 1px solid var(--border-default, #d1d5db);
  border-radius: 0.375rem;
  background: var(--bg-elevated, #f9fafb);
  cursor: pointer;
}

.btn-suggest:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.suggested-acs {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  padding: 0.5rem;
  border: 1px solid var(--border-default, #e5e7eb);
  border-radius: 0.375rem;
  background: var(--bg-elevated, #f9fafb);
}

.ac-item {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  font-size: 0.875rem;
  cursor: pointer;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}

.btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.5rem 1rem;
  background: var(--color-primary, #3b82f6);
  color: white;
  border: none;
  border-radius: 0.375rem;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
}

.btn-primary:hover:not(:disabled) {
  background: var(--color-primary-hover, #2563eb);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.5rem 1rem;
  background: var(--bg-surface, #fff);
  color: var(--text-primary);
  border: 1px solid var(--border-default, #d1d5db);
  border-radius: 0.375rem;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
}

.btn-secondary:hover {
  background: var(--bg-hover, #f9fafb);
}

.btn-icon {
  width: 1rem;
  height: 1rem;
}
</style>
