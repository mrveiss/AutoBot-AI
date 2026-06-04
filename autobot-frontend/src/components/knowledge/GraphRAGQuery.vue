<template>
  <div class="graph-rag-query">
    <!-- Header -->
    <div class="query-header">
      <h4><Icon name="search-plus" /> {{ $t('knowledge.graphRAG.title') }}</h4>
      <p class="header-description">{{ $t('knowledge.graphRAG.description') }}</p>
      <div v-if="healthStatus" class="health-indicator" :class="healthStatus.status">
        <Icon :name="healthIcon" />
        <span>{{ healthStatus.status }}</span>
      </div>
    </div>

    <!-- Query Section -->
    <div class="query-section">
      <div class="form-group">
        <label for="query-input">
          <Icon name="question-circle" /> {{ $t('knowledge.graphRAG.query') }}
        </label>
        <input
          id="query-input"
          v-model="queryText"
          type="text"
          :placeholder="$t('knowledge.graphRAG.queryPlaceholder')"
          :disabled="isSearching"
          @keyup.enter="executeSearch"
        />
      </div>

      <div class="options-row">
        <div class="form-group compact">
          <label for="start-entity">
            <Icon name="play-circle" /> {{ $t('knowledge.graphRAG.startEntity') }}
            <span class="label-hint">{{ $t('knowledge.graphRAG.startEntityHint') }}</span>
          </label>
          <input
            id="start-entity"
            v-model="startEntity"
            type="text"
            :placeholder="$t('knowledge.graphRAG.startEntityPlaceholder')"
            :disabled="isSearching"
          />
        </div>

        <div class="form-group compact">
          <label for="max-depth">
            <Icon name="layer-group" /> {{ $t('knowledge.graphRAG.maxDepth') }}
          </label>
          <select id="max-depth" v-model.number="maxDepth" :disabled="isSearching">
            <option :value="1">{{ $t('knowledge.graphRAG.hop1') }}</option>
            <option :value="2">{{ $t('knowledge.graphRAG.hop2') }}</option>
            <option :value="3">{{ $t('knowledge.graphRAG.hop3') }}</option>
          </select>
        </div>

        <div class="form-group compact">
          <label for="max-results">
            <Icon name="list-ol" /> {{ $t('knowledge.graphRAG.maxResults') }}
          </label>
          <select id="max-results" v-model.number="maxResults" :disabled="isSearching">
            <option :value="5">5</option>
            <option :value="10">10</option>
            <option :value="15">15</option>
            <option :value="20">20</option>
          </select>
        </div>
      </div>

      <div class="toggle-row">
        <label class="toggle-label">
          <input
            type="checkbox"
            v-model="enableReranking"
            :disabled="isSearching"
          />
          <span class="toggle-text">
            <Icon name="brain" />
            {{ $t('knowledge.graphRAG.enableNeuralReranking') }}
            <span class="toggle-hint">{{ $t('knowledge.graphRAG.rerankingHint') }}</span>
          </span>
        </label>
      </div>

      <div class="search-actions">
        <button
          @click="executeSearch"
          class="action-btn primary"
          :disabled="isSearching || !queryText.trim()"
        >
          <Icon name="spinner" class="animate-spin" v-if="isSearching" />
          <Icon name="search" v-else />
          {{ isSearching ? $t('knowledge.graphRAG.searching') : $t('knowledge.graphRAG.searchGraph') }}
        </button>
        <button
          @click="checkHealth"
          class="action-btn"
          :disabled="isCheckingHealth"
        >
          <Icon name="spinner" class="animate-spin" v-if="isCheckingHealth" />
          <Icon name="heartbeat" v-else />
          {{ $t('knowledge.graphRAG.checkHealth') }}
        </button>
      </div>
    </div>

    <!-- Results Section -->
    <div v-if="searchResults" class="results-section">
      <div class="results-header">
        <h5>
          <Icon name="list" />
          {{ $t('knowledge.graphRAG.resultsFound', { count: searchResults.results.length }) }}
        </h5>
        <div v-if="searchResults.metrics" class="metrics-badges">
          <span class="metric-badge">
            <Icon name="clock" />
            {{ searchResults.metrics.total_time?.toFixed(2) || '0' }}s
          </span>
          <span v-if="searchResults.metrics.graph_traversal_time" class="metric-badge">
            <Icon name="project-diagram" />
            Graph: {{ searchResults.metrics.graph_traversal_time.toFixed(2) }}s
          </span>
        </div>
      </div>

      <div v-if="searchResults.results.length > 0" class="results-list">
        <div
          v-for="(result, index) in searchResults.results"
          :key="index"
          class="result-item"
        >
          <div class="result-header">
            <div class="result-scores">
              <span class="score-badge hybrid" :title="$t('knowledge.graphRAG.hybridScore')">
                {{ formatScore(result.hybrid_score) }}
              </span>
              <span v-if="result.semantic_score" class="score-badge semantic">
                {{ $t('knowledge.graphRAG.semantic') }} {{ formatScore(result.semantic_score) }}
              </span>
              <span v-if="result.keyword_score" class="score-badge keyword">
                {{ $t('knowledge.graphRAG.keyword') }} {{ formatScore(result.keyword_score) }}
              </span>
            </div>
            <span v-if="result.relevance_rank" class="rank-badge">
              #{{ result.relevance_rank }}
            </span>
          </div>
          <div class="result-content">
            <p>{{ truncateContent(result.content) }}</p>
          </div>
          <div v-if="result.source_path" class="result-source">
            <Icon name="file" />
            {{ result.source_path }}
          </div>
          <div v-if="result.metadata" class="result-metadata">
            <span v-for="(value, key) in getDisplayMetadata(result.metadata)" :key="key" class="meta-tag">
              {{ key }}: {{ value }}
            </span>
          </div>
        </div>
      </div>

      <div v-else class="no-results">
        <Icon name="search" />
        <p>{{ $t('knowledge.graphRAG.noResultsFound') }}</p>
        <p class="hint">{{ $t('knowledge.graphRAG.noResultsHint') }}</p>
      </div>
    </div>

    <!-- Error Notification -->
    <div v-if="errorMessage" class="error-notification" role="alert">
      <Icon name="exclamation-circle" />
      <span>{{ errorMessage }}</span>
      <button @click="errorMessage = ''" class="close-btn">
        <Icon name="times" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * GraphRAGQuery - Graph-aware RAG search interface
 *
 * @description Provides an interface for querying the knowledge graph using
 * graph-aware retrieval augmented generation (RAG). Combines semantic search
 * with graph traversal for contextual results.
 *
 * @see Issue #586 - Entity Extraction & Graph RAG Manager GUI
 * @see Issue #6050 - Extract inline fetching to useKnowledgeGraphRAG
 *
 * @author mrveiss
 * @copyright (c) 2025 mrveiss
 */

// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import Icon from '@/components/ui/Icon.vue'
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useKnowledgeGraphRAG } from '@/composables/knowledge/useKnowledgeGraphRAG'

const { t } = useI18n()

// ============================================================================
// Composable
// ============================================================================

const {
  searchResults,
  healthStatus,
  isSearching,
  isCheckingHealth,
  errorMessage,
  searchGraph,
  checkHealth,
} = useKnowledgeGraphRAG()

// ============================================================================
// Local UI state
// ============================================================================

const queryText = ref('')
const startEntity = ref('')
const maxDepth = ref(2)
const maxResults = ref(10)
const enableReranking = ref(true)

// ============================================================================
// Computed
// ============================================================================

const healthIcon = computed(() => {
  if (!healthStatus.value) return 'question-circle'
  switch (healthStatus.value.status) {
    case 'healthy': return 'check-circle'
    case 'degraded': return 'exclamation-triangle'
    case 'unhealthy': return 'times-circle'
    default: return 'question-circle'
  }
})

// ============================================================================
// Methods
// ============================================================================

async function executeSearch(): Promise<void> {
  if (!queryText.value.trim()) {
    errorMessage.value = t('knowledge.graphRAG.errorEnterQuery')
    return
  }

  await searchGraph({
    query: queryText.value.trim(),
    start_entity: startEntity.value.trim() || null,
    max_depth: maxDepth.value,
    max_results: maxResults.value,
    enable_reranking: enableReranking.value,
  })
}

function formatScore(score?: number): string {
  if (score === undefined || score === null) return 'N/A'
  return `${Math.round(score * 100)}%`
}

function truncateContent(content: string, maxLength = 300): string {
  if (!content) return ''
  if (content.length <= maxLength) return content
  return content.substring(0, maxLength) + '...'
}

function getDisplayMetadata(metadata: Record<string, unknown>): Record<string, string> {
  const display: Record<string, string> = {}
  const allowedKeys = ['category', 'type', 'source', 'date']

  for (const key of allowedKeys) {
    if (metadata[key] !== undefined && metadata[key] !== null) {
      display[key] = String(metadata[key])
    }
  }
  return display
}

onMounted(() => {
  checkHealth()
})
</script>

<style scoped>
/* Issue #586: Graph RAG Query styles - Uses design tokens */
.graph-rag-query {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.query-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--spacing-md);
}

