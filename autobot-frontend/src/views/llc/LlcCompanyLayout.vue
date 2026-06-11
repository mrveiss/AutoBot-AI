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
.llc-company-layout {
  display: flex;
  align-items: stretch;
  min-height: 100%;
}

.llc-company-content {
  flex: 1;
  min-width: 0;
}
</style>
