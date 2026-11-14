<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Author: mrveiss -->
<!--
  GH#9627: Layout shell for company-scoped LLC routes
  (/llc/companies/:companyId/…) — renders the contextual LLC sidebar next
  to the routed view. Loads the company list once so the sidebar's company
  switcher is populated on deep links.
-->
<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import LlcSidebar from '@/components/llc/LlcSidebar.vue'
import PlanFirstProcessCard from '@/components/llc/workflowPlanner/PlanFirstProcessCard.vue'
import { useLlcCompanyStore } from '@/stores/useLlcCompanyStore'
import { useLlcCompanyNotices } from '@/composables/useLlcCompanyNotices'

const companyStore = useLlcCompanyStore()
const route = useRoute()
// The company the URL names (store selection when it names none): the notices subscribe to it (#21045)
// and the routed view is keyed by it (#21502).
const routeCompanyId = computed(() => {
  const raw = route.params.companyId
  return (Array.isArray(raw) ? raw[0] : raw) ?? companyStore.selectedCompanyId
})
useLlcCompanyNotices(routeCompanyId)
// The sidebar's company switch re-targets the same route, so Vue reuses the routed view and its
// load-on-mount data would stay the previous company's. The key sits on the <RouterView> vnode itself:
// a changed key remounts that RouterView subtree (the routed child and any nested view) once, while the
// layout, sidebar and plan card stay mounted (#21502). A route that handles the switch itself (CEO
// chat) opts out via meta.
const viewKey = computed(() => (route.meta?.keepOnCompanySwitch ? undefined : routeCompanyId.value))
// The creation wizard lands here with ?welcome=plan (#19938 E2).
const showPlanCard = computed(() => route.query.welcome === 'plan')

onMounted(() => {
  if (!companyStore.hasCompanies && !companyStore.isLoading) {
    void companyStore.fetchCompanies()
  }
})
</script>

<template>
  <div class="llc-company-layout">
    <LlcSidebar />
    <main class="llc-company-content">
      <PlanFirstProcessCard v-if="showPlanCard" class="m-3" />
      <RouterView :key="viewKey" />
    </main>
  </div>
</template>

<style scoped>
/*
  Height chain (#10750 C2): App.vue passes `h-full` to this component's root
  via <router-view class="h-full">, so `.llc-company-layout` has a real,
  bounded height. `height: 100%` here makes that explicit so routed board
  views can resolve their own `height: 100%` and contain their own scroll
  region instead of relying on calc(100vh - N) viewport magic.
*/
.llc-company-layout {
  display: flex;
  align-items: stretch;
  height: 100%;
  min-height: 0;
}

.llc-company-content {
  flex: 1;
  min-width: 0;
  /* Bounded flex column so children resolve height:100% and scroll internally */
  display: flex;
  flex-direction: column;
  min-height: 0;
}
</style>
