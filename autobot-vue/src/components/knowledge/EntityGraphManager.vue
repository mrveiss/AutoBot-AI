<template>
  <div class="entity-graph-manager">
    <!-- Header -->
    <div class="manager-header">
      <div class="header-content">
        <h3><i class="fas fa-sitemap"></i> Entity Graph Manager</h3>
        <p class="header-description">
          Extract entities from text and query the knowledge graph using AI-powered retrieval
        </p>
      </div>
      <div class="header-actions">
        <button @click="refreshStats" class="action-btn" :disabled="isLoadingStats">
          <i :class="isLoadingStats ? 'fas fa-spinner fa-spin' : 'fas fa-sync'"></i>
          Refresh Stats
        </button>
        <router-link to="/knowledge/graph" class="action-btn">
          <i class="fas fa-project-diagram"></i>
          View Graph
        </router-link>
      </div>
    </div>

    <!-- Tab Navigation -->
    <div class="tab-navigation">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        :class="['tab-button', { active: activeTab === tab.id }]"
        @click="activeTab = tab.id"
      >
        <i :class="tab.icon"></i>
        {{ tab.label }}
      </button>
    </div>

    <!-- Tab Content -->
    <div class="tab-content">
      <!-- Extract Tab -->
      <div v-if="activeTab === 'extract'" class="tab-panel">
        <EntityExtractor
          @extraction-complete="handleExtractionComplete"
          @view-graph="handleViewGraph"
        />
      </div>

      <!-- Query Tab -->
      <div v-if="activeTab === 'query'" class="tab-panel">
        <GraphRAGQuery />
      </div>

      <!-- Statistics Tab -->
      <div v-if="activeTab === 'stats'" class="tab-panel">
        <div class="stats-section">
          <h4><i class="fas fa-chart-bar"></i> Graph Statistics</h4>

          <div v-if="isLoadingStats" class="loading-state">
            <i class="fas fa-spinner fa-spin"></i>
            <span>Loading statistics...</span>
          </div>

          <div v-else-if="statsError" class="error-state">
            <i class="fas fa-exclamation-triangle"></i>
            <span>{{ statsError }}</span>
            <button @click="refreshStats" class="retry-btn">
              <i class="fas fa-redo"></i> Retry
            </button>
          </div>

          <div v-else class="stats-grid">
            <div class="stat-card">
              <div class="stat-icon">
                <i class="fas fa-circle"></i>
              </div>
              <div class="stat-info">
                <span class="stat-value">{{ graphStats.entityCount }}</span>
                <span class="stat-label">Total Entities</span>
              </div>
            </div>

            <div class="stat-card">
              <div class="stat-icon">
                <i class="fas fa-link"></i>
              </div>
              <div class="stat-info">
                <span class="stat-value">{{ graphStats.relationCount }}</span>
                <span class="stat-label">Total Relations</span>
              </div>
            </div>

            <div class="stat-card">
              <div class="stat-icon">
                <i class="fas fa-tags"></i>
              </div>
              <div class="stat-info">
                <span class="stat-value">{{ graphStats.entityTypes }}</span>
                <span class="stat-label">Entity Types</span>
              </div>
            </div>

            <div class="stat-card">
              <div class="stat-icon">
                <i class="fas fa-exchange-alt"></i>
              </div>
              <div class="stat-info">
                <span class="stat-value">{{ graphStats.relationTypes }}</span>
                <span class="stat-label">Relation Types</span>
              </div>
            </div>
          </div>

          <!-- Service Health -->
          <div class="health-section">
            <h5><i class="fas fa-heartbeat"></i> Service Health</h5>

            <div class="health-cards">
              <div class="health-card" :class="extractionHealth.status">
                <div class="health-header">
                  <span class="health-name">Entity Extraction</span>
                  <span class="health-status">{{ extractionHealth.status }}</span>
                </div>
                <div class="health-components">
                  <div
                    v-for="(status, component) in extractionHealth.components"
                    :key="component"
                    class="component-status"
                  >
                    <i :class="getStatusIcon(status)"></i>
                    <span>{{ formatComponentName(component) }}</span>
                  </div>
                </div>
              </div>

              <div class="health-card" :class="graphRagHealth.status">
                <div class="health-header">
                  <span class="health-name">Graph-RAG Service</span>
                  <span class="health-status">{{ graphRagHealth.status }}</span>
                </div>
                <div class="health-components">
                  <div
                    v-for="(status, component) in graphRagHealth.components"
                    :key="component"
                    class="component-status"
                  >
                    <i :class="getStatusIcon(status)"></i>
                    <span>{{ formatComponentName(component) }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Recent Activity -->
          <div v-if="recentExtractions.length > 0" class="activity-section">
            <h5><i class="fas fa-history"></i> Recent Extractions</h5>
            <div class="activity-list">
              <div
                v-for="extraction in recentExtractions"
                :key="extraction.request_id"
                class="activity-item"
              >
                <div class="activity-main">
                  <span class="activity-id">{{ extraction.conversation_id }}</span>
                  <span class="activity-stats">
                    {{ extraction.entities_created }} entities,
                    {{ extraction.relations_created }} relations
                  </span>
                </div>
                <span :class="['activity-status', extraction.success ? 'success' : 'error']">
                  {{ extraction.success ? 'Success' : 'Failed' }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * EntityGraphManager - Main view for entity extraction and graph RAG management
 *
 * @description Provides a unified interface for extracting entities from text,
 * querying the knowledge graph, and viewing statistics about the graph.
 *
 * @see Issue #586 - Entity Extraction & Graph RAG Manager GUI
 *
 * @author mrveiss
 * @copyright (c) 2025 mrveiss
 */

// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import apiClient from '@/utils/ApiClient'
import { parseApiResponse } from '@/utils/apiResponseHelpers'
import { createLogger } from '@/utils/debugUtils'
import EntityExtractor from './EntityExtractor.vue'
import GraphRAGQuery from './GraphRAGQuery.vue'

const logger = createLogger('EntityGraphManager')
const router = useRouter()

// ============================================================================
// Types
// ============================================================================

interface Tab {
  id: string
  label: string
  icon: string
}

interface GraphStats {
  entityCount: number
  relationCount: number
  entityTypes: number
  relationTypes: number
}

interface HealthStatus {
  status: 'healthy' | 'degraded' | 'unhealthy' | 'unknown'
  components: Record<string, string>
}

interface ExtractionResult {
  success: boolean
  conversation_id: string
  entities_created: number
  relations_created: number
  request_id: string
}

// ============================================================================
// State
// ============================================================================

const tabs: Tab[] = [
  { id: 'extract', label: 'Extract', icon: 'fas fa-brain' },
  { id: 'query', label: 'Query', icon: 'fas fa-search-plus' },
  { id: 'stats', label: 'Statistics', icon: 'fas fa-chart-bar' }
]

const activeTab = ref('extract')
const isLoadingStats = ref(false)
const statsError = ref('')

const graphStats = reactive<GraphStats>({
  entityCount: 0,
  relationCount: 0,
  entityTypes: 0,
  relationTypes: 0
})

const extractionHealth = reactive<HealthStatus>({
  status: 'unknown',
  components: {}
})

const graphRagHealth = reactive<HealthStatus>({
  status: 'unknown',
  components: {}
})

const recentExtractions = ref<ExtractionResult[]>([])

// ============================================================================
// Methods
// ============================================================================

async function refreshStats(): Promise<void> {
  isLoadingStats.value = true
  statsError.value = ''

  try {
    await Promise.all([
      fetchGraphStats(),
      fetchExtractionHealth(),
      fetchGraphRagHealth()
    ])
    logger.info('Stats refreshed successfully')
  } catch (error) {
    logger.error('Failed to refresh stats:', error)
    statsError.value = error instanceof Error ? error.message : 'Failed to load statistics'
  } finally {
    isLoadingStats.value = false
  }
}

async function fetchGraphStats(): Promise<void> {
  try {
    const response = await apiClient.get('/api/knowledge/unified/graph?max_facts=0')
    const data = await parseApiResponse(response)
    const graphData = data?.data || data

    if (graphData?.entities) {
      graphStats.entityCount = graphData.entities.length
      const entityTypeSet = new Set(graphData.entities.map((e: { type: string }) => e.type))
      graphStats.entityTypes = entityTypeSet.size
    }

    if (graphData?.relations) {
      graphStats.relationCount = graphData.relations.length
      const relTypeSet = new Set(graphData.relations.map((r: { type: string }) => r.type))
      graphStats.relationTypes = relTypeSet.size
    }
  } catch (error) {
    logger.warn('Could not fetch graph stats:', error)
  }
}

async function fetchExtractionHealth(): Promise<void> {
  try {
    const response = await apiClient.get('/api/entities/extract/health')
    const data = await parseApiResponse(response)
    const healthData = data?.data || data

    extractionHealth.status = healthData?.status || 'unknown'
    extractionHealth.components = healthData?.components || {}
  } catch (error) {
    logger.warn('Could not fetch extraction health:', error)
    extractionHealth.status = 'unhealthy'
    extractionHealth.components = {}
  }
}

async function fetchGraphRagHealth(): Promise<void> {
  try {
    const response = await apiClient.get('/api/graph-rag/health')
    const data = await parseApiResponse(response)
    const healthData = data?.data || data

    graphRagHealth.status = healthData?.status || 'unknown'
    graphRagHealth.components = healthData?.components || {}
  } catch (error) {
    logger.warn('Could not fetch graph-rag health:', error)
    graphRagHealth.status = 'unhealthy'
    graphRagHealth.components = {}
  }
}

function handleExtractionComplete(result: ExtractionResult): void {
  recentExtractions.value.unshift(result)
  if (recentExtractions.value.length > 5) {
    recentExtractions.value.pop()
  }
  refreshStats()
}

function handleViewGraph(): void {
  router.push('/knowledge/graph')
}

function getStatusIcon(status: string): string {
  switch (status) {
    case 'healthy': return 'fas fa-check-circle text-success'
    case 'degraded': return 'fas fa-exclamation-triangle text-warning'
    case 'unavailable':
    case 'unhealthy': return 'fas fa-times-circle text-error'
    default: return 'fas fa-question-circle text-muted'
  }
}

function formatComponentName(name: string): string {
  return name
    .replace(/_/g, ' ')
    .split(' ')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

onMounted(() => {
  refreshStats()
})
</script>

<style scoped>
/* Issue #586: Entity Graph Manager styles - Uses design tokens */
.entity-graph-manager {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
  padding: var(--spacing-lg);
}

.manager-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--spacing-md);
  flex-wrap: wrap;
}

.header-content h3 {
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin: 0;
}

.header-content h3 i {
  color: var(--color-primary);
}

.header-description {
  color: var(--text-secondary);
  font-size: var(--text-sm);
  margin-top: var(--spacing-xs);
}

.header-actions {
  display: flex;
  gap: var(--spacing-sm);
}

.action-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--border-default);
  background: var(--bg-card);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-primary);
  cursor: pointer;
  transition: all var(--duration-200);
  text-decoration: none;
}

