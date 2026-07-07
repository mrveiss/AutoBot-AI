<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025-2026 mrveiss -->
<!-- Author: mrveiss -->
<!--
  ProjectBrowserView (GH#9628) — leaf tier of the LLC work hierarchy.
  Lists the projects under a program as a card grid. Each card links out to
  the company-scoped Backlog and Timeline views. A header "Create" action opens
  a modal that POSTs a new project and prepends it to the list (#10750 B1).
  GH#11129: repo linkage UI — Attach / Sync / Detach a GitHub repo per project.
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

        <!-- GH#11129: repo linkage section -->
        <div v-if="p.code_source" class="card-repo">
          <div class="repo-row">
            <span class="repo-label">{{ t('llcBrowser.repo.linkedLabel') }}</span>
            <a
              :href="`https://github.com/${p.code_source.repo}`"
              target="_blank"
              rel="noopener noreferrer"
              class="repo-link"
            >{{ p.code_source.repo }}</a>
          </div>
          <div class="repo-row">
            <span class="repo-label">{{ t('llcBrowser.repo.clonePath') }}</span>
            <code class="repo-path">{{ p.code_source.clone_path }}</code>
            <!-- GH#11129: copy clone_path to clipboard -->
            <button
              v-if="p.code_source.clone_path"
              class="clone-copy-btn"
              :aria-label="t('llcBrowser.repo.copyClonePath')"
              @click="copyClonePath(p.code_source.clone_path)"
            >
              <Icon name="copy" />
            </button>
          </div>
          <div class="repo-row">
            <span class="repo-label">{{ t('llcBrowser.repo.status') }}</span>
            <span class="repo-status" :class="`repo-status-${p.code_source.status}`">
              {{ p.code_source.status }}
            </span>
          </div>
          <div class="repo-actions">
            <BaseButton
              variant="secondary"
              size="sm"
              :loading="syncingRepo === p.id"
              :disabled="syncingRepo === p.id"
              @click="syncRepo(p)"
            >
              {{ t('llcBrowser.repo.syncBtn') }}
            </BaseButton>
            <BaseButton
              variant="secondary"
              size="sm"
              :loading="detachingRepo === p.id"
              :disabled="detachingRepo === p.id"
              @click="detachRepo(p)"
            >
              {{ t('llcBrowser.repo.detachBtn') }}
            </BaseButton>
          </div>
          <ErrorBanner v-if="repoError[p.id]" :message="repoError[p.id]" class="browser-error" />
        </div>
        <div v-else class="card-repo card-repo-empty">
          <BaseButton
            variant="secondary"
            size="sm"
            @click="openAttach(p.id)"
          >
            {{ t('llcBrowser.repo.attachBtn') }}
          </BaseButton>
        </div>

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

    <!-- Create project modal -->
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

    <!-- GH#11129: Attach repo modal -->
    <BaseModal
      v-model="showAttach"
      :title="t('llcBrowser.repo.attachTitle')"
      size="sm"
    >
      <ErrorBanner v-if="attachError" :message="attachError" class="browser-error" />
      <div class="create-form">
        <BaseInput
          v-model="attachForm.repo"
          :label="t('llcBrowser.repo.repoLabel')"
          :placeholder="t('llcBrowser.repo.repoPlaceholder')"
          required
        />
        <BaseInput
          v-model="attachForm.credential_id"
          :label="t('llcBrowser.repo.credentialLabel')"
          :placeholder="t('llcBrowser.repo.credentialPlaceholder')"
        />
      </div>
      <template #actions>
        <BaseButton variant="secondary" :disabled="attaching" @click="showAttach = false">
          {{ t('llcBrowser.cancel') }}
        </BaseButton>
        <BaseButton
          variant="primary"
          :loading="attaching"
          :disabled="!attachForm.repo.trim() || attaching"
          @click="submitAttach"
        >
          {{ t('llcBrowser.repo.submitBtn') }}
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
import { useClipboard } from '@/composables/useClipboard'
import Icon from '@/components/ui/Icon.vue'
import LlcBreadcrumb, { type BreadcrumbItem } from '@/components/llc/LlcBreadcrumb.vue'
import Sparkline from '@/components/llc/Sparkline.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import { BaseModal } from '@autobot/ui'
import ErrorBanner from '@/components/base/ErrorBanner.vue'

// GH#11129: linked code-source summary on a project.
interface CodeSourceSummary {
  id: string
  repo: string | null
  branch: string | null
  clone_path: string | null
  status: string
  error_message: string | null
}

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
  // GH#11129: repo linkage fields (present when backend Task 1-3 is active)
  code_source_id?: string | null
  code_source?: CodeSourceSummary | null
}

interface VelocityHistory {
  sprints: { velocity: number }[]
}

const logger = createLogger('ProjectBrowserView')

// GH#11129: clipboard for clone_path copy button
const { copy: copyToClipboard } = useClipboard()
function copyClonePath(path: string): void {
  void copyToClipboard(path)
}
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

// GH#11129: repo attach/detach/sync state
const showAttach = ref(false)
const attachTargetId = ref<string | null>(null)
const attaching = ref(false)
const attachError = ref('')
const attachForm = ref({ repo: '', credential_id: '' })
const detachingRepo = ref<string | null>(null)
const syncingRepo = ref<string | null>(null)
// per-project error messages (keyed by project id)
const repoError = ref<Record<string, string>>({})

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

// GH#11129: repo linkage actions -------------------------------------------

function openAttach(projectId: string): void {
  attachTargetId.value = projectId
  attachForm.value = { repo: '', credential_id: '' }
  attachError.value = ''
  showAttach.value = true
}

async function submitAttach(): Promise<void> {
  const repo = attachForm.value.repo.trim()
  if (!repo || !attachTargetId.value) return
  attaching.value = true
  attachError.value = ''
  try {
    const updated = await api.post<ProjectResponse>(
      `/api/llc/projects/${attachTargetId.value}/repo`,
      {
        repo,
        credential_id: attachForm.value.credential_id.trim() || null,
      },
    )
    const idx = projects.value.findIndex(p => p.id === attachTargetId.value)
    if (idx !== -1) projects.value[idx] = updated
    showAttach.value = false
  } catch (err) {
    logger.error('Failed to attach repo', err)
    attachError.value = t('llcBrowser.repo.attachError')
  } finally {
    attaching.value = false
  }
}

async function detachRepo(project: ProjectResponse): Promise<void> {
  detachingRepo.value = project.id
  repoError.value = { ...repoError.value, [project.id]: '' }
  try {
    await api.delete(`/api/llc/projects/${project.id}/repo`)
    const idx = projects.value.findIndex(p => p.id === project.id)
    if (idx !== -1) {
      projects.value[idx] = { ...projects.value[idx], code_source_id: null, code_source: null }
    }
  } catch (err) {
    logger.error('Failed to detach repo', err)
    repoError.value = { ...repoError.value, [project.id]: t('llcBrowser.repo.detachError') }
  } finally {
    detachingRepo.value = null
  }
}

// Sync calls the codebase-analytics source sync endpoint.
// Sync route confirmed: POST /api/analytics/codebase/sources/{source_id}/sync (GH#11129)
async function syncRepo(project: ProjectResponse): Promise<void> {
  const sourceId = project.code_source?.id
  if (!sourceId) return
  syncingRepo.value = project.id
  repoError.value = { ...repoError.value, [project.id]: '' }
  try {
    await api.post(`/api/analytics/codebase/sources/${sourceId}/sync`)
  } catch (err) {
    logger.error('Failed to sync repo', err)
    repoError.value = { ...repoError.value, [project.id]: t('llcBrowser.repo.syncError') }
  } finally {
    syncingRepo.value = null
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

/* GH#11129: repo linkage styles */
.card-repo {
  padding: 0.5rem 0;
  border-top: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.card-repo-empty {
  padding-top: 0.5rem;
}

.repo-row {
  display: flex;
  align-items: baseline;
  gap: 0.375rem;
  flex-wrap: wrap;
}

.repo-label {
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--text-secondary);
  flex-shrink: 0;
}

.repo-link {
  font-size: 0.8125rem;
  color: var(--color-accent-text, var(--color-accent, #c4651a));
  text-decoration: none;
  word-break: break-all;
}

.repo-link:hover {
  text-decoration: underline;
}

.repo-path {
  font-size: 0.75rem;
  font-family: var(--font-mono, monospace);
  color: var(--text-secondary);
  background: var(--bg-hover);
  padding: 0.125rem 0.375rem;
  border-radius: 4px;
  word-break: break-all;
}

.repo-status {
  font-size: 0.75rem;
  font-weight: 500;
  padding: 0.125rem 0.375rem;
  border-radius: 999px;
  background: var(--bg-hover);
  color: var(--text-secondary);
}

.repo-status-ready {
  color: var(--color-success, #16a34a);
  background: var(--color-success-bg, #dcfce7);
}

.repo-status-error {
  color: var(--color-error, #dc2626);
  background: var(--color-error-bg, #fee2e2);
}

.repo-status-syncing {
  color: var(--color-warning, #d97706);
  background: var(--color-warning-bg, #fef3c7);
}

.repo-actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

/* GH#11129: copy clone_path button */
.clone-copy-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 0.125rem 0.25rem;
  color: var(--text-muted);
  display: inline-flex;
  align-items: center;
  border-radius: var(--radius-sm, 4px);
  transition: color var(--duration-200);
}

.clone-copy-btn:hover {
  color: var(--text-primary);
}
</style>
