<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Author: mrveiss -->
<!--
  GH#9627: Company selector — entry point for the Company OS nav item.
  Lists companies from GET /api/llc/companies/, stores the selection in
  the llcCompany Pinia store, then forwards to the company dashboard (or
  the ?redirect= destination set by the llcCompanyParamGuard).
-->
<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useLlcCompanyStore, type LlcCompany } from '@/stores/useLlcCompanyStore'
import { useRuntimeFeaturesStore } from '@/stores/useRuntimeFeaturesStore'

const route = useRoute()
const router = useRouter()
const companyStore = useLlcCompanyStore()
const runtimeFeaturesStore = useRuntimeFeaturesStore()

// #10502: Company OS (LLC) requires a PostgreSQL company/multi-company
// deployment; in single_user mode the company endpoints return 503. Gate the
// view on the runtime flag and show an informational empty-state instead of
// surfacing the raw 503 error + Retry button.
const companyOsEnabled = computed(() => runtimeFeaturesStore.companyOsEnabled)

async function selectCompany(company: LlcCompany): Promise<void> {
  companyStore.selectCompany(company.id)
  const redirect = route.query.redirect
  if (typeof redirect === 'string' && redirect.startsWith('/llc/')) {
    await router.push(redirect)
    return
  }
  await router.push({ path: '/llc/dashboard', query: { company: company.id } })
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

    <!-- #10502: deployment without company mode (single_user) — informational
         empty-state instead of a raw 503 error + Retry. -->
    <div v-if="!companyOsEnabled" class="selector-unavailable">
      <span class="selector-unavailable-icon" aria-hidden="true">🏢</span>
      <h2 class="selector-unavailable-title">
        {{ $t('nav.companyOsUnavailableTitle') }}
      </h2>
      <p class="selector-unavailable-desc">
        {{ $t('nav.companyOsUnavailableDesc') }}
      </p>
    </div>

    <div v-else-if="companyStore.error" class="selector-error">
      {{ companyStore.error }}
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
      <li v-for="company in companyStore.companies" :key="company.id">
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
          <span v-if="company.llc_status" class="company-status">
            {{ company.llc_status }}
          </span>
        </button>
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
  color: var(--text-primary, #111827);
}

.selector-subtitle {
  margin-top: 0.25rem;
  font-size: 0.875rem;
  color: var(--text-secondary, #6b7280);
}

/* #10502: unavailable (single_user deployment) empty-state */
.selector-unavailable {
  padding: 3rem 1.5rem;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  border: 1px solid var(--border-default, #e5e7eb);
  border-radius: var(--radius-lg, 12px);
  background: var(--bg-secondary, #f9fafb);
}

.selector-unavailable-icon {
  font-size: 2.5rem;
  line-height: 1;
}

.selector-unavailable-title {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text-primary, #111827);
}

.selector-unavailable-desc {
  max-width: 32rem;
  font-size: 0.875rem;
  color: var(--text-secondary, #6b7280);
}

.selector-error {
  padding: 0.75rem 1rem;
  border-radius: var(--radius-md, 8px);
  background: var(--color-danger-bg, #fae5e1);
  color: var(--color-danger, #cb3326);
  font-size: 0.875rem;
}

.selector-retry {
  margin-left: 0.75rem;
  text-decoration: underline;
}

.selector-empty {
  padding: 3rem 0;
  text-align: center;
  color: var(--text-muted, #6b7280);
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

.company-card {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.875rem 1rem;
  text-align: left;
  border-radius: var(--radius-lg, 12px);
  border: 1px solid var(--border-default, #e5e7eb);
  background: var(--bg-card, #ffffff);
  cursor: pointer;
}

.company-card:hover {
  border-color: var(--color-accent-border, var(--color-accent, #c4651a));
  background: var(--bg-hover, #f9fafb);
}

.company-card.active {
  border-color: var(--color-accent, #c4651a);
  background: var(--color-accent-subtle, #fcefe0);
}

.company-dot {
  width: 0.625rem;
  height: 0.625rem;
  border-radius: 9999px;
  flex: none;
  background: var(--color-accent, #c4651a);
}

.company-meta {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}

.company-name {
  font-weight: 600;
  color: var(--text-primary, #111827);
}

.company-description {
  font-size: 0.8125rem;
  color: var(--text-secondary, #6b7280);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.company-status {
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 0.125rem 0.5rem;
  border-radius: 9999px;
  background: var(--color-accent-subtle, #fcefe0);
  color: var(--color-accent-text, var(--color-accent, #c4651a));
  flex: none;
}

.selector-create {
  color: var(--color-accent-text, var(--color-accent, #c4651a));
  font-size: 0.875rem;
  font-weight: 600;
  text-decoration: none;
}

.selector-create:hover {
  text-decoration: underline;
}
</style>
