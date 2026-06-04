<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="llc-backlog-view">
    <div class="backlog-header">
      <div class="header-left">
        <h2 class="view-title">Backlog</h2>
        <span class="item-count">{{ filteredItems.length }} items</span>
      </div>
      <div class="header-actions">
        <button class="btn-primary" @click="showCreateForm = true">
          <svg class="btn-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
          </svg>
          Create Work Item
        </button>
        <button
          v-if="selectedIds.size > 0"
          class="btn-secondary"
          @click="showBulkAssign = true"
        >
          Assign Sprint ({{ selectedIds.size }})
        </button>
      </div>
    </div>

    <!-- Filters -->
    <div class="backlog-filters">
      <select v-model="filters.type" class="filter-select">
        <option value="">All Types</option>
        <option v-for="t in WORK_ITEM_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
      </select>
      <select v-model="filters.status" class="filter-select">
        <option value="">All Statuses</option>
        <option value="backlog">Backlog</option>
        <option value="ready">Ready</option>
      </select>
      <select v-model="filters.priority" class="filter-select">
        <option value="">All Priorities</option>
        <option v-for="p in PRIORITIES" :key="p.value" :value="p.value">{{ p.label }}</option>
      </select>
      <input
        v-model="filters.search"
        class="filter-search"
        placeholder="Search work items..."
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
            <th class="col-id">ID</th>
            <th class="col-type">Type</th>
            <th class="col-title">Title</th>
            <th class="col-priority">Priority</th>
            <th class="col-points">Points</th>
            <th class="col-assignee">Assignee</th>
            <th class="col-sprint">Sprint</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="item in filteredItems"
            :key="item.id"
            class="backlog-row"
            :class="{ selected: selectedIds.has(item.id) }"
            draggable="true"
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
              <span class="type-badge" :class="`type-${item.type}`">{{ item.type }}</span>
            </td>
            <td class="col-title">{{ item.title }}</td>
            <td class="col-priority">
              <span class="priority-badge" :class="`priority-${item.priority}`">
                {{ item.priority }}
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
              <span v-if="item.sprint_id" class="sprint-tag">Sprint {{ item.sprint_id.slice(0, 8) }}</span>
              <span v-else class="sprint-empty">—</span>
            </td>
          </tr>
          <tr v-if="filteredItems.length === 0 && !isLoading">
            <td colspan="8" class="empty-state">No items match the current filters.</td>
          </tr>
          <tr v-if="isLoading">
            <td colspan="8" class="loading-state">Loading...</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- AC Suggester create form -->
    <div v-if="showCreateForm" class="modal-overlay" @click.self="showCreateForm = false">
      <div class="modal-panel">
        <h3>Create Work Item</h3>
        <div class="form-field">
          <label>Title</label>
          <input v-model="newItem.title" type="text" class="form-input" placeholder="Work item title" />
        </div>
        <div class="form-row">
          <div class="form-field">
            <label>Type</label>
            <select v-model="newItem.type" class="form-select">
              <option v-for="t in WORK_ITEM_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
            </select>
          </div>
          <div class="form-field">
            <label>Priority</label>
            <select v-model="newItem.priority" class="form-select">
              <option v-for="p in PRIORITIES" :key="p.value" :value="p.value">{{ p.label }}</option>
            </select>
          </div>
          <div class="form-field">
            <label>Story Points</label>
            <input v-model.number="newItem.story_points" type="number" class="form-input" min="0" />
          </div>
        </div>
        <div class="form-field">
          <label>Description</label>
          <textarea v-model="newItem.description" class="form-textarea" rows="4" />
        </div>

        <!-- AC Suggester -->
        <div class="ac-suggester">
          <div class="ac-header">
            <label>Acceptance Criteria</label>
            <button
              class="btn-suggest"
              :disabled="!newItem.title || isSuggestingAC"
              @click="suggestAC"
            >
              <span v-if="isSuggestingAC">Suggesting...</span>
              <span v-else>✨ Suggest ACs</span>
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
          <button class="btn-secondary" @click="showCreateForm = false">Cancel</button>
          <button class="btn-primary" :disabled="!newItem.title || isCreating" @click="createItem">
            {{ isCreating ? 'Creating...' : 'Create' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Bulk sprint assign drawer -->
    <div v-if="showBulkAssign" class="modal-overlay" @click.self="showBulkAssign = false">
      <div class="modal-panel">
        <h3>Assign to Sprint</h3>
        <p>{{ selectedIds.size }} items selected</p>
        <div class="form-field">
          <label>Sprint ID</label>
          <input v-model="bulkSprintId" type="text" class="form-input" placeholder="Sprint UUID" />
        </div>
        <div class="modal-actions">
          <button class="btn-secondary" @click="showBulkAssign = false">Cancel</button>
          <button class="btn-primary" :disabled="!bulkSprintId || isBulkAssigning" @click="bulkAssign">
            {{ isBulkAssigning ? 'Assigning...' : 'Assign' }}
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
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import WorkItemDetail from './WorkItemDetail.vue'

const logger = createLogger('BacklogView')
const api = useApiClient()
const route = useRoute()

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

interface WorkItem {
  id: string
  identifier: string
  type: string
  title: string
  description: string
  priority: string
  story_points: number | null
  assignee_name: string | null
  sprint_id: string | null
  status: string
  labels: string[]
  acceptance_criteria: string[]
}

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

  const reordered = [...items.value]
  const [moved] = reordered.splice(fromIdx, 1)
  reordered.splice(toIdx, 0, moved)
  items.value = reordered
  draggedItem.value = null

  try {
    await api.post<unknown>(`/api/llc/companies/${companyId.value}/backlog/reorder`, {
      ordered_ids: reordered.map(i => i.id),
    })
  } catch (err) {
    logger.error('Reorder failed', err)
    await fetchBacklog()
  }
}

async function suggestAC() {
  if (!newItem.value.title) return
  isSuggestingAC.value = true
  try {
    const result = await api.post<{ suggestions: string[] }>(`/api/llc/work-items/suggest-ac`, {
      title: newItem.value.title,
      type: newItem.value.type,
      description: newItem.value.description,
    })
    suggestedACs.value = result.suggestions.map(text => ({ text, selected: true }))
  } catch (err) {
    logger.error('AC suggestion failed', err)
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
  background: var(--color-background);
  color: var(--color-text);
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
  color: var(--color-text-secondary, #6b7280);
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
  border: 1px solid var(--color-border, #d1d5db);
  border-radius: 0.375rem;
  background: var(--color-surface, #fff);
  color: var(--color-text);
  font-size: 0.875rem;
}

.filter-search {
  flex: 1;
  min-width: 200px;
}

.backlog-table-wrapper {
  flex: 1;
  overflow: auto;
  border: 1px solid var(--color-border, #e5e7eb);
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
  background: var(--color-surface-elevated, #f9fafb);
  border-bottom: 1px solid var(--color-border, #e5e7eb);
  white-space: nowrap;
}

.backlog-row {
  border-bottom: 1px solid var(--color-border, #f3f4f6);
  cursor: pointer;
  transition: background 0.1s;
}

.backlog-row:hover {
  background: var(--color-surface-hover, #f9fafb);
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
  color: var(--color-text-secondary, #6b7280);
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
  color: var(--color-text-secondary, #9ca3af);
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
  background: var(--color-surface, #fff);
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
  color: var(--color-text-secondary, #6b7280);
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
  border: 1px solid var(--color-border, #d1d5db);
  border-radius: 0.375rem;
  background: var(--color-surface, #fff);
  color: var(--color-text);
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
  color: var(--color-text-secondary, #6b7280);
}

.btn-suggest {
  font-size: 0.8rem;
  padding: 0.25rem 0.75rem;
  border: 1px solid var(--color-border, #d1d5db);
  border-radius: 0.375rem;
  background: var(--color-surface-elevated, #f9fafb);
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
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: 0.375rem;
  background: var(--color-surface-elevated, #f9fafb);
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
  background: var(--color-surface, #fff);
  color: var(--color-text);
  border: 1px solid var(--color-border, #d1d5db);
  border-radius: 0.375rem;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
}

.btn-secondary:hover {
  background: var(--color-surface-hover, #f9fafb);
}

.btn-icon {
  width: 1rem;
  height: 1rem;
}
</style>
