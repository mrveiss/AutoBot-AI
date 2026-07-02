<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025-2026 mrveiss -->
<!-- Author: mrveiss -->
<!--
  ProjectBrowserView (GH#9628) — leaf tier of the LLC work hierarchy.
  Lists the projects under a program as a card grid. Each card links out to
  the company-scoped Backlog and Timeline views. A header "Create" action opens
  a modal that POSTs a new project and prepends it to the list (#10750 B1).
-->
<template>
  <div class="llc-browser">
    <LlcBreadcrumb :items="breadcrumb" />

    <header class="browser-header">
      <div class="browser-heading">
        <h2 class="browser-title">{{ t('llcBrowser.projects.title') }}</h2>
        <span class="browser-count">
          {{ t('llcBrowser.projects.count', { count: projects.length }) }}
        </span>
      </div>
      <BaseButton variant="primary" :disabled="!programId" @click="openCreate">
        {{ t('llcBrowser.projects.create') }}
      </BaseButton>
    </header>

    <div v-if="loading" class="browser-state">{{ t('llcBrowser.projects.loading') }}</div>

    <template v-else-if="loadError">
      <ErrorBanner :message="t('llcBrowser.projects.loadError')" class="browser-error" />
      <BaseButton variant="secondary" size="sm" @click="loadProjects">
        {{ t('llcBrowser.retry') }}
      </BaseButton>
    </template>

    <div v-else-if="!projects.length" class="browser-state">
      {{ t('llcBrowser.projects.empty') }}
    </div>

    <div v-else class="card-grid">
      <article v-for="p in projects" :key="p.id" class="entity-card">
        <div class="card-top">
          <h3 class="card-name">{{ p.name }}</h3>
          <span class="status-badge" :class="`status-${p.status}`">{{ p.status }}</span>
        </div>
        <p v-if="p.description" class="card-desc">{{ p.description }}</p>
        <div class="card-stats">
          <span class="stat">{{ t('llcBrowser.openCount', { count: p.open_work_item_count }) }}</span>
          <span class="stat">{{ p.active_sprint_name || t('llcBrowser.noActiveSprint') }}</span>
        </div>
        <div v-if="velocityFor(p.id).length >= 2" class="card-velocity">
          <span class="velocity-label">{{ t('llcBrowser.velocity') }}</span>
          <Sparkline :points="velocityFor(p.id)" :aria-label="t('llcBrowser.velocityAria', { name: p.name })" />
        </div>
        <p class="card-meta">{{ t('llcBrowser.target', { date: formatDate(p.target_date) }) }}</p>
        <div class="card-actions">
          <RouterLink class="action-link" :to="`/llc/companies/${companyId}/backlog`">
            {{ t('llcBrowser.backlogLink') }}
          </RouterLink>
          <RouterLink class="action-link" :to="`/llc/companies/${companyId}/timeline`">
            {{ t('llcBrowser.timelineLink') }}
          </RouterLink>
        </div>
      </article>
    </div>

    <BaseModal
      v-model="showCreate"
      :title="t('llcBrowser.projects.createTitle')"
      size="sm"
    >
      <ErrorBanner v-if="createError" :message="createError" class="browser-error" />
      <div class="create-form">
        <BaseInput
          v-model="form.name"
          :label="t('llcBrowser.nameLabel')"
          :placeholder="t('llcBrowser.namePlaceholder')"
          required
        />
        <div class="create-field">
          <label class="create-label" for="project-description">
            {{ t('llcBrowser.descriptionLabel') }}
          </label>
          <textarea
            id="project-description"
            v-model="form.description"
            class="create-textarea"
            rows="3"
            :placeholder="t('llcBrowser.descriptionPlaceholder')"
          />
        </div>
      </div>
      <template #actions>
        <BaseButton variant="secondary" :disabled="creating" @click="showCreate = false">
          {{ t('llcBrowser.cancel') }}
        </BaseButton>
        <BaseButton
          variant="primary"
          :loading="creating"
          :disabled="!form.name.trim() || creating"
          @click="createProject"
        >
          {{ t('llcBrowser.createAction') }}
        </BaseButton>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import LlcBreadcrumb, { type BreadcrumbItem } from '@/components/llc/LlcBreadcrumb.vue'
import Sparkline from '@/components/llc/Sparkline.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import ErrorBanner from '@/components/base/ErrorBanner.vue'

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
const { t } = useI18n()

const companyId = computed(() => route.params.companyId as string)
const programId = computed(() => route.params.programId as string)
const projects = ref<ProjectResponse[]>([])
const loading = ref(false)
const loadError = ref(false)
// project id → chronological velocity series (oldest→newest) for the sparkline.
const velocities = ref<Record<string, number[]>>({})

const showCreate = ref(false)
const creating = ref(false)
const createError = ref('')
const form = ref({ name: '', description: '' })

function velocityFor(projectId: string): number[] {
  return velocities.value[projectId] ?? []
}

const breadcrumb = computed<BreadcrumbItem[]>(() => [
  {
    label: t('llcBrowser.portfolios.title'),
    to: { name: 'llc-portfolios', params: { companyId: companyId.value } },
  },
  { label: t('llcBrowser.programs.title') },
  { label: t('llcBrowser.projects.title') },
])

function formatDate(value: string | null): string {
  if (!value) return '—'
  const ms = Date.parse(value)
  if (Number.isNaN(ms)) return '—'
  return new Date(ms).toLocaleDateString()
}

async function loadProjects(): Promise<void> {
  loading.value = true
  loadError.value = false
  try {
    projects.value = await api.get<ProjectResponse[]>(
      `/api/llc/programs/${programId.value}/projects`,
    )
    void loadVelocities()
  } catch (err) {
    logger.error('Failed to load projects', err)
    loadError.value = true
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

function openCreate(): void {
  form.value = { name: '', description: '' }
  createError.value = ''
  showCreate.value = true
}

async function createProject(): Promise<void> {
  const name = form.value.name.trim()
  if (!name || !programId.value) return
  creating.value = true
  createError.value = ''
  try {
    // ProjectCreate: company_id (required) + name + optional description; the
    // server derives the true tenant from the parent program (#10261).
    const created = await api.post<ProjectResponse>(
      `/api/llc/programs/${programId.value}/projects`,
      {
        company_id: companyId.value,
        name,
        description: form.value.description.trim() || undefined,
      },
    )
    projects.value.unshift(created)
    showCreate.value = false
  } catch (err) {
    logger.error('Failed to create project', err)
    createError.value = t('llcBrowser.projects.createError')
  } finally {
    creating.value = false
  }
}

onMounted(loadProjects)
</script>

<style scoped>
.llc-browser {
  padding: 1.5rem;
}

.browser-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.browser-heading {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
}

.browser-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.browser-count {
  font-size: 0.875rem;
  color: var(--text-secondary);
}

.browser-state {
  padding: 2rem 0;
  color: var(--text-secondary);
}

.browser-error {
  margin-bottom: 0.75rem;
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
  border: 1px solid var(--border-default);
  background: var(--bg-surface);
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
  color: var(--text-primary);
  margin: 0;
}

.card-desc {
  font-size: 0.875rem;
  color: var(--text-secondary);
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-meta {
  font-size: 0.75rem;
  color: var(--text-secondary);
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
  color: var(--text-secondary);
  background: var(--bg-hover);
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
  color: var(--text-secondary);
}

.status-badge {
  flex: none;
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  padding: 0.125rem 0.5rem;
  border-radius: 999px;
  background: var(--bg-hover);
  color: var(--text-secondary);
}

.card-actions {
  display: flex;
  gap: 0.75rem;
  margin-top: 0.25rem;
  padding-top: 0.5rem;
  border-top: 1px solid var(--border-default);
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

.create-form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.create-field {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.create-label {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--text-secondary);
}

.create-textarea {
  width: 100%;
  padding: 0.5rem 0.75rem;
  border-radius: var(--radius-md, 8px);
  border: 1px solid var(--border-default);
  background: var(--bg-surface);
  color: var(--text-primary);
  font-size: 0.875rem;
  resize: vertical;
}
</style>
