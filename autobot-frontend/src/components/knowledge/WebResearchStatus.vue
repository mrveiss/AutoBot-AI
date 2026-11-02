<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2026 mrveiss -->
<!-- Author: mrveiss -->
<!--
  #19217: web research is configured once, platform-wide, in the SLM admin console. Every
  write to it is admin-only and global, so this main-app surface is a read-only status
  with a link there. It replaces both main-app editors (the Knowledge → Research settings
  tab and Settings → Web research), which are retired in the same change.
-->

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useWebResearchStore } from '@/stores/useWebResearchStore'
import { getSLMAdminUrl } from '@/config/ssot-config'

const { t } = useI18n()
const store = useWebResearchStore()

const slmWebResearchUrl = computed(() => `${getSLMAdminUrl()}/settings/admin/web-research`)

const METHOD_KEYS: Record<string, string> = {
  basic: 'settings.webResearch.methodBasic',
  advanced: 'settings.webResearch.methodAdvanced',
  api_based: 'settings.webResearch.methodApiBased',
}
const methodLabel = computed(() => {
  const method = store.settings.preferred_method
  return METHOD_KEYS[method] ? t(METHOD_KEYS[method]) : method
})

onMounted(() => {
  store.loadFromBackend()
})
</script>

<template>
  <section class="web-research-status" data-testid="web-research-status" :aria-busy="store.isLoading">
    <h3 class="status-title">{{ t('knowledge.webResearch.status.title') }}</h3>
    <p class="status-desc">{{ t('knowledge.webResearch.status.desc') }}</p>

    <dl class="status-grid">
      <div class="status-item">
        <dt>{{ t('knowledge.webResearch.status.enabled') }}</dt>
        <dd data-testid="status-enabled">
          {{ store.isEnabled ? t('knowledge.webResearch.status.yes') : t('knowledge.webResearch.status.no') }}
        </dd>
      </div>
      <div class="status-item">
        <dt>{{ t('knowledge.webResearch.status.method') }}</dt>
        <dd data-testid="status-method">{{ methodLabel }}</dd>
      </div>
      <div class="status-item">
        <dt>{{ t('knowledge.webResearch.status.cacheSize') }}</dt>
        <dd data-testid="status-cache">{{ store.cacheSize }}</dd>
      </div>
      <div class="status-item">
        <dt>{{ t('knowledge.webResearch.status.availability') }}</dt>
        <dd data-testid="status-availability">
          {{ store.researcherAvailable ? t('knowledge.webResearch.status.available') : t('knowledge.webResearch.status.notAvailable') }}
        </dd>
      </div>
    </dl>

    <a
      :href="slmWebResearchUrl"
      target="_blank"
      rel="noopener noreferrer"
      class="status-link"
      data-testid="web-research-slm-link"
    >{{ t('knowledge.webResearch.status.configureLink') }}</a>
  </section>
</template>

<style scoped>
.web-research-status {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
  padding: var(--spacing-lg);
  color: var(--text-primary);
}

.status-title {
  margin: 0;
  font-size: var(--text-lg);
}

.status-desc {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
  gap: var(--spacing-md);
  margin: 0;
}

.status-item {
  padding: var(--spacing-md);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
}

.status-item dt {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.status-item dd {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: 600;
}

.status-link {
  align-self: flex-start;
  font-weight: 600;
  text-decoration: underline;
  text-underline-offset: 2px;
}
</style>
