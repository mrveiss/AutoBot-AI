<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2026 mrveiss -->
<!-- Author: mrveiss -->
<!-- ExtractTab — "Get Data" tab: LLM-powered schema-driven data extraction (MVA-344) -->

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useWebResearch } from '@/composables/knowledge/useWebResearch'
import type { ExtractResponse } from '@/composables/knowledge/useWebResearch'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ExtractTab')
const { t } = useI18n()
const { extractData } = useWebResearch()

// ── State ──────────────────────────────────────────────────────────────────

const url = ref('')
const schemaText = ref('{\n  "type": "object",\n  "properties": {\n    "title": { "type": "string" },\n    "summary": { "type": "string" }\n  }\n}')
const render = ref<'auto' | 'fast' | 'playwright'>('auto')
const ingest = ref(false)

const isLoading = ref(false)
const errorMsg = ref<string | null>(null)
const schemaError = ref<string | null>(null)
const result = ref<ExtractResponse | null>(null)

// ── Actions ────────────────────────────────────────────────────────────────

function parseSchema(): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(schemaText.value)
    schemaError.value = null
    return parsed as Record<string, unknown>
  } catch (e) {
    schemaError.value = e instanceof Error ? e.message : 'Invalid JSON'
    return null
  }
}

async function submit() {
  if (!url.value.trim()) return
  const schema = parseSchema()
  if (!schema) return

  isLoading.value = true
  errorMsg.value = null
  result.value = null

  try {
    result.value = await extractData({
      url: url.value.trim(),
      schema,
      render: render.value,
      ingest: ingest.value,
    })
  } catch (err: unknown) {
    logger.error('Get Data failed', err)
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
  <div class="extract-tab">
    <!-- Form -->
    <form class="wr-form" @submit.prevent="submit">
      <div class="wr-form-row">
        <label class="wr-label" for="extract-url">{{ t('knowledge.webResearch.extract.urlLabel') }}</label>
        <input
          id="extract-url"
          v-model="url"
          type="url"
          class="wr-input"
          :placeholder="t('knowledge.webResearch.extract.urlPlaceholder')"
          required
          :disabled="isLoading"
          :aria-label="t('knowledge.webResearch.extract.urlLabel')"
        />
      </div>

      <div class="wr-form-row">
        <label class="wr-label" for="extract-schema">{{ t('knowledge.webResearch.extract.schemaLabel') }}</label>
        <textarea
          id="extract-schema"
          v-model="schemaText"
          class="wr-textarea"
          rows="8"
          :disabled="isLoading"
          :aria-label="t('knowledge.webResearch.extract.schemaLabel')"
          spellcheck="false"
        />
        <p v-if="schemaError" class="wr-field-error" role="alert">{{ schemaError }}</p>
      </div>

      <div class="wr-form-row wr-form-row--inline">
        <div class="wr-field">
          <label class="wr-label" for="extract-render">{{ t('knowledge.webResearch.renderLabel') }}</label>
          <select id="extract-render" v-model="render" class="wr-select" :disabled="isLoading">
            <option value="auto">{{ t('knowledge.webResearch.renderAuto') }}</option>
            <option value="fast">{{ t('knowledge.webResearch.renderFast') }}</option>
            <option value="playwright">{{ t('knowledge.webResearch.renderPlaywright') }}</option>
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
        <button type="submit" class="wr-btn wr-btn--primary" :disabled="isLoading || !url.trim() || !!schemaError">
          <span v-if="isLoading" class="wr-spinner" aria-hidden="true" />
          {{ isLoading ? t('knowledge.webResearch.extracting') : t('knowledge.webResearch.extract.submitLabel') }}
        </button>
        <button v-if="result || errorMsg" type="button" class="wr-btn wr-btn--ghost" @click="reset">
          {{ t('knowledge.webResearch.reset') }}
        </button>
      </div>
    </form>

    <!-- Loading skeleton -->
    <div v-if="isLoading" class="wr-skeleton-block" aria-label="Loading" aria-busy="true">
      <div class="wr-skeleton wr-skeleton--title" />
      <div v-for="n in 5" :key="n" class="wr-skeleton wr-skeleton--line" />
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
          d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
      </svg>
      <p>{{ t('knowledge.webResearch.extract.emptyState') }}</p>
    </div>

    <!-- Result: JSON viewer -->
    <div v-else class="wr-result">
      <div class="wr-result__header">
        <h3 class="wr-result__title">{{ t('knowledge.webResearch.extract.resultTitle') }}</h3>
        <span v-if="result.schema_valid" class="wr-badge wr-badge--success">{{ t('knowledge.webResearch.schemaValid') }}</span>
        <span v-else class="wr-badge wr-badge--warning">{{ t('knowledge.webResearch.schemaInvalid') }}</span>
      </div>
      <div class="wr-result__url">
        <a :href="result.url" target="_blank" rel="noopener noreferrer">{{ result.url }}</a>
      </div>
      <pre class="wr-result__content wr-result__content--json">{{ JSON.stringify(result.data, null, 2) }}</pre>
    </div>
  </div>
</template>
