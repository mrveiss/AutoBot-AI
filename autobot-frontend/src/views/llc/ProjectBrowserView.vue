<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025-2026 mrveiss -->
<!-- Author: mrveiss -->
<!--
  ProjectBrowserView (GH#9628) — leaf tier of the LLC work hierarchy.
  Lists the projects under a program as a card grid. Each card links out to
  the company-scoped Backlog and Timeline views.
-->
<template>
  <div class="llc-browser">
    <LlcBreadcrumb :items="breadcrumb" />

    <header class="browser-header">
      <h2 class="browser-title">Projects</h2>
      <span class="browser-count">{{ projects.length }} projects</span>
    </header>

    <div v-if="loading" class="browser-state">Loading projects…</div>
    <div v-else-if="!projects.length" class="browser-state">No projects yet.</div>

    <div v-else class="card-grid">
      <article v-for="p in projects" :key="p.id" class="entity-card">
        <div class="card-top">
          <h3 class="card-name">{{ p.name }}</h3>
          <span class="status-badge" :class="`status-${p.status}`">{{ p.status }}</span>
        </div>
        <p v-if="p.description" class="card-desc">{{ p.description }}</p>
        <div class="card-stats">
          <span class="stat">{{ p.open_work_item_count }} open</span>
          <span class="stat">{{ p.active_sprint_name || 'No active sprint' }}</span>
        </div>
        <div v-if="velocityFor(p.id).length >= 2" class="card-velocity">
          <span class="velocity-label">Velocity</span>
          <Sparkline :points="velocityFor(p.id)" :aria-label="`Velocity for ${p.name}`" />
        </div>
        <p class="card-meta">Target {{ formatDate(p.target_date) }}</p>
        <div class="card-actions">
          <RouterLink class="action-link" :to="`/llc/companies/${companyId}/backlog`">
            Backlog
          </RouterLink>
          <RouterLink class="action-link" :to="`/llc/companies/${companyId}/timeline`">
            Timeline
          </RouterLink>
        </div>
      </article>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import LlcBreadcrumb, { type BreadcrumbItem } from '@/components/llc/LlcBreadcrumb.vue'
import Sparkline from '@/components/llc/Sparkline.vue'

interface ProjectResponse {
  id: string
  company_id: string
  program_id: string
  goal_id: string | null
  name: string
  description: string | null
  status: string
  lead_agent_id: string | null
  lead_user_id: string | null
  target_date: string | null
  auto_rollover: boolean
  created_at: string
  updated_at: string
  open_work_item_count: number
  active_sprint_name: string | null
}

interface VelocityHistory {
  sprints: { velocity: number }[]
}

const logger = createLogger('ProjectBrowserView')
const api = useApiClient()
const route = useRoute()

const companyId = computed(() => route.params.companyId as string)
const programId = computed(() => route.params.programId as string)
const projects = ref<ProjectResponse[]>([])
const loading = ref(false)
// project id → chronological velocity series (oldest→newest) for the sparkline.
const velocities = ref<Record<string, number[]>>({})

function velocityFor(projectId: string): number[] {
  return velocities.value[projectId] ?? []
}

const breadcrumb = computed<BreadcrumbItem[]>(() => [
  {
    label: 'Portfolios',
    to: { name: 'llc-portfolios', params: { companyId: companyId.value } },
  },
  { label: 'Programs' },
  { label: 'Projects' },
])

function formatDate(value: string | null): string {
  if (!value) return '—'
  const ms = Date.parse(value)
  if (Number.isNaN(ms)) return '—'
  return new Date(ms).toLocaleDateString()
}

async function loadProjects(): Promise<void> {
  loading.value = true
  try {
    projects.value = await api.get<ProjectResponse[]>(
      `/api/llc/programs/${programId.value}/projects`,
    )
    void loadVelocities()
  } catch (err) {
    logger.error('Failed to load projects', err)
    projects.value = []
  } finally {
    loading.value = false
  }
}

// Fetch each project's velocity history in parallel (reuses the #9861 endpoint).
// A single failure must not blank the others, so each fetch is isolated.
async function loadVelocities(): Promise<void> {
  await Promise.all(
    projects.value.map(async p => {
      try {
        const res = await api.get<VelocityHistory>(`/api/llc/projects/${p.id}/velocity`)
        // Endpoint returns most-recent-first; reverse for a left-to-right trend.
        velocities.value[p.id] = (res.sprints ?? []).map(s => s.velocity).reverse()
      } catch (err) {
        logger.error(`Failed to load velocity for project ${p.id}`, err)
      }
    }),
  )
}

onMounted(loadProjects)
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
  border-radius: var(--radius-md, 8px);
  border: 1px solid var(--border-default, #e5e7eb);
  background: var(--bg-surface, #ffffff);
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

.card-desc {
  font-size: 0.875rem;
  color: var(--text-secondary, #9ca3af);
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-meta {
  font-size: 0.75rem;
  color: var(--text-secondary, #9ca3af);
  margin: 0;
}

.card-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.stat {
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--text-secondary, #6b7280);
  background: var(--bg-hover, #f3f4f6);
  padding: 0.125rem 0.5rem;
  border-radius: 999px;
}

.card-velocity {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.velocity-label {
  font-size: 0.6875rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--text-secondary, #9ca3af);
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

.card-actions {
  display: flex;
  gap: 0.75rem;
  margin-top: 0.25rem;
  padding-top: 0.5rem;
  border-top: 1px solid var(--border-default, #e5e7eb);
}

.action-link {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--color-accent-text, var(--color-accent, #c4651a));
  text-decoration: none;
}

.action-link:hover {
  text-decoration: underline;
}
</style>
