<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Author: mrveiss -->
<!--
  GH#9627: Contextual LLC sidebar — navigation spine for company-scoped views.

  Rendered by LlcCompanyLayout inside /llc/companies/:companyId/… routes.
  Links only routes that exist in router/index.ts:
    - Dashboard / Goals / Org Chart are query-scoped (?company=) views (#9861)
    - Backlog / Approvals / Costs / CEO Chat / Heartbeat are :companyId-scoped
  Sprint & Kanban boards need a :boardId and are reached via the Backlog.
-->
<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useLlcCompanyStore } from '@/stores/useLlcCompanyStore'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const companyStore = useLlcCompanyStore()

const companyId = computed(() => {
  const raw = route.params.companyId
  return (Array.isArray(raw) ? raw[0] : raw) ?? companyStore.selectedCompanyId
})

interface SidebarLink {
  labelKey: string
  to: { path: string; query?: Record<string, string> }
}

const links = computed<SidebarLink[]>(() => {
  const id = companyId.value
  return [
    // Query-scoped views (resolve company via ?company= — see #9861)
    { labelKey: 'nav.llcDashboard', to: { path: '/llc/dashboard', query: { company: id } } },
    // Company-scoped views (/llc/companies/:companyId/…)
    { labelKey: 'nav.llcBacklog', to: { path: `/llc/companies/${id}/backlog` } },
    { labelKey: 'nav.llcTimeline', to: { path: `/llc/companies/${id}/timeline` } },
    { labelKey: 'nav.llcGoals', to: { path: '/llc/goals', query: { company: id } } },
    { labelKey: 'nav.llcOrgChart', to: { path: '/llc/org-chart', query: { company: id } } },
    { labelKey: 'nav.llcApprovals', to: { path: `/llc/companies/${id}/approvals` } },
    { labelKey: 'nav.llcCosts', to: { path: `/llc/companies/${id}/costs` } },
    { labelKey: 'nav.llcHeartbeat', to: { path: `/llc/companies/${id}/heartbeat` } },
    { labelKey: 'nav.llcCeoChat', to: { path: `/llc/companies/${id}/ceo-chat` } },
  ]
})

function isActive(link: SidebarLink): boolean {
  return route.path === link.to.path
}

/**
 * Switch the active company while staying on the equivalent view.
 * Board-scoped routes (:boardId) belong to the old company, so fall back
 * to the new company's backlog for those.
 */
async function onCompanyChange(event: Event): Promise<void> {
  const id = (event.target as HTMLSelectElement).value
  if (!id || id === companyId.value) return
  companyStore.selectCompany(id)
  if (route.params.boardId) {
    await router.push({ name: 'llc-backlog', params: { companyId: id } })
  } else if (route.params.companyId) {
    await router.push({
      name: route.name as string,
      params: { ...route.params, companyId: id },
    })
  }
}
</script>

<template>
  <aside class="llc-sidebar" :aria-label="t('nav.companyOs')">
    <div class="llc-sidebar-company">
      <label class="llc-sidebar-label" for="llc-company-select">
        {{ t('nav.companyOs') }}
      </label>
      <select
        id="llc-company-select"
        class="llc-sidebar-select"
        :value="companyId"
        @change="onCompanyChange"
      >
        <option v-if="!companyStore.hasCompanies" :value="companyId" disabled>
          {{ companyStore.selectedCompany?.name ?? companyId }}
        </option>
        <option v-for="company in companyStore.companies" :key="company.id" :value="company.id">
          {{ company.name }}
        </option>
      </select>
      <RouterLink class="llc-sidebar-switch" :to="{ name: 'llc-company-select' }">
        {{ t('nav.llcSelectCompany') }}
      </RouterLink>
    </div>

    <nav class="llc-sidebar-nav" :aria-label="t('nav.companyOs')">
      <RouterLink
        v-for="link in links"
        :key="link.labelKey"
        :to="link.to"
        class="llc-nav-item"
        :class="{ active: isActive(link) }"
        :aria-current="isActive(link) ? 'page' : undefined"
      >
        {{ t(link.labelKey) }}
      </RouterLink>
    </nav>
  </aside>
</template>

<style scoped>
/* Ember semantic tokens (src/assets/css/themes/ember.css):
   --bg-surface = sidebar bg · --color-accent = marigold accent (#C4651A light)
   --color-accent-subtle = active item bg · fallbacks keep non-ember themes legible */
.llc-sidebar {
  width: 13.5rem;
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 1rem 0.75rem;
  background: var(--bg-surface, #f9fafb);
  border-right: 1px solid var(--border-default, #e5e7eb);
  min-height: 100%;
}

.llc-sidebar-company {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.llc-sidebar-label {
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted, #6b7280);
}

.llc-sidebar-select {
  width: 100%;
  padding: 0.375rem 0.5rem;
  font-size: 0.875rem;
  border-radius: var(--radius-md, 8px);
  border: 1px solid var(--border-default, #d1d5db);
  background: var(--bg-input, #ffffff);
  color: var(--text-primary, #111827);
}

.llc-sidebar-switch {
  font-size: 0.75rem;
  color: var(--color-accent-text, var(--color-accent, #c4651a));
  text-decoration: none;
}

.llc-sidebar-switch:hover {
  text-decoration: underline;
}

.llc-sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}

.llc-nav-item {
  display: block;
  padding: 0.4375rem 0.625rem;
  font-size: 0.875rem;
  border-radius: var(--radius-md, 8px);
  border-left: 2px solid transparent;
  color: var(--text-secondary, #4b5563);
  text-decoration: none;
}

.llc-nav-item:hover {
  background: var(--bg-hover, #f3f4f6);
  color: var(--text-primary, #111827);
}

.llc-nav-item.active {
  background: var(--color-accent-subtle, #fcefe0);
  border-left-color: var(--color-accent, #c4651a);
  color: var(--color-accent-text, var(--color-accent, #c4651a));
  font-weight: 600;
}
</style>
