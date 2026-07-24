<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Author: mrveiss -->
<!--
  GH#9627: Company selector — entry point for the Company OS nav item.
  Lists companies from GET /api/llc/companies/, stores the selection in
  the llcCompany Pinia store, then forwards to the company dashboard (or
  the ?redirect= destination set by the llcCompanyParamGuard).
  GH#12231: each row exposes a CompanyStatusControl (status badge + the
  valid activate/suspend/offboard/archive transitions for its state).
  GH#12212: archived companies are hidden by default (a "show archived" toggle
  reveals them) and an archived company can be permanently deleted (soft-delete
  via DELETE /api/llc/companies/{id}, scoped to that company's tenant context).
-->
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { BaseButton, BaseModal } from '@autobot/ui'
import { useLlcCompanyStore, type LlcCompany } from '@/stores/useLlcCompanyStore'
import { useRuntimeFeaturesStore } from '@/stores/useRuntimeFeaturesStore'
import CompanyStatusControl from '@/components/llc/CompanyStatusControl.vue'
import type { CompanyStatusResult } from '@/composables/llc/useCompanyStatusApi'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('CompanySelectorView')

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const companyStore = useLlcCompanyStore()
const runtimeFeaturesStore = useRuntimeFeaturesStore()

// #10502: Company OS (LLC) requires a PostgreSQL company/multi-company
// deployment; without it the company endpoints return 503. Gate the view on the
// runtime flag and show an informational empty-state instead of surfacing the
// raw 503 error + Retry button.
const companyOsEnabled = computed(() => runtimeFeaturesStore.companyOsEnabled)

// #12212: archived companies are hidden by default; the toggle refetches with
// include_archived=true so retired companies stay recoverable/visible.
const showArchived = ref(false)

// #12212: delete-confirmation + per-delete state.
const pendingDelete = ref<LlcCompany | null>(null)
const isDeleting = ref(false)
const deleteError = ref('')

async function selectCompany(company: LlcCompany): Promise<void> {
  companyStore.selectCompany(company.id)
  const redirect = route.query.redirect
  if (typeof redirect === 'string' && redirect.startsWith('/llc/')) {
    await router.push(redirect)
    return
  }
  // Enter the company's PM workspace (LlcCompanyLayout with sidebar → backlog,
  // boards, sprints…), not the sidebar-less standalone /llc/dashboard.
  await router.push(`/llc/companies/${company.id}`)
}

// #12231: reflect a status transition on the selector badge without a refetch.
// #12212: when a company is archived and archived rows are hidden, refetch so it
// drops out of the default list rather than lingering as a terminal badge.
function onStatusUpdated(updated: CompanyStatusResult): void {
  if (updated.llc_status === 'archived' && !showArchived.value) {
    void companyStore.fetchCompanies(showArchived.value)
    return
  }
  companyStore.applyStatus(updated.id, updated.llc_status)
}

// #12212: reload the list whenever the archived-visibility toggle changes.
function onToggleArchived(): void {
  showArchived.value = !showArchived.value
  void companyStore.fetchCompanies(showArchived.value)
}

// #12212: Delete is only offered for ARCHIVED companies — archive first (the
// safe, reversible retire step), then permanently remove, mirroring the
// project archive→delete flow.
function isArchived(company: LlcCompany): boolean {
  return company.llc_status === 'archived'
}

function requestDelete(company: LlcCompany): void {
  deleteError.value = ''
  pendingDelete.value = company
}

function cancelDelete(): void {
  pendingDelete.value = null
}

async function confirmDelete(): Promise<void> {
  const company = pendingDelete.value
  if (!company) return
  isDeleting.value = true
  deleteError.value = ''
  try {
    await companyStore.deleteCompany(company.id)
    pendingDelete.value = null
  } catch (err) {
    logger.error(`Failed to delete company ${company.id}`, err)
    // 409 = the company still has active sub-companies (CompanyHasChildrenError).
    const message = err instanceof Error ? err.message : ''
    deleteError.value = message.includes('409')
      ? t('llcCompanyStatus.deleteHasChildren')
      : t('llcCompanyStatus.deleteError')
  } finally {
    isDeleting.value = false
  }
}

onMounted(async () => {
  await runtimeFeaturesStore.load()
  // Only hit the company endpoint when the deployment supports company mode;
  // otherwise the request returns 503 and we render the unavailable state.
  if (companyOsEnabled.value) {
    void companyStore.fetchCompanies(showArchived.value)
  }
})
</script>

<template>
  <div class="company-selector">
    <header class="selector-header">
      <h1 class="selector-title">{{ $t('nav.companyOs') }}</h1>
      <p class="selector-subtitle">{{ $t('nav.llcSelectCompanyPrompt') }}</p>
      <!-- #12212: reveal archived companies (hidden from the default list). -->
      <label v-if="companyOsEnabled && !companyStore.unavailable" class="selector-archived-toggle">
        <input
          type="checkbox"
          :checked="showArchived"
          :disabled="companyStore.isLoading"
          @change="onToggleArchived"
        />
        {{ $t('llcCompanyStatus.showArchived') }}
      </label>
    </header>

    <!-- #10502: company mode off OR a 503 from the company endpoint —
         informational empty-state, never a raw error. -->
    <div v-if="!companyOsEnabled || companyStore.unavailable" class="selector-unavailable">
      <span class="selector-unavailable-icon" aria-hidden="true">🏢</span>
      <h2 class="selector-unavailable-title">
        {{ $t('nav.companyOsUnavailableTitle') }}
      </h2>
      <p class="selector-unavailable-desc">
        {{ $t('nav.companyOsUnavailableDesc') }}
      </p>
    </div>

    <div v-else-if="companyStore.error" class="selector-error">
      {{ $t('common.errorBoundary.fetchError') }}
      <button class="selector-retry" @click="companyStore.fetchCompanies(showArchived)">
        {{ $t('common.retry') }}
      </button>
    </div>

    <div v-else-if="companyStore.isLoading" class="selector-empty">
      {{ $t('common.loading') }}
    </div>

    <div v-else-if="!companyStore.hasCompanies" class="selector-empty">
      <p>{{ $t('nav.llcNoCompanies') }}</p>
      <RouterLink class="selector-create" to="/llc/companies/create">
        {{ $t('nav.llcCreateCompany') }}
      </RouterLink>
    </div>

    <ul v-else class="company-list">
      <li v-for="company in companyStore.companies" :key="company.id" class="company-row">
        <button
          type="button"
          class="company-card"
          :class="{ active: company.id === companyStore.selectedCompanyId }"
          @click="selectCompany(company)"
        >
          <span
            class="company-dot"
            :style="company.brand_color ? { background: company.brand_color } : undefined"
            aria-hidden="true"
          />
          <span class="company-meta">
            <span class="company-name">{{ company.name }}</span>
            <span v-if="company.description" class="company-description">
              {{ company.description }}
            </span>
          </span>
        </button>
        <div class="company-row-controls">
          <CompanyStatusControl
            class="company-row-status"
            :company="company"
            @updated="onStatusUpdated"
          />
          <!-- #12212: permanent delete, offered only once a company is archived. -->
          <BaseButton
            v-if="isArchived(company)"
            class="company-delete-btn"
            variant="danger"
            size="sm"
            @click="requestDelete(company)"
          >
            {{ $t('llcCompanyStatus.delete') }}
          </BaseButton>
        </div>
      </li>
    </ul>

    <footer v-if="companyStore.hasCompanies" class="selector-footer">
      <RouterLink class="selector-create" to="/llc/companies/create">
        {{ $t('nav.llcCreateCompany') }}
      </RouterLink>
    </footer>

    <!-- #12212: delete-confirmation modal for an archived company. -->
    <BaseModal
      v-if="pendingDelete"
      :model-value="true"
      :title="$t('llcCompanyStatus.confirmDeleteTitle')"
      :close-label="$t('common.cancel')"
      size="sm"
      @close="cancelDelete"
    >
      <p class="company-delete-confirm">
        {{ $t('llcCompanyStatus.confirmDelete', { name: pendingDelete.name }) }}
      </p>
      <p v-if="deleteError" class="company-delete-error" role="alert">
        {{ deleteError }}
      </p>
      <template #actions>
        <BaseButton variant="ghost" :disabled="isDeleting" @click="cancelDelete">
          {{ $t('common.cancel') }}
        </BaseButton>
        <BaseButton variant="danger" :disabled="isDeleting" @click="confirmDelete">
          {{ $t('llcCompanyStatus.delete') }}
        </BaseButton>
      </template>
    </BaseModal>
  </div>
</template>

<style scoped>
/* Ember semantic tokens — marigold accent (--color-accent = #C4651A light) */
.company-selector {
  max-width: 42rem;
  margin: 0 auto;
  padding: 1.5rem 1rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.selector-title {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-primary);
}

.selector-subtitle {
  margin-top: 0.25rem;
  font-size: 0.875rem;
  color: var(--text-secondary);
}

/* #10502: unavailable (no company-mode deployment) empty-state */
.selector-unavailable {
  padding: 3rem 1.5rem;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  background: var(--bg-secondary);
}

.selector-unavailable-icon {
  font-size: 2.5rem;
  line-height: 1;
}

.selector-unavailable-title {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text-primary);
}

