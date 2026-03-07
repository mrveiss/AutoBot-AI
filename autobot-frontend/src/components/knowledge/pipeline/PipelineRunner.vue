<!-- AutoBot - Knowledge Graph Pipeline (Issue #759) -->
<template>
  <div class="pipeline-runner">
    <div class="runner-header">
      <h4><i class="fas fa-play-circle"></i> {{ $t('knowledge.pipeline.runner.title') }}</h4>
      <p class="header-description">
        {{ $t('knowledge.pipeline.runner.description') }}
      </p>
    </div>

    <!-- Pipeline Form -->
    <form class="pipeline-form" @submit.prevent="handleSubmit">
      <div class="form-group">
        <label for="document-id">{{ $t('knowledge.pipeline.runner.documentId') }}</label>
        <input
          id="document-id"
          v-model="form.document_id"
          type="text"
          :placeholder="$t('knowledge.pipeline.runner.documentIdPlaceholder')"
          :class="['form-input', { 'input-error': documentIdError }]"
          @input="documentIdError = ''"
        />
        <p v-if="documentIdError" class="field-error">
          {{ documentIdError }}
        </p>
      </div>

      <div class="form-group">
        <label for="pipeline-name">{{ $t('knowledge.pipeline.runner.pipeline') }}</label>
        <select
          id="pipeline-name"
          v-model="form.pipeline_name"
          class="form-input"
        >
          <option value="default">{{ $t('knowledge.pipeline.runner.pipelineDefault') }}</option>
          <option value="extract_only">{{ $t('knowledge.pipeline.runner.pipelineExtractOnly') }}</option>
          <option value="cognify_only">{{ $t('knowledge.pipeline.runner.pipelineCognifyOnly') }}</option>
          <option value="summarize_only">{{ $t('knowledge.pipeline.runner.pipelineSummarizeOnly') }}</option>
        </select>
      </div>

      <div class="form-group">
        <div class="config-label-row">
          <label for="config-json">
            {{ $t('knowledge.pipeline.runner.configurationJson') }}
            <span class="label-hint">{{ $t('knowledge.pipeline.runner.optional') }}</span>
          </label>
          <button
            type="button"
            class="config-toggle-btn"
            @click="showConfigEditor = !showConfigEditor"
          >
            <i :class="showConfigEditor ? 'fas fa-code' : 'fas fa-sliders-h'"></i>
            {{ showConfigEditor ? $t('knowledge.pipeline.runner.jsonEditor') : $t('knowledge.pipeline.runner.visualConfig') }}
          </button>
        </div>
        <PipelineConfig
          v-if="!showConfigEditor"
          @config-change="applyVisualConfig"
        />
        <template v-else>
          <textarea
            id="config-json"
            v-model="configJson"
            class="form-input config-editor"
            rows="6"
            placeholder='{"batch_size": 10, "confidence_threshold": 0.7}'
            spellcheck="false"
          />
          <p v-if="configError" class="field-error">
            {{ configError }}
          </p>
        </template>
      </div>

      <button
        type="submit"
        class="submit-btn"
        :disabled="loading"
      >
        <i :class="loading ? 'fas fa-spinner fa-spin' : 'fas fa-play'"></i>
        {{ loading ? $t('knowledge.pipeline.runner.running') : $t('knowledge.pipeline.runner.runPipeline') }}
      </button>
    </form>

    <!-- Error Display -->
    <div v-if="error" class="error-banner">
      <i class="fas fa-exclamation-triangle"></i>
      <span>{{ error }}</span>
      <button class="dismiss-btn" :aria-label="$t('knowledge.pipeline.runner.dismissError')" @click="clearError">
        <i class="fas fa-times"></i>
      </button>
    </div>

    <!-- Result Display -->
    <div v-if="result" class="result-panel">
      <div class="result-header">
        <h5>
          <i class="fas fa-check-circle"></i>
          {{ $t('knowledge.pipeline.runner.pipelineComplete') }}
        </h5>
        <span class="result-duration">
          {{ result.duration_seconds.toFixed(1) }}s
        </span>
      </div>

      <div class="result-stats">
        <div class="result-stat">
          <span class="stat-value">
            {{ result.stats.chunks_processed }}
          </span>
          <span class="stat-label">{{ $t('knowledge.pipeline.runner.chunks') }}</span>
        </div>
        <div class="result-stat">
          <span class="stat-value">
            {{ result.stats.entities_extracted }}
          </span>
          <span class="stat-label">{{ $t('knowledge.pipeline.runner.entities') }}</span>
        </div>
        <div class="result-stat">
          <span class="stat-value">
            {{ result.stats.relationships_created }}
          </span>
          <span class="stat-label">{{ $t('knowledge.pipeline.runner.relationships') }}</span>
        </div>
        <div class="result-stat">
          <span class="stat-value">
            {{ result.stats.events_detected }}
          </span>
          <span class="stat-label">{{ $t('knowledge.pipeline.runner.events') }}</span>
        </div>
        <div class="result-stat">
          <span class="stat-value">
            {{ result.stats.summaries_generated }}
          </span>
          <span class="stat-label">{{ $t('knowledge.pipeline.runner.summaries') }}</span>
        </div>
      </div>

      <div class="result-meta">
        <span>{{ $t('knowledge.pipeline.runner.pipelineLabel') }} {{ result.pipeline_id }}</span>
        <span>{{ $t('knowledge.pipeline.runner.statusLabel') }} {{ result.status }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, reactive } from 'vue'
import {
  useKnowledgeGraph,
  type PipelineResult,
} from '@/composables/useKnowledgeGraph'
import { createLogger } from '@/utils/debugUtils'
import PipelineConfig from './PipelineConfig.vue'
import { useI18n } from 'vue-i18n'

const logger = createLogger('PipelineRunner')
const { t } = useI18n()
const { runPipeline, loading, error, clearError } = useKnowledgeGraph()

const form = reactive({
  document_id: '',
  pipeline_name: 'default',
})

const showConfigEditor = ref(true)
const configJson = ref('')
const configError = ref('')
const documentIdError = ref('')
const result = ref<PipelineResult | null>(null)

function applyVisualConfig(config: Record<string, unknown>): void {
  configJson.value = JSON.stringify(config, null, 2)
  configError.value = ''
}

function parseConfig(): Record<string, unknown> | null {
  if (!configJson.value.trim()) return {}
  try {
    configError.value = ''
    return JSON.parse(configJson.value)
  } catch {
    configError.value = t('knowledge.pipeline.runner.invalidJson')
    return null
  }
}

async function handleSubmit(): Promise<void> {
  if (!form.document_id.trim()) {
    documentIdError.value = t('knowledge.pipeline.runner.documentIdRequired')
    return
  }

  const config = parseConfig()
  if (config === null) return

  result.value = null
  const pipelineResult = await runPipeline({
    document_id: form.document_id,
    pipeline_name: form.pipeline_name,
    config: config,
  })

  if (pipelineResult) {
    result.value = pipelineResult
    logger.info('Pipeline result:', pipelineResult.pipeline_id)
  }
}
</script>

<style scoped>
.pipeline-runner {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
  padding: var(--spacing-lg);
}

.runner-header h4 {
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin: 0;
}

.runner-header h4 i {
  color: var(--color-primary);
}

.header-description {
  color: var(--text-secondary);
  font-size: var(--text-sm);
  margin-top: var(--spacing-xs);
}

/* Form */
.pipeline-form {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.form-group label {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.label-hint {
  font-weight: var(--font-normal);
  color: var(--text-tertiary);
  font-size: var(--text-xs);
}

.form-input {
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: var(--text-sm);
  font-family: inherit;
  transition: border-color var(--duration-200);
}

.form-input:focus {
  outline: none;
  border-color: var(--color-primary);
}

.config-label-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.config-toggle-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-xs) var(--spacing-sm);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  cursor: pointer;
}

.config-toggle-btn:hover {
  color: var(--text-primary);
  border-color: var(--border-strong);
}

.config-editor {
  font-family: 'Fira Code', 'Cascadia Code', monospace;
  font-size: var(--text-xs);
  resize: vertical;
  min-height: 100px;
}

.input-error {
  border-color: var(--color-error) !important;
}

.field-error {
  color: var(--color-error);
  font-size: var(--text-xs);
  margin: 0;
}

.submit-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-lg);
  background: var(--color-primary);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  cursor: pointer;
  transition: opacity var(--duration-200);
  align-self: flex-start;
}

.submit-btn:hover:not(:disabled) {
  opacity: 0.9;
}

.submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Error Banner */
.error-banner {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-error-bg);
  border: 1px solid var(--color-error);
  border-radius: var(--radius-md);
  color: var(--color-error);
  font-size: var(--text-sm);
}

.error-banner span {
  flex: 1;
}

.dismiss-btn {
  background: none;
  border: none;
  color: var(--color-error);
  cursor: pointer;
  padding: var(--spacing-xs);
}

/* Result Panel */
.result-panel {
  background: var(--bg-card);
  border: 1px solid var(--color-success);
  border-radius: var(--radius-lg);
  padding: var(--spacing-lg);
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-md);
}

.result-header h5 {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-success);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin: 0;
}

.result-duration {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  background: var(--bg-secondary);
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--radius-full);
}

.result-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-md);
}

.result-stat {
  text-align: center;
  padding: var(--spacing-sm);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
}

.result-stat .stat-value {
  display: block;
  font-size: var(--text-2xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
}

.result-stat .stat-label {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.result-meta {
  display: flex;
  gap: var(--spacing-lg);
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

@media (max-width: 768px) {
  .result-stats {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
