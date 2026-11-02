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
        <button class="btn-primary" @click="openCreateForm">
          <svg class="btn-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
          </svg>
          {{ t('llc.backlog.createWorkItem') }}
        </button>
        <button
          v-if="selectedIds.size > 0"
          class="btn-secondary"
          @click="openBulkAssign"
        >
          {{ t('llc.backlog.assignSprint', { count: selectedIds.size }) }}
        </button>
      </div>
    </div>

    <!-- Filters -->
    <div class="backlog-filters">
      <!-- #17680: a project filter, served by the API's own `project_id` -->
      <select v-model="projectFilterId" class="filter-select" :disabled="isLoadingProjects">
        <option value="">{{ t('llc.backlog.allProjects') }}</option>
        <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
      </select>
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
              <WorkItemBadge kind="type" :value="item.type" />
            </td>
            <td class="col-title">{{ item.title }}</td>
            <td class="col-priority">
              <WorkItemBadge kind="priority" :value="item.priority" />
            </td>
            <td class="col-points">{{ item.story_points ?? '—' }}</td>
            <td class="col-assignee">
              <BaseAvatar v-if="item.assignee_name" :name="item.assignee_name" size="sm" variant="primary" />
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

    <BacklogCreateModal
      :model-value="showCreateForm"
      :company-id="companyId"
      :projects="projects"
      :loading-projects="isLoadingProjects"
      :default-project-id="projectFilterId"
      @close="showCreateForm = false"
      @created="onItemCreated"
    />

    <!-- Bulk sprint assign drawer -->
    <BaseModal
      :model-value="showBulkAssign"
      :title="t('llc.backlog.assignToSprint')"
      :close-label="t('ui.modal.closeDialog')"
      :width="560"
      @close="showBulkAssign = false"
    >
      <div class="modal-form-body">
        <p>{{ t('llc.backlog.itemsSelected', { count: selectedIds.size }) }}</p>
        <div class="form-field">
          <label>{{ t('llc.backlog.project') }}</label>
          <select class="form-input" :value="selectedProjectId" :disabled="isLoadingProjects"
                  @change="onProjectSelect(($event.target as HTMLSelectElement).value)">
            <option value="">{{ isLoadingProjects ? t('llc.backlog.loadingProjects') : t('llc.backlog.selectProject') }}</option>
            <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </div>
        <div class="form-field">
          <label>{{ t('llc.backlog.sprint') }}</label>
          <select v-model="bulkSprintId" class="form-input" :disabled="!selectedProjectId || isLoadingSprints">
            <option value="">{{ isLoadingSprints ? t('llc.backlog.loadingSprints') : t('llc.backlog.selectSprint') }}</option>
            <option v-for="s in sprints" :key="s.id" :value="s.id">{{ s.name }}</option>
          </select>
          <p v-if="selectedProjectId && !isLoadingSprints && sprints.length === 0" class="form-hint">
            {{ t('llc.backlog.noSprints') }}
          </p>
        </div>
      </div>

      <template #actions>
        <button class="btn-secondary" @click="showBulkAssign = false">{{ t('common.cancel') }}</button>
        <button class="btn-primary" :disabled="!bulkSprintId || isBulkAssigning" @click="bulkAssign">
          {{ isBulkAssigning ? t('llc.backlog.assigning') : t('llc.backlog.assign') }}
        </button>
      </template>
    </BaseModal>

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
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import WorkItemDetail from './WorkItemDetail.vue'
import WorkItemBadge from '@/components/llc/WorkItemBadge.vue'
import BacklogCreateModal from '@/components/llc/BacklogCreateModal.vue'
import { BaseAvatar, BaseModal } from '@autobot/ui'

const logger = createLogger('BacklogView')
const api = useApiClient()
const route = useRoute()
const { t } = useI18n()

const companyId = computed(() => route.params.companyId as string)

import { WORK_ITEM_TYPES, PRIORITIES, type WorkItem } from './workItemTypes'

const items = ref<WorkItem[]>([])
const isLoading = ref(false)
const detailItem = ref<WorkItem | null>(null)
const selectedIds = ref<Set<string>>(new Set())
const draggedItem = ref<WorkItem | null>(null)

const filters = ref({ type: '', status: '', priority: '', search: '' })

// #17680: kept out of `filters` on purpose -- everything in there is applied
// client-side by `filteredItems`, and this one is applied by the server. A
// project filter cannot be client-side: the route pages at `limit=50`, so
// narrowing an already-truncated page returns an arbitrary subset of the
// project rather than the project.
const projectFilterId = ref('')

const showCreateForm = ref(false)

const showBulkAssign = ref(false)
const isBulkAssigning = ref(false)
const bulkSprintId = ref('')

interface ProjectOpt { id: string; name: string; lifecycle_state: string }
interface SprintOpt { id: string; name: string; status: string }

const projects = ref<ProjectOpt[]>([])
const sprints = ref<SprintOpt[]>([])
const selectedProjectId = ref('')
const isLoadingProjects = ref(false)
const isLoadingSprints = ref(false)

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

