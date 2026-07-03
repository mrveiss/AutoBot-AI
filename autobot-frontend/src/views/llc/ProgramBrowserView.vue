<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025-2026 mrveiss -->
<!-- Author: mrveiss -->
<!--
  ProgramBrowserView (GH#9628) — middle tier of the LLC work hierarchy.
  Lists the programs under a portfolio as a card grid; clicking a card
  drills down into that program's projects. A header "Create" action opens a
  modal that POSTs a new program and prepends it to the list (#10750 B1).
-->
<template>
  <div class="llc-browser">
    <LlcBreadcrumb :items="breadcrumb" />

    <header class="browser-header">
      <div class="browser-heading">
        <h2 class="browser-title">{{ t('llcBrowser.programs.title') }}</h2>
        <span class="browser-count">
          {{ t('llcBrowser.programs.count', { count: programs.length }) }}
        </span>
      </div>
      <BaseButton variant="primary" :disabled="!portfolioId" @click="openCreate">
        {{ t('llcBrowser.programs.create') }}
      </BaseButton>
    </header>

    <div v-if="loading" class="browser-state">{{ t('llcBrowser.programs.loading') }}</div>

    <template v-else-if="loadError">
      <ErrorBanner :message="t('llcBrowser.programs.loadError')" class="browser-error" />
      <BaseButton variant="secondary" size="sm" @click="loadPrograms">
        {{ t('llcBrowser.retry') }}
      </BaseButton>
    </template>

    <div v-else-if="!programs.length" class="browser-state">
      {{ t('llcBrowser.programs.empty') }}
    </div>

    <div v-else class="card-grid">
      <button
        v-for="p in programs"
        :key="p.id"
        type="button"
        class="entity-card"
        @click="openProgram(p)"
      >
        <div class="card-top">
          <h3 class="card-name">{{ p.name }}</h3>
          <span class="status-badge" :class="`status-${p.status}`">{{ p.status }}</span>
        </div>
        <p v-if="p.description" class="card-desc">{{ p.description }}</p>
        <p class="card-meta">{{ t('llcBrowser.projectUnit', { count: p.project_count }, p.project_count) }}</p>
      </button>
    </div>

    <BaseModal
      v-model="showCreate"
      :title="t('llcBrowser.programs.createTitle')"
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
          <label class="create-label" for="program-description">
            {{ t('llcBrowser.descriptionLabel') }}
          </label>
          <textarea
            id="program-description"
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
          @click="createProgram"
        >
          {{ t('llcBrowser.createAction') }}
        </BaseButton>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import LlcBreadcrumb, { type BreadcrumbItem } from '@/components/llc/LlcBreadcrumb.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import { BaseModal } from '@autobot/ui'
import ErrorBanner from '@/components/base/ErrorBanner.vue'

interface ProgramResponse {
  id: string
  company_id: string
  portfolio_id: string
  name: string
  description: string | null
  status: string
  created_at: string
  updated_at: string
  project_count: number
}

const logger = createLogger('ProgramBrowserView')
const api = useApiClient()
const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const companyId = computed(() => route.params.companyId as string)
const portfolioId = computed(() => route.params.portfolioId as string)
const programs = ref<ProgramResponse[]>([])
const loading = ref(false)
const loadError = ref(false)

const showCreate = ref(false)
const creating = ref(false)
const createError = ref('')
const form = ref({ name: '', description: '' })

const breadcrumb = computed<BreadcrumbItem[]>(() => [
  {
    label: t('llcBrowser.portfolios.title'),
    to: { name: 'llc-portfolios', params: { companyId: companyId.value } },
  },
  { label: t('llcBrowser.programs.title') },
])

async function loadPrograms(): Promise<void> {
  loading.value = true
  loadError.value = false
  try {
    programs.value = await api.get<ProgramResponse[]>(
      `/api/llc/portfolios/${portfolioId.value}/programs`,
    )
  } catch (err) {
    logger.error('Failed to load programs', err)
    loadError.value = true
    programs.value = []
  } finally {
    loading.value = false
  }
}

function openCreate(): void {
  form.value = { name: '', description: '' }
  createError.value = ''
  showCreate.value = true
}

async function createProgram(): Promise<void> {
  const name = form.value.name.trim()
  if (!name || !portfolioId.value) return
  creating.value = true
  createError.value = ''
  try {
    // ProgramCreate: company_id (required) + name + optional description; the
    // server derives the true tenant from the parent portfolio (#10261).
    const created = await api.post<ProgramResponse>(
      `/api/llc/portfolios/${portfolioId.value}/programs`,
      {
        company_id: companyId.value,
        name,
        description: form.value.description.trim() || undefined,
      },
    )
    programs.value.unshift(created)
    showCreate.value = false
  } catch (err) {
    logger.error('Failed to create program', err)
    createError.value = t('llcBrowser.programs.createError')
  } finally {
    creating.value = false
  }
}

function openProgram(p: ProgramResponse): void {
  router.push({
    name: 'llc-projects',
    params: { companyId: companyId.value, programId: p.id },
  })
}

onMounted(loadPrograms)
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
  text-align: left;
  cursor: pointer;
  border-radius: var(--radius-md, 8px);
  border: 1px solid var(--border-default);
  background: var(--bg-surface);
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
