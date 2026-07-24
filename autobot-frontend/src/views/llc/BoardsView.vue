<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025-2026 mrveiss -->
<!-- Author: mrveiss -->
<!--
  BoardsView (GH#10219) — lists a company's Kanban and Sprint boards as a card
  grid, giving the previously-orphaned board views a navigation entry point.
  Clicking a card opens the corresponding Kanban or Sprint board.

  GH#12213 — adds the "New Kanban Board" flow: the board *create* endpoints
  (POST /api/llc/boards/kanban) had no frontend caller, so a company with no
  boards could never make one. A project picker now creates (get-or-create) a
  kanban board and opens it.
-->
<template>
  <div class="llc-browser">
    <header class="browser-header">
      <h2 class="browser-title">{{ $t('llc.boards.title') }}</h2>
      <span class="browser-count">{{ $t('llc.boards.count', { count: boards.length }) }}</span>
      <button type="button" class="btn btn-primary new-board-btn" @click="openCreate">
        {{ $t('llc.boards.newKanban') }}
      </button>
    </header>

    <div v-if="isLoading" class="browser-state">{{ $t('llc.boards.loading') }}</div>
    <div v-else-if="!boards.length" class="browser-state">
      <p class="empty-text">{{ $t('llc.boards.empty') }}</p>
      <button type="button" class="btn btn-primary" @click="openCreate">
        {{ $t('llc.boards.newKanban') }}
      </button>
    </div>

    <div v-else class="card-grid">
      <button v-for="b in boards" :key="b.id" type="button" class="entity-card" @click="openBoard(b)">
        <div class="card-top">
          <h3 class="card-name">{{ b.name }}</h3>
          <span class="status-badge" :class="`type-${b.type}`">{{ b.type }}</span>
        </div>
        <p class="card-meta">{{ $t('llc.boards.created', { date: formatDate(b.created_at) }) }}</p>
      </button>
    </div>

    <BaseModal
      v-if="showCreate"
      :close-label="$t('ui.modal.closeDialog')"
      :model-value="true"
      :title="$t('llc.boards.createTitle')"
      size="sm"
      @close="closeCreate"
    >
      <form class="create-form" @submit.prevent="submitCreate">
        <label class="field">
          <span class="field-label">{{ $t('llc.boards.project') }}</span>
          <select v-model="selectedProjectId" class="field-input" :disabled="projectsLoading">
            <option value="" disabled>
              {{ projectsLoading ? $t('llc.boards.loadingProjects') : $t('llc.boards.selectProject') }}
            </option>
            <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </label>
        <p v-if="!projectsLoading && !projects.length" class="form-hint">
          {{ $t('llc.boards.noProjects') }}
        </p>
        <p v-if="createError" class="form-error">{{ createError }}</p>
      </form>

      <template #actions>
        <button type="button" class="btn btn-ghost" @click="closeCreate">
          {{ $t('common.cancel') }}
        </button>
        <button
          type="button"
          class="btn btn-primary"
          :disabled="creating || !selectedProjectId"
          @click="submitCreate"
        >
          {{ creating ? $t('llc.boards.creating') : $t('llc.boards.create') }}
        </button>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { BaseModal } from '@autobot/ui'
import { useApiClient } from '@/plugins/api'
import { useKanbanBoardsApi, type BoardSummary } from '@/composables/llc/useKanbanBoardsApi'
import { createLogger } from '@/utils/debugUtils'
import { formatDate as fmtDate } from '@/utils/formatHelpers'

interface ProjectOption {
  id: string
  name: string
}

const logger = createLogger('BoardsView')
const api = useApiClient()
const route = useRoute()
const router = useRouter()
const { boards, isLoading, listBoards, createKanbanBoard } = useKanbanBoardsApi()

const companyId = computed(() => route.params.companyId as string)

const showCreate = ref(false)
const projects = ref<ProjectOption[]>([])
const projectsLoading = ref(false)
const selectedProjectId = ref('')
const creating = ref(false)
const createError = ref('')

function formatDate(value: string): string {
  return fmtDate(value) || '—'
}

function openBoard(b: BoardSummary): void {
  const name = b.type === 'sprint' ? 'llc-sprint-board' : 'llc-kanban-board'
  router.push({ name, params: { companyId: companyId.value, boardId: b.id } })
}

async function loadProjects(): Promise<void> {
  projectsLoading.value = true
  try {
    projects.value = await api.get<ProjectOption[]>(
      `/api/llc/companies/${companyId.value}/projects`,
    )
  } catch (err) {
    logger.error('Failed to load projects', err)
    projects.value = []
  } finally {
    projectsLoading.value = false
  }
}

function openCreate(): void {
  showCreate.value = true
  createError.value = ''
  selectedProjectId.value = ''
  void loadProjects()
}

function closeCreate(): void {
  showCreate.value = false
}

async function submitCreate(): Promise<void> {
  if (!selectedProjectId.value || creating.value) return
  creating.value = true
  createError.value = ''
  try {
    const board = await createKanbanBoard(companyId.value, selectedProjectId.value)
    showCreate.value = false
    router.push({
      name: 'llc-kanban-board',
      params: { companyId: companyId.value, boardId: board.id },
    })
  } catch (err: unknown) {
    createError.value = (err instanceof Error && err.message) || 'Failed to create board.'
    logger.error('Failed to create kanban board', err)
  } finally {
    creating.value = false
  }
}

onMounted(listBoards)
</script>

<style scoped>
.llc-browser {
  padding: 1.5rem;
}

.browser-header {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.browser-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary, #111827);
  margin: 0;
}

.browser-count {
  font-size: 0.875rem;
  color: var(--text-secondary, #9ca3af);
}

.new-board-btn {
  margin-left: auto;
}

.browser-state {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 2rem 0;
  color: var(--text-secondary, #9ca3af);
}

.empty-text {
  margin: 0;
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(16rem, 1fr));
  gap: 1rem;
}

.entity-card {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 1rem;
  text-align: left;
  cursor: pointer;
  border-radius: var(--radius-md, 8px);
  border: 1px solid var(--border-default, #e5e7eb);
  background: var(--bg-surface, #ffffff);
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.entity-card:hover {
  border-color: var(--color-accent, #c4651a);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}

.card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.5rem;
}

.card-name {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary, #111827);
  margin: 0;
}

.card-meta {
  font-size: 0.75rem;
  color: var(--text-secondary, #9ca3af);
  margin: 0;
}

.status-badge {
  flex: none;
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  padding: 0.125rem 0.5rem;
  border-radius: 999px;
  background: var(--bg-hover, #f3f4f6);
  color: var(--text-secondary, #6b7280);
}

.type-kanban {
  background: #bfdbfe;
  color: #1d4ed8;
}

.type-sprint {
  background: #ddd6fe;
  color: #5b21b6;
}

.create-form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.field-label {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--text-secondary, #6b7280);
}

.field-input {
  padding: 0.4rem 0.5rem;
  border-radius: var(--radius-sm, 6px);
  border: 1px solid var(--border-default, #d1d5db);
  background: var(--bg-surface, #fff);
  color: var(--text-primary, #111827);
}

.form-hint {
  margin: 0;
  font-size: 0.8rem;
  color: var(--text-secondary, #6b7280);
}

.form-error {
  margin: 0;
  font-size: 0.8rem;
  color: var(--color-error, #dc2626);
}

.btn {
  padding: 0.45rem 0.9rem;
  border-radius: var(--radius-sm, 6px);
  font-size: 0.85rem;
  cursor: pointer;
  border: 1px solid transparent;
}

.btn-ghost {
  background: transparent;
  border-color: var(--border-default, #d1d5db);
  color: var(--text-secondary, #6b7280);
}

.btn-primary {
  background: var(--color-accent, #c4651a);
  color: #fff;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
