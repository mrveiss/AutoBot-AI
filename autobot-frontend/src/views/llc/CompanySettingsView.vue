<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Author: mrveiss -->
<!--
  #15945: Company settings (/llc/companies/:companyId/settings), the mockup's CompanySettings
  screen. The CEO section is the one built so far; the other sections of the mockup (general,
  outbound agent messages, role knowledge, sub-companies) are separate work and are not stubbed here.
-->
<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import CompanyCeoCard from '@/components/llc/CompanyCeoCard.vue'

const props = defineProps<{ companyId?: string }>()
const route = useRoute()
const { t } = useI18n()
const companyId = computed(() => (route.params.companyId as string) ?? props.companyId ?? '')
</script>

<template>
  <div class="flex flex-col gap-4 p-4" data-testid="company-settings">
    <header class="flex flex-col gap-1">
      <h1 class="m-0 text-xl text-autobot-text-primary">{{ t('llcSettings.title') }}</h1>
      <p class="m-0 text-autobot-text-secondary">{{ t('llcSettings.subtitle') }}</p>
    </header>
    <p v-if="!companyId" class="m-0 text-autobot-text-muted">{{ t('llcSettings.noCompany') }}</p>
    <CompanyCeoCard v-else :company-id="companyId" />
  </div>
</template>
