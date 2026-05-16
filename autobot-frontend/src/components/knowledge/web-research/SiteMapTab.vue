<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2026 mrveiss -->
<!-- Author: mrveiss -->
<!-- SiteMapTab — "Find Pages" tab: discover all URLs on a domain (MVA-344) -->

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useWebResearch } from '@/composables/knowledge/useWebResearch'
import type { SiteMapResponse, SiteMapUrlEntry } from '@/composables/knowledge/useWebResearch'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('SiteMapTab')
const { t } = useI18n()
const { findPages } = useWebResearch()

// ── State ──────────────────────────────────────────────────────────────────

const domain = ref('')
const maxUrls = ref(500)
const respectRobots = ref(true)

const isLoading = ref(false)
const errorMsg = ref<string | null>(null)
const result = ref<SiteMapResponse | null>(null)
const filterText = ref('')

// ── Actions ────────────────────────────────────────────────────────────────

function filteredUrls(urls: SiteMapUrlEntry[]): SiteMapUrlEntry[] {
  if (!filterText.value.trim()) return urls
  const q = filterText.value.toLowerCase()
  return urls.filter(u => u.url.toLowerCase().includes(q) || (u.title ?? '').toLowerCase().includes(q))
}

async function submit() {
  if (!domain.value.trim()) return
  isLoading.value = true
  errorMsg.value = null
  result.value = null
  filterText.value = ''

  try {
    result.value = await findPages({
      domain: domain.value.trim(),
      max_urls: maxUrls.value,
      respect_robots: respectRobots.value,
    })
  } catch (err: unknown) {
    logger.error('Find Pages failed', err)
    errorMsg.value = err instanceof Error ? err.message : t('knowledge.webResearch.errorGeneric')
  } finally {
    isLoading.value = false
  }
}

function reset() {
  result.value = null
  errorMsg.value = null
  filterText.value = ''
}
</script>

<template>
  <div class="sitemap-tab">
    <!-- Form -->
    <form class="wr-form" @submit.prevent="submit">
      <div class="wr-form-row">
        <label class="wr-label" for="sitemap-domain">{{ t('knowledge.webResearch.siteMap.domainLabel') }}</label>
        <input
          id="sitemap-domain"
          v-model="domain"
          type="text"
          class="wr-input"
          :placeholder="t('knowledge.webResearch.siteMap.domainPlaceholder')"
          required
          :disabled="isLoading"
          :aria-label="t('knowledge.webResearch.siteMap.domainLabel')"
        />
      </div>

      <div class="wr-form-row wr-form-row--inline">
        <div class="wr-field">
          <label class="wr-label" for="sitemap-max-urls">{{ t('knowledge.webResearch.siteMap.maxUrlsLabel') }}</label>
          <input
            id="sitemap-max-urls"
            v-model.number="maxUrls"
            type="number"
            min="1"
            max="5000"
            class="wr-input wr-input--number"
            :disabled="isLoading"
          />
        </div>

        <div class="wr-field wr-field--checkbox">
          <label class="wr-checkbox-label">
            <input v-model="respectRobots" type="checkbox" :disabled="isLoading" />
            {{ t('knowledge.webResearch.respectRobotsLabel') }}
          </label>
        </div>
      </div>

      <div class="wr-form-actions">
        <button type="submit" class="wr-btn wr-btn--primary" :disabled="isLoading || !domain.trim()">
          <span v-if="isLoading" class="wr-spinner" aria-hidden="true" />
          {{ isLoading ? t('knowledge.webResearch.discovering') : t('knowledge.webResearch.siteMap.submitLabel') }}
        </button>
        <button v-if="result || errorMsg" type="button" class="wr-btn wr-btn--ghost" @click="reset">
          {{ t('knowledge.webResearch.reset') }}
        </button>
      </div>
    </form>

    <!-- Loading skeleton with progress -->
    <div v-if="isLoading" class="wr-progress-block" aria-label="Loading" aria-busy="true">
      <div class="wr-progress-bar wr-progress-bar--indeterminate">
        <div class="wr-progress-bar__fill wr-progress-bar__fill--indeterminate" />
      </div>
      <p class="wr-progress-status">{{ t('knowledge.webResearch.discovering') }}</p>
      <div class="wr-skeleton-block">
        <div v-for="n in 6" :key="n" class="wr-skeleton wr-skeleton--line" />
      </div>
    </div>

    <!-- Error -->
    <div v-else-if="errorMsg" class="wr-error" role="alert">
      <svg class="wr-error__icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
          d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
      </svg>
      <span>{{ errorMsg }}</span>
      <button class="wr-error__retry" @click="submit">{{ t('knowledge.webResearch.retry') }}</button>
    </div>

    <!-- Empty state -->
    <div v-else-if="!result" class="wr-empty">
      <svg class="wr-empty__icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
          d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
      </svg>
      <p>{{ t('knowledge.webResearch.siteMap.emptyState') }}</p>
    </div>

    <!-- Result -->
    <div v-else class="wr-result">
      <div class="wr-result__header">
        <h3 class="wr-result__title">
          {{ t('knowledge.webResearch.siteMap.resultTitle', { count: result.count, domain: result.domain }) }}
        </h3>
        <span class="wr-badge wr-badge--info">{{ result.source }}</span>
      </div>

      <!-- Filter input -->
      <div class="wr-filter-row">
        <input
          v-model="filterText"
          type="text"
          class="wr-input wr-input--filter"
          :placeholder="t('knowledge.webResearch.filterPlaceholder')"
          :aria-label="t('knowledge.webResearch.filterLabel')"
        />
        <span class="wr-filter-count">
          {{ filteredUrls(result.urls).length }} / {{ result.count }}
        </span>
      </div>

      <!-- URL tree list -->
      <ul class="wr-url-list" :aria-label="t('knowledge.webResearch.siteMap.urlListLabel')">
        <li
          v-for="entry in filteredUrls(result.urls)"
          :key="entry.url"
          class="wr-url-list__item"
          :style="{ paddingLeft: entry.depth * 16 + 'px' }"
        >
          <svg class="wr-url-list__tree-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
          </svg>
          <div class="wr-url-list__content">
            <a :href="entry.url" target="_blank" rel="noopener noreferrer" class="wr-url-list__link">{{ entry.url }}</a>
            <span v-if="entry.title" class="wr-url-list__title">{{ entry.title }}</span>
          </div>
        </li>
      </ul>

      <p v-if="filteredUrls(result.urls).length === 0" class="wr-empty-filter">
        {{ t('knowledge.webResearch.noFilterResults') }}
      </p>
    </div>
  </div>
</template>
