<template>
  <div class="entity-graph-manager">
    <!-- Header -->
    <div class="manager-header">
      <div class="header-content">
        <h3><Icon name="sitemap" /> {{ $t('knowledge.entityGraph.title') }}</h3>
        <p class="header-description">
          {{ $t('knowledge.entityGraph.description') }}
        </p>
      </div>
      <div class="header-actions">
        <button @click="refreshStats" class="action-btn" :disabled="isLoadingStats">
          <i :class="isLoadingStats ? 'fas fa-spinner fa-spin' : 'sync'"></i>
          {{ $t('knowledge.entityGraph.refreshStats') }}
        </button>
        <router-link to="/knowledge/graph" class="action-btn">
          <Icon name="project-diagram" />
          {{ $t('knowledge.entityGraph.viewGraph') }}
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
        <Icon :name="tab.icon" />
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
          <h4><Icon name="chart-bar" /> {{ $t('knowledge.entityGraph.graphStatistics') }}</h4>

          <div v-if="isLoadingStats" class="loading-state">
            <Icon name="spinner" class="animate-spin" />
            <span>{{ $t('knowledge.entityGraph.loadingStatistics') }}</span>
          </div>

          <div v-else-if="statsError" class="error-state">
            <Icon name="exclamation-triangle" />
            <span>{{ statsError }}</span>
            <button @click="refreshStats" class="retry-btn">
              <Icon name="redo" /> {{ $t('knowledge.entityGraph.retry') }}
            </button>
          </div>

          <div v-else class="stats-grid">
            <div class="stat-card">
              <div class="stat-icon">
                <Icon name="circle" />
              </div>
              <div class="stat-info">
                <span class="stat-value">{{ graphStats.entityCount }}</span>
                <span class="stat-label">{{ $t('knowledge.entityGraph.totalEntities') }}</span>
              </div>
            </div>

            <div class="stat-card">
              <div class="stat-icon">
                <Icon name="link" />
              </div>
              <div class="stat-info">
                <span class="stat-value">{{ graphStats.relationCount }}</span>
                <span class="stat-label">{{ $t('knowledge.entityGraph.totalRelations') }}</span>
              </div>
            </div>

            <div class="stat-card">
              <div class="stat-icon">
                <Icon name="tags" />
              </div>
              <div class="stat-info">
                <span class="stat-value">{{ graphStats.entityTypes }}</span>
                <span class="stat-label">{{ $t('knowledge.entityGraph.entityTypes') }}</span>
              </div>
            </div>

            <div class="stat-card">
              <div class="stat-icon">
                <Icon name="exchange-alt" />
              </div>
              <div class="stat-info">
                <span class="stat-value">{{ graphStats.relationTypes }}</span>
                <span class="stat-label">{{ $t('knowledge.entityGraph.relationTypes') }}</span>
              </div>
            </div>
          </div>

          <!-- Service Health -->
          <div class="health-section">
            <h5><Icon name="heartbeat" /> {{ $t('knowledge.entityGraph.serviceHealth') }}</h5>

            <div class="health-cards">
              <div class="health-card" :class="extractionHealth.status">
                <div class="health-header">
                  <span class="health-name">{{ $t('knowledge.entityGraph.entityExtraction') }}</span>
                  <span class="health-status">{{ extractionHealth.status }}</span>
                </div>
                <div class="health-components">
                  <div
                    v-for="(status, component) in extractionHealth.components"
                    :key="component"
                    class="component-status"
                  >
                    <Icon :name="getStatusIcon(status)" />
                    <span>{{ formatComponentName(component) }}</span>
                  </div>
                </div>
              </div>

              <div class="health-card" :class="graphRagHealth.status">
                <div class="health-header">
                  <span class="health-name">{{ $t('knowledge.entityGraph.graphRagService') }}</span>
                  <span class="health-status">{{ graphRagHealth.status }}</span>
                </div>
                <div class="health-components">
                  <div
                    v-for="(status, component) in graphRagHealth.components"
                    :key="component"
                    class="component-status"
                  >
                    <Icon :name="getStatusIcon(status)" />
                    <span>{{ formatComponentName(component) }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Recent Activity -->
          <div v-if="recentExtractions.length > 0" class="activity-section">
            <h5><Icon name="history" /> {{ $t('knowledge.entityGraph.recentExtractions') }}</h5>
            <div class="activity-list">
              <div
                v-for="extraction in recentExtractions"
                :key="extraction.request_id"
                class="activity-item"
              >
                <div class="activity-main">
                  <span class="activity-id">{{ extraction.conversation_id }}</span>
                  <span class="activity-stats">
                    {{ $t('knowledge.entityGraph.entitiesAndRelations', { entities: extraction.entities_created, relations: extraction.relations_created }) }}
                  </span>
                </div>
                <span :class="['activity-status', extraction.success ? 'success' : 'error']">
                  {{ extraction.success ? $t('knowledge.entityGraph.success') : $t('knowledge.entityGraph.failedStatus') }}
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

import Icon from '@/components/ui/Icon.vue'
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { createLogger } from '@/utils/debugUtils'
import { useKnowledgeEntityGraph } from '@/composables/knowledge/useKnowledgeEntityGraph'
import EntityExtractor from './EntityExtractor.vue'
import GraphRAGQuery from './GraphRAGQuery.vue'

const logger = createLogger('EntityGraphManager')
const { t } = useI18n()
const router = useRouter()

// ============================================================================
// Types
// ============================================================================

interface Tab {
  id: string
  label: string
  icon: string
}

interface ExtractionResult {
  success: boolean
  conversation_id: string
  entities_created: number
  relations_created: number
  request_id: string
}

// ============================================================================
// Composable
// ============================================================================

const {
  graphStats,
  extractionHealth,
  graphRagHealth,
  isLoading: isLoadingStats,
  statsError,
  refreshStats,
} = useKnowledgeEntityGraph()

// ============================================================================
// State
// ============================================================================

const tabs = computed<Tab[]>(() => [
  { id: 'extract', label: t('knowledge.entityGraph.tabExtract'), icon: 'brain' },
  { id: 'query', label: t('knowledge.entityGraph.tabQuery'), icon: 'search-plus' },
  { id: 'stats', label: t('knowledge.entityGraph.tabStatistics'), icon: 'chart-bar' }
])

const activeTab = ref('extract')
const recentExtractions = ref<ExtractionResult[]>([])

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
    case 'healthy': return 'check-circle'
    case 'degraded': return 'exclamation-triangle'
    case 'unavailable':
    case 'unhealthy': return 'times-circle'
    default: return 'question-circle'
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
  margin: var(--spacing-0);
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
  margin: var(--spacing-0);
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
  gap: var(--spacing-0-5);
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
