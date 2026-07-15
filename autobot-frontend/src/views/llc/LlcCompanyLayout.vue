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
import { onMounted } from 'vue'
import LlcSidebar from '@/components/llc/LlcSidebar.vue'
import { useLlcCompanyStore } from '@/stores/useLlcCompanyStore'

const companyStore = useLlcCompanyStore()

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
      <RouterView />
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
