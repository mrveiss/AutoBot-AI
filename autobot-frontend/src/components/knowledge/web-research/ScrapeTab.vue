<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2026 mrveiss -->
<!-- Author: mrveiss -->
<!-- ScrapeTab — "Fetch Page" tab: extract text/markdown from a single URL (MVA-344) -->

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useWebResearch } from '@/composables/knowledge/useWebResearch'
import type { ScrapeResponse } from '@/composables/knowledge/useWebResearch'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ScrapeTab')
const { t } = useI18n()
const { scrapePage } = useWebResearch()

// ── State ──────────────────────────────────────────────────────────────────

const url = ref('')
const render = ref<'auto' | 'fast' | 'playwright'>('auto')
const ingest = ref(false)
const format = ref<'markdown' | 'html' | 'json'>('markdown')

const isLoading = ref(false)
const errorMsg = ref<string | null>(null)
const result = ref<ScrapeResponse | null>(null)

// ── Actions ────────────────────────────────────────────────────────────────

async function submit() {
  if (!url.value.trim()) return
  isLoading.value = true
  errorMsg.value = null
  result.value = null
  try {
    result.value = await scrapePage({
      url: url.value.trim(),
      render: render.value,
      ingest: ingest.value,
      format: format.value,
    })
  } catch (err: unknown) {
    logger.error('Fetch Page failed', err)
    errorMsg.value = err instanceof Error ? err.message : t('knowledge.webResearch.errorGeneric')
  } finally {
    isLoading.value = false
  }
}

function reset() {
  result.value = null
  errorMsg.value = null
}
</script>

<template>
  <div class="scrape-tab">
    <!-- Form -->
    <form class="wr-form" @submit.prevent="submit">
      <div class="wr-form-row">
        <label class="wr-label" for="scrape-url">{{ t('knowledge.webResearch.scrape.urlLabel') }}</label>
        <input
          id="scrape-url"
          v-model="url"
          type="url"
          class="wr-input"
          :placeholder="t('knowledge.webResearch.scrape.urlPlaceholder')"
          required
          :disabled="isLoading"
          :aria-label="t('knowledge.webResearch.scrape.urlLabel')"
        />
      </div>

      <div class="wr-form-row wr-form-row--inline">
        <div class="wr-field">
          <label class="wr-label" for="scrape-render">{{ t('knowledge.webResearch.renderLabel') }}</label>
          <select id="scrape-render" v-model="render" class="wr-select" :disabled="isLoading">
            <option value="auto">{{ t('knowledge.webResearch.renderAuto') }}</option>
            <option value="fast">{{ t('knowledge.webResearch.renderFast') }}</option>
            <option value="playwright">{{ t('knowledge.webResearch.renderPlaywright') }}</option>
          </select>
        </div>

        <div class="wr-field">
          <label class="wr-label" for="scrape-format">{{ t('knowledge.webResearch.scrape.formatLabel') }}</label>
          <select id="scrape-format" v-model="format" class="wr-select" :disabled="isLoading">
            <option value="markdown">Markdown</option>
            <option value="html">HTML</option>
            <option value="json">JSON</option>
          </select>
        </div>

        <div class="wr-field wr-field--checkbox">
          <label class="wr-checkbox-label">
            <input v-model="ingest" type="checkbox" :disabled="isLoading" />
            {{ t('knowledge.webResearch.ingestLabel') }}
          </label>
        </div>
      </div>

      <div class="wr-form-actions">
        <button type="submit" class="wr-btn wr-btn--primary" :disabled="isLoading || !url.trim()">
          <span v-if="isLoading" class="wr-spinner" aria-hidden="true" />
          {{ isLoading ? t('knowledge.webResearch.fetching') : t('knowledge.webResearch.scrape.submitLabel') }}
        </button>
        <button v-if="result || errorMsg" type="button" class="wr-btn wr-btn--ghost" @click="reset">
          {{ t('knowledge.webResearch.reset') }}
        </button>
      </div>
    </form>

    <!-- Loading skeleton -->
    <div v-if="isLoading" class="wr-skeleton-block" aria-label="Loading" aria-busy="true">
      <div class="wr-skeleton wr-skeleton--title" />
      <div class="wr-skeleton wr-skeleton--line" />
      <div class="wr-skeleton wr-skeleton--line wr-skeleton--short" />
      <div class="wr-skeleton wr-skeleton--line" />
      <div class="wr-skeleton wr-skeleton--line wr-skeleton--short" />
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
          d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
      </svg>
      <p>{{ t('knowledge.webResearch.scrape.emptyState') }}</p>
    </div>

    <!-- Result -->
    <div v-else class="wr-result">
      <div class="wr-result__header">
        <h3 class="wr-result__title">{{ result.metadata.title || result.url }}</h3>
        <span v-if="result.indexed" class="wr-badge wr-badge--success">{{ t('knowledge.webResearch.indexed') }}</span>
        <span class="wr-result__meta">{{ result.metadata.fetched_at }}</span>
      </div>
      <div class="wr-result__url">
        <a :href="result.url" target="_blank" rel="noopener noreferrer">{{ result.url }}</a>
      </div>

      <!-- Markdown viewer -->
      <pre v-if="result.markdown" class="wr-result__content wr-result__content--markdown">{{ result.markdown }}</pre>
      <pre v-else-if="result.html" class="wr-result__content">{{ result.html }}</pre>
      <pre v-else class="wr-result__content">{{ JSON.stringify(result, null, 2) }}</pre>
    </div>
  </div>
</template>
