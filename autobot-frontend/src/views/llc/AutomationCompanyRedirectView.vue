<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Author: mrveiss -->
<!--
  GH#13939: Company OS absorbed the automation module. The workflow builder now
  lives at /llc/companies/:companyId/automation/*, so the legacy /automation/*
  entry point (main nav item, bookmarks, deep links) resolves the active
  company and forwards, preserving the requested section. With no company to
  scope to, the user is sent to the company selector carrying the destination.
-->
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useLlcCompanyContext } from '@/composables/llc/useLlcCompanyContext'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('AutomationCompanyRedirect')
const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const { resolveCompanyId } = useLlcCompanyContext()

const needsCompany = ref(false)

/** `/automation/browser-automation` → `browser-automation` */
function requestedSection(): string {
  const raw = route.params.pathMatch
  const parts = Array.isArray(raw) ? raw : raw ? [String(raw)] : []
  return parts.filter(Boolean).join('/')
}

onMounted(async () => {
  const section = requestedSection() || 'overview'
  const companyId = await resolveCompanyId()
  if (!companyId) {
    needsCompany.value = true
    logger.warn('No company to scope automation to — routing to the company selector')
    await router.replace({ name: 'llc-company-select', query: { redirect: route.fullPath } })
    return
  }
  // #13996: carry the query and hash across — `resolveEntityRoute` deep-links
  // here as `/automation?workflow=<id>`, and a bare path dropped the anchor.
  await router.replace({
    path: `/llc/companies/${companyId}/automation/${section}`,
    query: route.query,
    hash: route.hash,
  })
})
</script>

<template>
  <div class="p-8 text-center text-autobot-text-muted">
    {{ needsCompany ? t('workflow.views.companyRequired') : t('workflow.views.resolvingCompany') }}
  </div>
</template>
