<!-- AutoBot - Knowledge Graph Pipeline (Issue #759) -->
<template>
  <div class="pipeline-runner">
    <div class="runner-header">
      <h4><i class="fas fa-play-circle"></i> Run Pipeline</h4>
      <p class="header-description">
        Process a document through the knowledge graph extraction pipeline
      </p>
    </div>

    <!-- Pipeline Form -->
    <form class="pipeline-form" @submit.prevent="handleSubmit">
      <div class="form-group">
        <label for="document-id">Document ID</label>
        <input
          id="document-id"
          v-model="form.document_id"
          type="text"
          placeholder="Enter document ID to process"
          :class="['form-input', { 'input-error': documentIdError }]"
          @input="documentIdError = ''"
        />
        <p v-if="documentIdError" class="field-error">
          {{ documentIdError }}
        </p>
      </div>

      <div class="form-group">
        <label for="pipeline-name">Pipeline</label>
        <select
          id="pipeline-name"
          v-model="form.pipeline_name"
          class="form-input"
        >
          <option value="default">Default (All Stages)</option>
          <option value="extract_only">Extract Only</option>
          <option value="cognify_only">Cognify Only</option>
          <option value="summarize_only">Summarize Only</option>
        </select>
      </div>

      <div class="form-group">
        <label for="config-json">
          Configuration (JSON)
          <span class="label-hint">Optional</span>
        </label>
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
      </div>

      <button
        type="submit"
        class="submit-btn"
        :disabled="loading"
      >
        <i :class="loading ? 'fas fa-spinner fa-spin' : 'fas fa-play'"></i>
        {{ loading ? 'Running...' : 'Run Pipeline' }}
      </button>
    </form>

    <!-- Error Display -->
    <div v-if="error" class="error-banner">
      <i class="fas fa-exclamation-triangle"></i>
      <span>{{ error }}</span>
      <button class="dismiss-btn" @click="clearError">
        <i class="fas fa-times"></i>
      </button>
    </div>

    <!-- Result Display -->
    <div v-if="result" class="result-panel">
      <div class="result-header">
        <h5>
          <i class="fas fa-check-circle"></i>
          Pipeline Complete
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
          <span class="stat-label">Chunks</span>
        </div>
        <div class="result-stat">
          <span class="stat-value">
            {{ result.stats.entities_extracted }}
          </span>
          <span class="stat-label">Entities</span>
        </div>
        <div class="result-stat">
          <span class="stat-value">
            {{ result.stats.relationships_created }}
          </span>
          <span class="stat-label">Relationships</span>
        </div>
        <div class="result-stat">
          <span class="stat-value">
            {{ result.stats.events_detected }}
          </span>
          <span class="stat-label">Events</span>
        </div>
        <div class="result-stat">
          <span class="stat-value">
            {{ result.stats.summaries_generated }}
          </span>
          <span class="stat-label">Summaries</span>
        </div>
      </div>

      <div class="result-meta">
        <span>Pipeline: {{ result.pipeline_id }}</span>
        <span>Status: {{ result.status }}</span>
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

const logger = createLogger('PipelineRunner')
const { runPipeline, loading, error, clearError } = useKnowledgeGraph()

const form = reactive({
  document_id: '',
  pipeline_name: 'default',
})

const configJson = ref('')
const configError = ref('')
const documentIdError = ref('')
const result = ref<PipelineResult | null>(null)

function parseConfig(): Record<string, unknown> | null {
  if (!configJson.value.trim()) return {}
  try {
    configError.value = ''
    return JSON.parse(configJson.value)
  } catch (err) {
    configError.value = 'Invalid JSON configuration'
    return null
  }
}

async function handleSubmit(): Promise<void> {
  if (!form.document_id.trim()) {
    documentIdError.value = 'Document ID is required'
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