function openCreateForm() {
  showCreateForm.value = true
  if (projects.value.length === 0) loadProjects()
}

function onItemCreated(item: WorkItem) {
  items.value.unshift(item)
  showCreateForm.value = false
}

// Cascade picker for bulk sprint assignment: pick a Project, then a Sprint from
// that project. Only assignable (non-archived) projects and (open) sprints are
// offered so a user never needs to paste a raw Sprint UUID (#10853).
async function loadProjects() {
  isLoadingProjects.value = true
  try {
    const result = await api.get<ProjectOpt[]>(`/api/llc/companies/${companyId.value}/projects`)
    projects.value = (result ?? []).filter(
      p => p.lifecycle_state !== 'archived' && p.lifecycle_state !== 'disposed',
    )
  } catch (err) {
    logger.error('Failed to load projects', err)
  } finally {
    isLoadingProjects.value = false
  }
}

async function onProjectSelect(projectId: string) {
  selectedProjectId.value = projectId
  bulkSprintId.value = ''
  sprints.value = []
  if (!projectId) return
  isLoadingSprints.value = true
  try {
    const result = await api.get<SprintOpt[]>(`/api/llc/projects/${projectId}/sprints`)
    sprints.value = (result ?? []).filter(
      sp => sp.status !== 'closed' && sp.status !== 'archived',
    )
  } catch (err) {
    logger.error('Failed to load sprints', err)
  } finally {
    isLoadingSprints.value = false
  }
}

function openBulkAssign() {
  showBulkAssign.value = true
  selectedProjectId.value = ''
  sprints.value = []
  bulkSprintId.value = ''
  if (projects.value.length === 0) loadProjects()
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
    // #17680: `GET /api/llc/backlog` has accepted and honoured `project_id`
    // since it was written, and this was its only caller -- sending
    // `company_id` alone. So "the project backlog" was always the whole
    // company's backlog, for every project.
    const query = new URLSearchParams({ company_id: companyId.value })
    if (projectFilterId.value) query.set('project_id', projectFilterId.value)
    const result = await api.get<{ items: WorkItem[] }>(`/api/llc/backlog?${query.toString()}`)
    items.value = result.items ?? []
  } catch (err) {
    logger.error('Failed to load backlog', err)
  } finally {
    isLoading.value = false
  }
}

// Server-side filter, so a change is a refetch rather than a recompute.
watch(projectFilterId, () => {
  selectedIds.value = new Set()
  fetchBacklog()
})

onMounted(() => {
  fetchBacklog()
  // The filter needs the project list on load; the bulk-assign modal used to
  // be the only thing that fetched it, so it arrived only after opening that.
  loadProjects()
})
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
  font-size: var(--text-2xl);
  font-weight: 600;
  margin: 0;
}

.item-count {
  font-size: var(--text-sm);
  color: var(--text-secondary);
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
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
  background: var(--bg-surface);
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.filter-search {
  flex: 1;
  min-width: 200px;
}

.backlog-table-wrapper {
  flex: 1;
  overflow: auto;
  border: 1px solid var(--border-default);
  border-radius: 0.5rem;
}

.backlog-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);
}

.backlog-table th {
  padding: 0.625rem 0.75rem;
  text-align: left;
  font-weight: 600;
  background: var(--bg-elevated);
  border-bottom: 1px solid var(--border-default);
  white-space: nowrap;
}

.backlog-row {
  border-bottom: 1px solid var(--border-default);
  cursor: pointer;
  transition: background 0.1s;
}

.backlog-row:hover {
  background: var(--bg-hover);
}

.backlog-row.selected {
  background: var(--color-primary-subtle, var(--backlogview-selected-row-bg));
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
  color: var(--text-secondary);
}


.sprint-tag {
  font-size: var(--text-xs);
  padding: 0.125rem 0.5rem;
  background: var(--backlogview-sprint-tag-bg);
  color: var(--backlogview-sprint-tag-text);
  border-radius: 0.25rem;
}

.empty-state,
.loading-state {
  text-align: center;
  padding: 2rem;
  color: var(--text-secondary);
}

/* #10882: overlay/panel/header/footer chrome now provided by @autobot/ui
   BaseModal; only the body field stack keeps its 1rem gap here. */
.modal-form-body {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.form-field label {
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--text-secondary);
}

.form-input {
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
  background: var(--bg-surface);
  color: var(--text-primary);
  font-size: var(--text-sm);
  width: 100%;
}

.form-hint {
  margin: 0.25rem 0 0;
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.5rem 1rem;
  background: var(--color-primary);
  color: white;
  border: none;
  border-radius: 0.375rem;
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
}

.btn-primary:hover:not(:disabled) {
  background: var(--color-primary-hover);
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
  background: var(--bg-surface);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
}

.btn-secondary:hover {
  background: var(--bg-hover);
}

.btn-icon {
  width: 1rem;
  height: 1rem;
}
</style>