.query-header h4 {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin: var(--spacing-0);
  flex: 1;
}

.query-header h4 i {
  color: var(--color-primary);
}

.header-description {
  color: var(--text-secondary);
  font-size: var(--text-sm);
  width: 100%;
  margin-top: calc(-1 * var(--spacing-sm));
}

.health-indicator {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
}

.health-indicator.healthy {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.health-indicator.degraded {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.health-indicator.unhealthy {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.query-section {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  padding: var(--spacing-lg);
  border: 1px solid var(--border-subtle);
}

.form-group {
  margin-bottom: var(--spacing-md);
}

.form-group.compact {
  margin-bottom: var(--spacing-0);
}

.form-group label {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-primary);
  margin-bottom: var(--spacing-sm);
}

.form-group label i {
  color: var(--text-tertiary);
}

.label-hint {
  font-weight: var(--font-normal);
  color: var(--text-tertiary);
  font-size: var(--text-xs);
}

.form-group input,
.form-group select {
  width: 100%;
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  background: var(--bg-input);
  color: var(--text-primary);
  transition: border-color var(--duration-200);
}

.form-group input:focus,
.form-group select:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}
.form-group input:focus-visible,
.form-group select:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.form-group input:disabled,
.form-group select:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.options-row {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-md);
}

.toggle-row {
  margin-bottom: var(--spacing-md);
}

.toggle-label {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  cursor: pointer;
}

.toggle-label input[type="checkbox"] {
  width: auto;
  margin: var(--spacing-0);
}

.toggle-text {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.toggle-text i {
  color: var(--color-primary);
}

.toggle-hint {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.search-actions {
  display: flex;
  gap: var(--spacing-sm);
  justify-content: flex-end;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-lg);
  border: 1px solid var(--border-default);
  background: var(--bg-card);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-primary);
  cursor: pointer;
  transition: all var(--duration-200);
}

.action-btn:hover:not(:disabled) {
  background: var(--bg-hover);
  border-color: var(--border-strong);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-btn.primary {
  background: var(--color-primary);
  color: white;
  border-color: transparent;
}

.action-btn.primary:hover:not(:disabled) {
  box-shadow: var(--shadow-primary);
}

.results-section {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  padding: var(--spacing-lg);
  border: 1px solid var(--border-subtle);
}

.results-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-md);
  padding-bottom: var(--spacing-md);
  border-bottom: 1px solid var(--border-subtle);
}

.results-header h5 {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin: var(--spacing-0);
}

.metrics-badges {
  display: flex;
  gap: var(--spacing-sm);
}

.metric-badge {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-xs) var(--spacing-sm);
  background: var(--bg-secondary);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.results-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.result-item {
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  border: 1px solid var(--border-subtle);
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-sm);
}

.result-scores {
  display: flex;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
}

.score-badge {
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
}

.score-badge.hybrid {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.score-badge.semantic {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.score-badge.keyword {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.rank-badge {
  padding: var(--spacing-xs) var(--spacing-sm);
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-weight: var(--font-bold);
  color: var(--text-secondary);
}

.result-content p {
  font-size: var(--text-sm);
  color: var(--text-primary);
  line-height: 1.6;
  margin: var(--spacing-0);
}

.result-source {
  margin-top: var(--spacing-sm);
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.result-metadata {
  margin-top: var(--spacing-sm);
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
}

.meta-tag {
  padding: 2px var(--spacing-sm);
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.no-results {
  text-align: center;
  padding: var(--spacing-xl);
  color: var(--text-secondary);
}

.no-results i {
  font-size: 2rem;
  margin-bottom: var(--spacing-md);
  color: var(--text-tertiary);
}

.no-results p {
  margin: var(--spacing-0);
}

.no-results .hint {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
  margin-top: var(--spacing-sm);
}

.error-notification {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  border-left: 4px solid var(--color-error);
  border-radius: var(--radius-md);
  color: var(--color-error-text);
}

.error-notification i.fa-exclamation-circle {
  color: var(--color-error);
}

.error-notification span {
  flex: 1;
  font-size: var(--text-sm);
}

.close-btn {
  background: none;
  border: none;
  padding: var(--spacing-xs);
  cursor: pointer;
  color: var(--text-secondary);
  opacity: 0.7;
  transition: opacity var(--duration-200);
}

.close-btn:hover {
  opacity: 1;
}

@media (max-width: 768px) {
  .options-row {
    grid-template-columns: 1fr;
  }

  .search-actions {
    flex-direction: column;
  }

  .results-header {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-sm);
  }

  .metrics-badges {
    width: 100%;
  }
}
</style>