.selector-unavailable-desc {
  max-width: 32rem;
  font-size: 0.875rem;
  color: var(--text-secondary);
}

.selector-error {
  padding: 0.75rem 1rem;
  border-radius: var(--radius-md);
  background: var(--color-danger-bg);
  color: var(--color-error);
  font-size: 0.875rem;
}

.selector-retry {
  margin-left: 0.75rem;
  text-decoration: underline;
}

.selector-empty {
  padding: 3rem 0;
  text-align: center;
  color: var(--text-muted);
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  align-items: center;
}

.company-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

/* #12231: card + its status control stack together as one row */
.company-row {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.875rem 1rem;
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-default);
  background: var(--bg-card);
}

.company-card {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  text-align: left;
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
}

.company-row:hover {
  border-color: var(--color-accent-border, var(--color-accent, var(--coselector-accent)));
  background: var(--bg-hover);
}

.company-card.active {
  color: var(--color-accent, var(--coselector-accent));
}

/* #12212: status control + delete action share the row's action strip */
.company-row-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  padding-left: 1.375rem;
}

.company-row-status {
  flex: 1 1 auto;
}

/* #12212: archived-visibility toggle in the header */
.selector-archived-toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  margin-top: 0.5rem;
  font-size: 0.8125rem;
  color: var(--text-secondary);
  cursor: pointer;
}

/* #12212: delete confirmation copy */
.company-delete-confirm {
  margin: 0;
  color: var(--text-primary);
}

.company-delete-error {
  margin: 0.5rem 0 0;
  font-size: var(--font-size-xs);
  color: var(--color-danger);
}

.company-dot {
  width: 0.625rem;
  height: 0.625rem;
  border-radius: var(--radius-full);
  flex: none;
  background: var(--color-accent, var(--coselector-accent));
}

.company-meta {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}

.company-name {
  font-weight: 600;
  color: var(--text-primary);
}

.company-description {
  font-size: 0.8125rem;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.selector-create {
  color: var(--color-accent-text, var(--color-accent, var(--coselector-accent)));
  font-size: 0.875rem;
  font-weight: 600;
  text-decoration: none;
}

.selector-create:hover {
  text-decoration: underline;
}
</style>
