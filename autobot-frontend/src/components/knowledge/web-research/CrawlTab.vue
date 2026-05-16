<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2026 mrveiss -->
<!-- Author: mrveiss -->
<!-- CrawlTab — "Crawl Site" tab: BFS crawl with live progress (MVA-344) -->

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useWebResearch } from '@/composables/knowledge/useWebResearch'
import type { CrawlResponse, CrawlPageEntry } from '@/composables/knowledge/useWebResearch'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('CrawlTab')
const { t } = useI18n()
const { crawlSite } = useWebResearch()

// ── State ──────────────────────────────────────────────────────────────────

const seedUrl = ref('')
const maxDepth = ref(2)
const maxPages = ref(50)
const respectRobots = ref(true)
const ingest = ref(true)
const sameOrigin = ref(true)
const render = ref<'auto' | 'fast' | 'playwright'>('auto')

const isLoading = ref(false)
const errorMsg = ref<string | null>(null)
const result = ref<CrawlResponse | null>(null)
const progressPages = ref<CrawlPageEntry[]>([])

const progressPct = computed(() =>
  result.value ? 100 : isLoading.value && maxPages.value > 0
    ? Math.min(99, Math.round((progressPages.value.length / maxPages.value) * 100))
    : 0
)

// ── Actions ────────────────────────────────────────────────────────────────

async function submit() {
  if (!seedUrl.value.trim()) return
  isLoading.value = true
  errorMsg.value = null
  result.value = null
  progressPages.value = []

  try {
    // Crawl is synchronous on the backend (can be slow) — no polling needed.
    // We simulate progress by showing a spinner while waiting.
    result.value = await crawlSite({
      seeds: [seedUrl.value.trim()],
      max_depth: maxDepth.value,
      max_pages: maxPages.value,
      respect_robots: respectRobots.value,
      ingest: ingest.value,
      same_origin: sameOrigin.value,
      render: render.value,
    })
  } catch (err: unknown) {
    logger.error('Crawl Site failed', err)
    errorMsg.value = err instanceof Error ? err.message : t('knowledge.webResearch.errorGeneric')
  } finally {
    isLoading.value = false
  }
}

function reset() {
  result.value = null
  errorMsg.value = null
  progressPages.value = []
}
</script>

<template>
  <div class="crawl-tab">
    <!-- Form -->
    <form class="wr-form" @submit.prevent="submit">
      <div class="wr-form-row">
        <label class="wr-label" for="crawl-seed">{{ t('knowledge.webResearch.crawl.seedLabel') }}</label>
        <input
          id="crawl-seed"
          v-model="seedUrl"
          type="url"
          class="wr-input"
          :placeholder="t('knowledge.webResearch.crawl.seedPlaceholder')"
          required
          :disabled="isLoading"
          :aria-label="t('knowledge.webResearch.crawl.seedLabel')"
        />
      </div>

      <div class="wr-form-row wr-form-row--inline">
        <div class="wr-field">
          <label class="wr-label" for="crawl-depth">{{ t('knowledge.webResearch.crawl.depthLabel') }}</label>
          <input
            id="crawl-depth"
            v-model.number="maxDepth"
            type="number"
            min="1"
            max="10"
            class="wr-input wr-input--number"
            :disabled="isLoading"
          />
        </div>

        <div class="wr-field">
          <label class="wr-label" for="crawl-max-pages">{{ t('knowledge.webResearch.crawl.maxPagesLabel') }}</label>
          <input
            id="crawl-max-pages"
            v-model.number="maxPages"
            type="number"
            min="1"
            max="500"
            class="wr-input wr-input--number"
            :disabled="isLoading"
          />
        </div>

        <div class="wr-field">
          <label class="wr-label" for="crawl-render">{{ t('knowledge.webResearch.renderLabel') }}</label>
          <select id="crawl-render" v-model="render" class="wr-select" :disabled="isLoading">
            <option value="auto">{{ t('knowledge.webResearch.renderAuto') }}</option>
            <option value="fast">{{ t('knowledge.webResearch.renderFast') }}</option>
            <option value="playwright">{{ t('knowledge.webResearch.renderPlaywright') }}</option>
          </select>
        </div>
      </div>

      <div class="wr-form-row wr-form-row--inline">
        <div class="wr-field wr-field--checkbox">
          <label class="wr-checkbox-label">
            <input v-model="respectRobots" type="checkbox" :disabled="isLoading" />
            {{ t('knowledge.webResearch.respectRobotsLabel') }}
          </label>
        </div>
        <div class="wr-field wr-field--checkbox">
          <label class="wr-checkbox-label">
            <input v-model="sameOrigin" type="checkbox" :disabled="isLoading" />
            {{ t('knowledge.webResearch.crawl.sameOriginLabel') }}
          </label>
        </div>
        <div class="wr-field wr-field--checkbox">
          <label class="wr-checkbox-label">
            <input v-model="ingest" type="checkbox" :disabled="isLoading" />
            {{ t('knowledge.webResearch.ingestLabel') }}
          </label>
        </div>
      </div>

      <div class="wr-form-actions">
        <button type="submit" class="wr-btn wr-btn--primary" :disabled="isLoading || !seedUrl.trim()">
          <span v-if="isLoading" class="wr-spinner" aria-hidden="true" />
          {{ isLoading ? t('knowledge.webResearch.crawling') : t('knowledge.webResearch.crawl.submitLabel') }}
        </button>
        <button v-if="result || errorMsg" type="button" class="wr-btn wr-btn--ghost" @click="reset">
          {{ t('knowledge.webResearch.reset') }}
        </button>
      </div>
    </form>

    <!-- Progress bar + skeleton -->
    <div v-if="isLoading" class="wr-progress-block" aria-label="Loading" aria-busy="true">
      <div class="wr-progress-bar">
        <div class="wr-progress-bar__fill" :style="{ width: progressPct + '%' }" />
      </div>
      <p class="wr-progress-status">{{ t('knowledge.webResearch.crawling') }}</p>
      <div class="wr-skeleton-block">
        <div v-for="n in 4" :key="n" class="wr-skeleton wr-skeleton--line" />
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
          d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      <p>{{ t('knowledge.webResearch.crawl.emptyState') }}</p>
    </div>

    <!-- Result -->
    <div v-else class="wr-result">
      <div class="wr-result__header">
        <h3 class="wr-result__title">
          {{ t('knowledge.webResearch.crawl.resultTitle', { count: result.count }) }}
        </h3>
        <span v-if="result.indexed" class="wr-badge wr-badge--success">{{ t('knowledge.webResearch.indexed') }}</span>
      </div>

      <ul class="wr-url-list" :aria-label="t('knowledge.webResearch.crawl.urlListLabel')">
        <li
          v-for="page in result.pages"
          :key="page.url"
          class="wr-url-list__item"
          :class="{ 'wr-url-list__item--failed': !page.success }"
        >
          <span class="wr-url-list__depth" :aria-label="t('knowledge.webResearch.depthLabel', { depth: page.depth })">
            {{ '·'.repeat(page.depth + 1) }}
          </span>
          <a :href="page.url" target="_blank" rel="noopener noreferrer" class="wr-url-list__link">{{ page.url }}</a>
          <span v-if="!page.success" class="wr-badge wr-badge--error">{{ t('knowledge.webResearch.failed') }}</span>
        </li>
      </ul>
    </div>
  </div>
</template>