.action-btn:hover:not(:disabled) {
  background: var(--bg-hover);
  border-color: var(--border-strong);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Tab Navigation */
.tab-navigation {
  display: flex;
  gap: var(--spacing-xs);
  background: var(--bg-secondary);
  padding: var(--spacing-xs);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-subtle);
}

.tab-button {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  border: none;
  background: transparent;
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--duration-200);
}

.tab-button:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}

.tab-button.active {
  background: var(--bg-card);
  color: var(--color-primary);
  box-shadow: var(--shadow-sm);
}

.tab-button i {
  font-size: var(--text-base);
}

/* Tab Content */
.tab-content {
  min-height: 400px;
}

.tab-panel {
  animation: fadeIn var(--duration-200) ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

/* Statistics Section */
.stats-section {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.stats-section h4,
.stats-section h5 {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin: 0;
}

.stats-section h4 i,
.stats-section h5 i {
  color: var(--color-primary);
}

.loading-state,
.error-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-md);
  padding: var(--spacing-xl);
  color: var(--text-secondary);
}

.error-state {
  color: var(--color-error);
}

.retry-btn {
  padding: var(--spacing-xs) var(--spacing-sm);
  border: 1px solid var(--color-error);
  background: transparent;
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  color: var(--color-error);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.retry-btn:hover {
  background: var(--color-error-bg);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--spacing-md);
}

