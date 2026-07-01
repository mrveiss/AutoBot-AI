<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025-2026 mrveiss -->
<!-- Author: mrveiss -->
<!--
  BoardsView (GH#10219) — lists a company's Kanban and Sprint boards as a card
  grid, giving the previously-orphaned board views a navigation entry point.
  Clicking a card opens the corresponding Kanban or Sprint board.
-->
<template>
  <div class="llc-browser">
    <header class="browser-header">
      <h2 class="browser-title">Boards</h2>
      <span class="browser-count">{{ boards.length }} boards</span>
    </header>

    <div v-if="loading" class="browser-state">Loading boards…</div>
    <div v-else-if="!boards.length" class="browser-state">
      No boards yet — boards are created per project (Kanban) and per sprint (Sprint).
    </div>

    <div v-else class="card-grid">
      <button v-for="b in boards" :key="b.id" type="button" class="entity-card" @click="openBoard(b)">
        <div class="card-top">
          <h3 class="card-name">{{ b.name }}</h3>
          <span class="status-badge" :class="`type-${b.type}`">{{ b.type }}</span>
        </div>
        <p class="card-meta">Created {{ formatDate(b.created_at) }}</p>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'

interface BoardSummary {
  id: string
  company_id: string
  project_id: string | null
  sprint_id: string | null
  type: 'kanban' | 'sprint'
  name: string
  created_at: string
  updated_at: string
}

const logger = createLogger('BoardsView')
const api = useApiClient()
const route = useRoute()
const router = useRouter()

const companyId = computed(() => route.params.companyId as string)
const boards = ref<BoardSummary[]>([])
const loading = ref(false)

function formatDate(value: string): string {
  const ms = Date.parse(value)
  if (Number.isNaN(ms)) return '—'
  return new Date(ms).toLocaleDateString()
}

async function loadBoards(): Promise<void> {
  loading.value = true
  try {
    boards.value = await api.get<BoardSummary[]>('/api/llc/boards')
  } catch (err) {
    logger.error('Failed to load boards', err)
    boards.value = []
  } finally {
    loading.value = false
  }
}

function openBoard(b: BoardSummary): void {
  const name = b.type === 'sprint' ? 'llc-sprint-board' : 'llc-kanban-board'
  router.push({ name, params: { companyId: companyId.value, boardId: b.id } })
}

onMounted(loadBoards)
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

.browser-state {
  padding: 2rem 0;
  color: var(--text-secondary, #9ca3af);
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
</style>
