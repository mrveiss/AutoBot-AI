<template>
  <div class="graph-rag-query">
    <!-- Header -->
    <div class="query-header">
      <h4><i class="fas fa-search-plus"></i> Graph-RAG Query</h4>
      <p class="header-description">Search knowledge using graph-aware retrieval</p>
      <div v-if="healthStatus" class="health-indicator" :class="healthStatus.status">
        <i :class="healthIcon"></i>
        <span>{{ healthStatus.status }}</span>
      </div>
    </div>

    <!-- Query Section -->
    <div class="query-section">
      <div class="form-group">
        <label for="query-input">
          <i class="fas fa-question-circle"></i> Query
        </label>
        <input
          id="query-input"
          v-model="queryText"
          type="text"
          placeholder="Ask a question about your knowledge graph..."
          :disabled="isSearching"
          @keyup.enter="executeSearch"
        />
      </div>

      <div class="options-row">
        <div class="form-group compact">
          <label for="start-entity">
            <i class="fas fa-play-circle"></i> Start Entity
            <span class="label-hint">(optional)</span>
          </label>
          <input
            id="start-entity"
            v-model="startEntity"
            type="text"
            placeholder="Entity name to start from..."
            :disabled="isSearching"
          />
        </div>

        <div class="form-group compact">
          <label for="max-depth">
            <i class="fas fa-layer-group"></i> Max Depth
          </label>
          <select id="max-depth" v-model.number="maxDepth" :disabled="isSearching">
            <option :value="1">1 Hop</option>
            <option :value="2">2 Hops</option>
            <option :value="3">3 Hops</option>
          </select>
        </div>

        <div class="form-group compact">
          <label for="max-results">
            <i class="fas fa-list-ol"></i> Max Results
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
            <i class="fas fa-brain"></i>
            Enable Neural Reranking
            <span class="toggle-hint">(slower but more accurate)</span>
          </span>
        </label>
      </div>

      <div class="search-actions">
        <button
          @click="executeSearch"
          class="action-btn primary"
          :disabled="isSearching || !queryText.trim()"
        >
          <i v-if="isSearching" class="fas fa-spinner fa-spin"></i>
          <i v-else class="fas fa-search"></i>
          {{ isSearching ? 'Searching...' : 'Search Graph' }}
        </button>
        <button
          @click="checkHealth"
          class="action-btn"
          :disabled="isCheckingHealth"
        >
          <i v-if="isCheckingHealth" class="fas fa-spinner fa-spin"></i>
          <i v-else class="fas fa-heartbeat"></i>
          Check Health
        </button>
      </div>
    </div>

    <!-- Results Section -->
    <div v-if="searchResults" class="results-section">
      <div class="results-header">
        <h5>
          <i class="fas fa-list"></i>
          {{ searchResults.results.length }} Results Found
        </h5>
        <div v-if="searchResults.metrics" class="metrics-badges">
          <span class="metric-badge">
            <i class="fas fa-clock"></i>
            {{ searchResults.metrics.total_time?.toFixed(2) || '0' }}s
          </span>
          <span v-if="searchResults.metrics.graph_traversal_time" class="metric-badge">
            <i class="fas fa-project-diagram"></i>
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
              <span class="score-badge hybrid" :title="'Hybrid Score'">
                {{ formatScore(result.hybrid_score) }}
              </span>
              <span v-if="result.semantic_score" class="score-badge semantic">
                Semantic: {{ formatScore(result.semantic_score) }}
              </span>
              <span v-if="result.keyword_score" class="score-badge keyword">
                Keyword: {{ formatScore(result.keyword_score) }}
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
            <i class="fas fa-file"></i>
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
        <i class="fas fa-search"></i>
        <p>No results found for your query.</p>
        <p class="hint">Try adjusting your search terms or increasing the depth.</p>
      </div>
    </div>

    <!-- Error Notification -->
    <div v-if="errorMessage" class="error-notification" role="alert">
      <i class="fas fa-exclamation-circle"></i>
      <span>{{ errorMessage }}</span>
      <button @click="errorMessage = ''" class="close-btn">
        <i class="fas fa-times"></i>
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
 *
 * @author mrveiss
 * @copyright (c) 2025 mrveiss
 */

// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, computed, onMounted } from 'vue'
import apiClient from '@/utils/ApiClient'
import { parseApiResponse } from '@/utils/apiResponseHelpers'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('GraphRAGQuery')

// ============================================================================
// Types
// ============================================================================

interface SearchResult {
  content: string
  metadata?: Record<string, unknown>
  semantic_score?: number
  keyword_score?: number
  hybrid_score?: number
  relevance_rank?: number
  source_path?: string
}

interface SearchMetrics {
  total_time?: number
  graph_traversal_time?: number
  semantic_search_time?: number
  reranking_time?: number
}

interface SearchResponse {
  success: boolean
  results: SearchResult[]
  metrics: SearchMetrics
  request_id: string
}

interface HealthStatus {
  status: 'healthy' | 'degraded' | 'unhealthy'
  components: Record<string, string>
  timestamp: string
}

// ============================================================================
// State
// ============================================================================

const queryText = ref('')
const startEntity = ref('')
const maxDepth = ref(2)
const maxResults = ref(10)
const enableReranking = ref(true)
const isSearching = ref(false)
const isCheckingHealth = ref(false)
const errorMessage = ref('')
const searchResults = ref<SearchResponse | null>(null)
const healthStatus = ref<HealthStatus | null>(null)

// ============================================================================
// Computed
// ============================================================================

const healthIcon = computed(() => {
  if (!healthStatus.value) return 'fas fa-question-circle'
  switch (healthStatus.value.status) {
    case 'healthy': return 'fas fa-check-circle'
    case 'degraded': return 'fas fa-exclamation-triangle'
    case 'unhealthy': return 'fas fa-times-circle'
    default: return 'fas fa-question-circle'
  }
})

// ============================================================================
// Methods
// ============================================================================

async function executeSearch(): Promise<void> {
  if (!queryText.value.trim()) {
    errorMessage.value = 'Please enter a search query'
    return
  }

  isSearching.value = true
  errorMessage.value = ''
  searchResults.value = null

  try {
    logger.info(`Executing Graph-RAG search: "${queryText.value.substring(0, 50)}..."`)

    const response = await apiClient.post('/api/graph-rag/search', {
      query: queryText.value.trim(),
      start_entity: startEntity.value.trim() || null,
      max_depth: maxDepth.value,
      max_results: maxResults.value,
      enable_reranking: enableReranking.value
    })

    const parsedResponse = await parseApiResponse(response)
    searchResults.value = parsedResponse?.data || parsedResponse

    logger.info(`Search complete: ${searchResults.value?.results?.length || 0} results`)
  } catch (error) {
    logger.error('Graph-RAG search failed:', error)
    errorMessage.value = error instanceof Error ? error.message : 'Search failed'
  } finally {
    isSearching.value = false
  }
}

async function checkHealth(): Promise<void> {
  isCheckingHealth.value = true

  try {
    const response = await apiClient.get('/api/graph-rag/health')
    const parsedResponse = await parseApiResponse(response)
    healthStatus.value = parsedResponse?.data || parsedResponse
    logger.info(`Health check: ${healthStatus.value?.status}`)
  } catch (error) {
    logger.error('Health check failed:', error)
    healthStatus.value = {
      status: 'unhealthy',
      components: {},
      timestamp: new Date().toISOString()
    }
  } finally {
    isCheckingHealth.value = false
  }
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
  margin: 0;
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
  margin-bottom: 0;
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
  margin: 0;
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
  background: linear-gradient(135deg, var(--color-primary), var(--color-primary-hover));
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
  margin: 0;
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
  margin: 0;
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
  margin: 0;
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