.stat-card {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-lg);
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-subtle);
}

.stat-icon {
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-primary-bg);
  border-radius: var(--radius-md);
  color: var(--color-primary);
  font-size: var(--text-xl);
}

.stat-info {
  display: flex;
  flex-direction: column;
}

.stat-value {
  font-size: var(--text-2xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
}

.stat-label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

/* Health Section */
.health-section {
  margin-top: var(--spacing-lg);
}

.health-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--spacing-md);
  margin-top: var(--spacing-md);
}

.health-card {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  padding: var(--spacing-md);
  border: 1px solid var(--border-subtle);
  border-left: 4px solid var(--border-default);
}

.health-card.healthy {
  border-left-color: var(--color-success);
}

.health-card.degraded {
  border-left-color: var(--color-warning);
}

.health-card.unhealthy,
.health-card.unknown {
  border-left-color: var(--color-error);
}

.health-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-md);
}

.health-name {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.health-status {
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--radius-full);
  text-transform: capitalize;
}

.health-card.healthy .health-status {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.health-card.degraded .health-status {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.health-card.unhealthy .health-status,
.health-card.unknown .health-status {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.health-components {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.component-status {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.component-status i {
  font-size: var(--text-xs);
}

.text-success { color: var(--color-success); }
.text-warning { color: var(--color-warning); }
.text-error { color: var(--color-error); }
.text-muted { color: var(--text-tertiary); }

/* Activity Section */
.activity-section {
  margin-top: var(--spacing-lg);
}

.activity-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-md);
}

.activity-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--bg-card);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-subtle);
}

.activity-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.activity-id {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.activity-stats {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.activity-status {
  font-size: var(--text-xs);
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--radius-full);
}

.activity-status.success {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.activity-status.error {
  background: var(--color-error-bg);
  color: var(--color-error);
}

@media (max-width: 768px) {
  .manager-header {
    flex-direction: column;
  }

  .header-actions {
    width: 100%;
  }

  .header-actions .action-btn {
    flex: 1;
    justify-content: center;
  }

  .tab-navigation {
    flex-direction: column;
  }

  .stats-grid {
    grid-template-columns: 1fr;
  }

  .health-cards {
    grid-template-columns: 1fr;
  }
}
</style>
