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
        <option v-for="wt in WORK_ITEM_TYPES" :key="wt.value" :value="wt.value">{{ t(wt.labelKey) }}</option>
      </select>
      <select v-model="filters.status" class="filter-select">
        <option value="">{{ t('llc.backlog.allStatuses') }}</option>
        <option value="backlog">{{ t('llc.backlog.statusBacklog') }}</option>
        <option value="ready">{{ t('llc.backlog.statusReady') }}</option>
      </select>
      <select v-model="filters.priority" class="filter-select">
        <option value="">{{ t('llc.backlog.allPriorities') }}</option>
        <option v-for="p in PRIORITIES" :key="p.value" :value="p.value">{{ t(p.labelKey) }}</option>
      </select>
      <input
        v-model="filters.search"
        class="filter-search"
        :placeholder="t('llc.backlog.searchPlaceholder')"
        type="text"
      />
    </div>

    <BacklogHierarchyPanel :company-id="companyId" />

    <BaseAlert v-if="loadFailed" variant="error" :message="t('llc.backlog.fetchFailed')">
      <template #actions>
        <BaseButton size="sm" variant="secondary" data-testid="retry-load" @click="fetchBacklog">{{ t('common.retry') }}</BaseButton>
      </template>
    </BaseAlert>

    <BaseAlert v-if="createdRefreshFailed" variant="warning" :message="t('llc.backlog.createdRefreshFailed')">
      <template #actions>
        <BaseButton size="sm" variant="secondary" data-testid="retry-refresh" @click="onItemCreated">{{ t('common.retry') }}</BaseButton>
      </template>
    </BaseAlert>

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
          <tr v-if="filteredItems.length === 0 && !isLoading && !loadFailed">
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
      :projects-failed="projectsFailed"
      :default-project-id="projectFilterId"
      @close="showCreateForm = false"
      @retry-projects="loadProjects"
      @created="onItemCreated"
    />

    <BacklogBulkAssignModal
      :model-value="showBulkAssign"
      :company-id="companyId"
      :work-item-ids="Array.from(selectedIds)"
      :projects="projects"
      :loading-projects="isLoadingProjects"
      @close="showBulkAssign = false"
      @assigned="onBulkAssigned"
    />

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
import { useAssignableProjects } from '@/composables/llc/useAssignableProjects'
import { useBacklogItems } from '@/composables/llc/useBacklogItems'
import { createLogger } from '@/utils/debugUtils'
import WorkItemDetail from './WorkItemDetail.vue'
import WorkItemBadge from '@/components/llc/WorkItemBadge.vue'
import BacklogCreateModal from '@/components/llc/BacklogCreateModal.vue'
import BacklogBulkAssignModal from '@/components/llc/BacklogBulkAssignModal.vue'
import BacklogHierarchyPanel from '@/components/llc/BacklogHierarchyPanel.vue'
import { BaseAlert, BaseAvatar, BaseButton } from '@autobot/ui'

const logger = createLogger('BacklogView')
const api = useApiClient()
const route = useRoute()
const { t } = useI18n()

const companyId = computed(() => route.params.companyId as string)

import { WORK_ITEM_TYPES, PRIORITIES, type WorkItem } from './workItemTypes'

const detailItem = ref<WorkItem | null>(null)
const selectedIds = ref<Set<string>>(new Set())
const draggedItem = ref<WorkItem | null>(null)

const filters = ref({ type: '', status: '', priority: '', search: '' })

// #17680: applied by the server, so kept out of `filters` (those are client-side): a client-side project
// filter would narrow an already-truncated 50-row page to an arbitrary subset.
const projectFilterId = ref('')

const showCreateForm = ref(false)
const createdRefreshFailed = ref(false) // a create worked, the list refresh after it did not (#20930)

const showBulkAssign = ref(false)

const { projects, isLoadingProjects, projectsFailed, loadProjects } = useAssignableProjects(companyId)
const { items, isLoading, loadFailed, fetchBacklog } = useBacklogItems(companyId, projectFilterId)

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
  if (projects.value.length === 0 && !isLoadingProjects.value) loadProjects()
}

// Refetched, not prepended: the form can pick any project and the list is filtered by the server.
// Also the Retry of a failed refresh: the form is already closed then. A refresh a newer request superseded
// answers true (see useBacklogItems), so an earlier one can never set the warning over a newer outcome (#21032).
async function onItemCreated() {
  showCreateForm.value = false
  createdRefreshFailed.value = !(await fetchBacklog())
}

function openBulkAssign() {
  showBulkAssign.value = true
  if (projects.value.length === 0) loadProjects()
}

function onBulkAssigned() {
  selectedIds.value = new Set()
  showBulkAssign.value = false
  fetchBacklog()
}

// Server-side filter, so a change is a refetch rather than a recompute.
watch(projectFilterId, () => {
  selectedIds.value = new Set()
  fetchBacklog()
})

// Another company has other projects, sprints and items: nothing chosen for the last one may carry over (#20930).
watch(companyId, () => {
  const refetchedByFilter = projectFilterId.value !== ''
  selectedIds.value = new Set()
  projectFilterId.value = ''
  createdRefreshFailed.value = false
  if (!refetchedByFilter) fetchBacklog()
})

onMounted(() => {
  fetchBacklog()
  // The project filter needs the project list on load.
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
