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
-->
<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useLlcCompanyStore, type LlcCompany } from '@/stores/useLlcCompanyStore'
import { useRuntimeFeaturesStore } from '@/stores/useRuntimeFeaturesStore'
import CompanyStatusControl from '@/components/llc/CompanyStatusControl.vue'
import type { CompanyStatusResult } from '@/composables/llc/useCompanyStatusApi'

const route = useRoute()
const router = useRouter()
const companyStore = useLlcCompanyStore()
const runtimeFeaturesStore = useRuntimeFeaturesStore()

// #10502: Company OS (LLC) requires a PostgreSQL company/multi-company
// deployment; without it the company endpoints return 503. Gate the view on the
// runtime flag and show an informational empty-state instead of surfacing the
// raw 503 error + Retry button.
const companyOsEnabled = computed(() => runtimeFeaturesStore.companyOsEnabled)

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
function onStatusUpdated(updated: CompanyStatusResult): void {
  companyStore.applyStatus(updated.id, updated.llc_status)
}

onMounted(async () => {
  await runtimeFeaturesStore.load()
  // Only hit the company endpoint when the deployment supports company mode;
  // otherwise the request returns 503 and we render the unavailable state.
  if (companyOsEnabled.value) {
    void companyStore.fetchCompanies()
  }
})
</script>

<template>
  <div class="company-selector">
    <header class="selector-header">
      <h1 class="selector-title">{{ $t('nav.companyOs') }}</h1>
      <p class="selector-subtitle">{{ $t('nav.llcSelectCompanyPrompt') }}</p>
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
      <button class="selector-retry" @click="companyStore.fetchCompanies()">
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
        <CompanyStatusControl
          class="company-row-status"
          :company="company"
          @updated="onStatusUpdated"
        />
      </li>
    </ul>

    <footer v-if="companyStore.hasCompanies" class="selector-footer">
      <RouterLink class="selector-create" to="/llc/companies/create">
        {{ $t('nav.llcCreateCompany') }}
      </RouterLink>
    </footer>
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

.company-row-status {
  padding-left: 1.375rem;
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
