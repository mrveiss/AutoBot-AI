<template>
  <div class="knowledge-health">
    <!-- Header -->
    <div class="maintenance-header">
      <div class="header-content">
        <h2><Icon name="heartbeat" /> {{ $t('knowledge.views.health') }}</h2>
      </div>
      <div class="header-actions">
        <BaseButton
          variant="secondary"
          size="sm"
          @click="refreshAll"
          :disabled="isRefreshing"
          :loading="isRefreshing"
        >
          <Icon name="sync" v-if="!isRefreshing" />
          {{ isRefreshing ? $t('knowledge.maintenance.refreshing') : $t('knowledge.maintenance.refreshAll') }}
        </BaseButton>
      </div>
    </div>

    <!-- Health Dashboard Strip -->
    <div class="health-dashboard">
      <div class="section-title">
        <h3><Icon name="heartbeat" /> {{ $t('knowledge.maintenance.healthDashboard') }}</h3>
        <span v-if="healthDashboard" :class="['health-status-badge', healthDashboard.status]">
          {{ healthDashboard.status }}
        </span>
      </div>

      <div v-if="isLoadingHealth" class="loading-state">
        <Icon name="spinner" class="animate-spin" />
        <span>{{ $t('knowledge.maintenance.loadingHealth') }}</span>
      </div>

      <div v-else-if="healthDashboard" class="health-grid">
        <!-- Stats Cards -->
        <div class="health-card">
          <div class="card-icon facts">
            <Icon name="lightbulb" />
          </div>
          <div class="card-content">
            <span class="card-value">{{ healthDashboard.stats.total_facts }}</span>
            <span class="card-label">{{ $t('knowledge.maintenance.totalFacts') }}</span>
          </div>
        </div>

        <div class="health-card">
          <div class="card-icon vectors">
            <Icon name="cubes" />
          </div>
          <div class="card-content">
            <span class="card-value">{{ healthDashboard.stats.total_vectors }}</span>
            <span class="card-label">{{ $t('knowledge.maintenance.totalVectors') }}</span>
          </div>
        </div>

        <div class="health-card">
          <div class="card-icon storage">
            <Icon name="database" />
          </div>
          <div class="card-content">
            <span class="card-value">{{ formatFileSize(healthDashboard.stats.db_size) }}</span>
            <span class="card-label">{{ $t('knowledge.maintenance.databaseSize') }}</span>
          </div>
        </div>

        <div v-if="healthDashboard?.quality" class="health-card">
          <div class="card-icon quality" :class="getQualityClass(healthDashboard.quality.overall_score)">
            <Icon name="chart-line" />
          </div>
          <div class="card-content">
            <span class="card-value">{{ healthDashboard.quality.overall_score }}%</span>
            <span class="card-label">{{ $t('knowledge.maintenance.qualityScore') }}</span>
          </div>
        </div>

        <!-- Quality Dimensions (expandable) -->
        <details v-if="healthDashboard?.quality?.dimensions" class="quality-dimensions">
          <summary>{{ $t('knowledge.maintenance.qualityDimensions') }}</summary>
          <div class="dimension-bars">
            <div
              v-for="(score, dimension) in healthDashboard.quality.dimensions"
              :key="dimension"
              class="dimension-item"
            >
              <div class="dimension-header">
                <span class="dimension-name">{{ formatDimensionName(dimension) }}</span>
                <span class="dimension-score">{{ score }}%</span>
              </div>
              <div class="dimension-bar">
                <div
                  class="dimension-fill"
                  :style="{ width: score + '%' }"
                  :class="getQualityClass(score)"
                ></div>
              </div>
            </div>
          </div>
        </details>

        <!-- Issues Summary -->
        <div v-if="healthDashboard?.quality" class="issues-summary">
          <h4>{{ $t('knowledge.maintenance.issuesFound') }}</h4>
          <div class="issues-counts">
            <div class="issue-count critical">
              <Icon name="exclamation-circle" />
              <span>{{ healthDashboard.quality.critical_issues ?? 0 }} {{ $t('knowledge.maintenance.critical') }}</span>
            </div>
            <div class="issue-count warning">
              <Icon name="exclamation-triangle" />
              <span>{{ healthDashboard.quality.warnings ?? 0 }} {{ $t('knowledge.maintenance.warnings') }}</span>
            </div>
          </div>
        </div>

        <!-- Recommendations (expandable) -->
        <details v-if="healthDashboard.top_recommendations?.length" class="recommendations">
          <summary>{{ $t('knowledge.maintenance.topRecommendations') }}</summary>
          <ul class="recommendation-list">
            <li v-for="(rec, idx) in healthDashboard.top_recommendations" :key="idx">
              <Icon name="lightbulb" />
              {{ rec }}
            </li>
          </ul>
        </details>
      </div>

      <div v-else class="empty-state">
        <Icon name="info-circle" />
        <p>{{ $t('knowledge.maintenance.healthError') }}</p>
      </div>

      <!-- RAG / Vector Index Status -->
      <div v-if="vectorStats" class="rag-status-area">
        <!-- Vectorization notice -->
        <div v-if="needsVectorization" class="vectorization-notice">
          <div class="notice-icon">
            <Icon name="info-circle" />
          </div>
          <div class="notice-content">
            <h4>{{ $t('knowledge.stats.vectorNotGenerated') }}</h4>
            <p>
              {{ $t('knowledge.stats.vectorNotGeneratedDesc', { count: vectorStats.total_facts }) }}
            </p>
            <p class="notice-hint">
              <Icon name="lightbulb" />
              {{ $t('knowledge.stats.vectorNotGeneratedHint') }}
            </p>
          </div>
        </div>

        <!-- RAG / index availability badges -->
        <div class="rag-badges">
          <span :class="['rag-badge', vectorStats.rag_available ? 'available' : 'unavailable']">
            <Icon :name="vectorStats.rag_available ? 'check-circle' : 'times-circle'" />
            {{ vectorStats.rag_available ? $t('knowledge.stats.available') : $t('knowledge.stats.unavailable') }}
            {{ $t('knowledge.stats.rag') }}
          </span>
          <span :class="['rag-badge', vectorStats.initialized ? 'available' : 'unavailable']">
            <Icon :name="vectorStats.initialized ? 'check-circle' : 'times-circle'" />
            {{ $t('knowledge.stats.initialized') }}
          </span>
        </div>

        <!-- Index health detail (expandable) -->
        <details class="index-health-details">
          <summary>{{ $t('knowledge.stats.vectorIndexHealth') }}</summary>
          <div class="health-details">
            <div class="detail-item">
              <label>{{ $t('knowledge.stats.redisDb') }}:</label>
              <span class="mono">{{ vectorStats.redis_db }}</span>
            </div>
            <div class="detail-item">
              <label>{{ $t('knowledge.stats.indexName') }}:</label>
              <span class="mono">{{ vectorStats.index_name }}</span>
            </div>
            <div class="detail-item">
              <label>{{ $t('knowledge.stats.vectorFramework') }}:</label>
              <span class="mono">LlamaIndex + LangChain</span>
            </div>
            <div class="detail-item">
              <label>{{ $t('knowledge.stats.embeddingModel') }}:</label>
              <span class="mono">{{ getEmbeddingModelDisplay() }}</span>
            </div>
            <div class="detail-item">
              <label>{{ $t('knowledge.stats.textSplitter') }}:</label>
              <span class="mono">LangChain RecursiveCharacterTextSplitter</span>
            </div>
            <div class="detail-item">
              <label>{{ $t('knowledge.stats.lastUpdated') }}:</label>
              <span>{{ formatDateTimeHelper(vectorStats.last_updated) }}</span>
            </div>
            <div class="detail-item">
              <label>{{ $t('knowledge.stats.indexedDocuments') }}:</label>
              <span>{{ vectorStats.indexed_documents || 0 }}</span>
            </div>
          </div>
        </details>
      </div>
    </div>

    <!-- Tab Bar -->
    <div ref="tablistRef" class="health-tabs" role="tablist" :aria-label="$t('knowledge.views.healthAriaLabel')">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        v-bind="tabAttrs(tab.id)"
        :class="['health-tab-btn', { active: activeTab === tab.id }]"
        @click="activeTab = tab.id"
        @keydown="handleTabKeydown"
      >
        <Icon :name="tab.icon" />
        {{ $t(tab.labelKey) }}
        <span
          v-if="tab.id === 'verification' && pendingVerificationsTotal > 0"
          class="tab-badge"
          aria-live="polite"
        >{{ pendingVerificationsTotal }}</span>
      </button>
    </div>

    <!-- Tab Bodies (v-if for lazy mount — each tab's onMounted fires on first open) -->
    <div class="health-tab-content">
      <div v-if="activeTab === 'analytics'" v-bind="panelAttrs('analytics')">
        <KnowledgeHealthAnalytics />
      </div>
      <div v-if="activeTab === 'verification'" v-bind="panelAttrs('verification')">
        <KnowledgeVerificationQueue />
      </div>
      <div v-if="activeTab === 'tools'" v-bind="panelAttrs('tools')">
        <KnowledgeHealthTools @refresh-strip="loadHealthDashboard" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import type { IconName } from '@/components/ui/Icon.vue'
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useTabs } from '@/composables/useTabs'
import { formatFileSize, formatDateTime as formatDateTimeHelper } from '@/utils/formatHelpers'
import BaseButton from '@/components/base/BaseButton.vue'
import { createLogger } from '@/utils/debugUtils'
import { useKnowledgeMaintenance } from '@/composables/knowledge/useKnowledgeMaintenance'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import { useVectorStats, EMPTY_VECTOR_STATS } from '@/composables/knowledge/useVectorStats'
import type { VectorStats } from '@/composables/knowledge/useVectorStats'
import { knowledgeRepository } from '@/models/repositories/KnowledgeRepository'
import KnowledgeHealthAnalytics from '@/components/knowledge/KnowledgeHealthAnalytics.vue'
import KnowledgeVerificationQueue from '@/components/knowledge/KnowledgeVerificationQueue.vue'
import KnowledgeHealthTools from '@/components/knowledge/KnowledgeHealthTools.vue'

const logger = createLogger('KnowledgeHealth')
const route = useRoute()

// Composable — health dashboard fetch
const { healthDashboard, isLoadingHealth, loadHealthDashboard } = useKnowledgeMaintenance()

// Store — pending verification count + stats refresh
const store = useKnowledgeStore()
const pendingVerificationsTotal = computed(() => store.pendingVerificationsTotal)

// State
const isRefreshing = ref(false)

// Shared stats mapping (#11571). The strip must stay visible after the first
// load even when the store is factless or the backend is unreachable (same
// visibility as the previous local zeroed fallback), so fall back to
// EMPTY_VECTOR_STATS once a load has completed.
const { vectorStats: sharedVectorStats, refresh: refreshVectorStats } = useVectorStats()
const vectorStatsLoaded = ref(false)
const vectorStats = computed<VectorStats | null>(() =>
  sharedVectorStats.value ?? (vectorStatsLoaded.value ? EMPTY_VECTOR_STATS : null)
)

// Tab state — initialized from the route at setup time so deep links
// (?tab=verification|tools) mount the right tab on first render (#11558)
type TabId = 'analytics' | 'verification' | 'tools'
const TAB_IDS = ['analytics', 'verification', 'tools'] as const satisfies readonly TabId[]
const routeTab = route.query.tab
const initialTab: TabId =
  typeof routeTab === 'string' && (TAB_IDS as readonly string[]).includes(routeTab)
    ? (routeTab as TabId)
    : 'analytics'

const { activeTab, tabAttrs, panelAttrs, handleKeydown: handleTabKeydown, tablistRef } =
  useTabs(TAB_IDS, { initial: initialTab })

const tabs: Array<{ id: TabId; labelKey: string; icon: IconName }> = [
  { id: 'analytics', labelKey: 'knowledge.health.tabAnalytics', icon: 'chart-bar' },
  { id: 'verification', labelKey: 'knowledge.health.tabVerification', icon: 'check-double' },
  { id: 'tools', labelKey: 'knowledge.health.tabTools', icon: 'cog' },
]

// Computed
const needsVectorization = computed(() => {
  if (!vectorStats.value) return false
  return (vectorStats.value.total_facts || 0) > 0 && (vectorStats.value.total_vectors || 0) === 0
})

// Methods
const loadVectorHealth = async () => {
  try {
    await refreshVectorStats()
  } catch (error) {
    logger.error('Failed to load vector health stats:', error)
  } finally {
    vectorStatsLoaded.value = true
  }
}

const refreshAll = async () => {
  isRefreshing.value = true

  try {
    await Promise.all([loadHealthDashboard(), loadVectorHealth()])
    logger.info('Health strip refreshed')
  } catch (error) {
    logger.error('Error refreshing health strip:', error)
  } finally {
    isRefreshing.value = false
  }
}

const formatDimensionName = (dimension: string): string => {
  return dimension
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase())
}

const getQualityClass = (score: number): string => {
  if (score >= 80) return 'good'
  if (score >= 50) return 'warning'
  return 'critical'
}

const getEmbeddingModelDisplay = (): string => {
  if (!vectorStats.value) return 'Loading...'

  const model = vectorStats.value.embedding_model
  const dimensions = vectorStats.value.embedding_dimensions

  if (model && dimensions) {
    return `${model} (${dimensions}-dim)`
  } else if (model) {
    return model
  } else {
    return 'Not configured'
  }
}

// Lifecycle
onMounted(async () => {
  loadHealthDashboard()
  loadVectorHealth()

  // Prefetch pending-verification total so the badge is populated on page load.
  // Total-only setter: must not clobber the list when a ?tab=verification deep
  // link mounted KnowledgeVerificationQueue first and it already loaded page 1.
  try {
    const data = await knowledgeRepository.getPendingVerifications(1, 1)
    store.setPendingVerificationsTotal(data.total || 0)
  } catch (error) {
    logger.error('Failed to prefetch pending verification count: %s', error)
  }
})
</script>

<style scoped>
/* KnowledgeHealth — overview strip + tab shell */
.knowledge-health {
  padding: var(--spacing-6);
  max-width: 1400px;
  margin: 0 auto;
}

/* Header */
.maintenance-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--spacing-8);
  padding-bottom: var(--spacing-4);
  border-bottom: 2px solid var(--border-default);
}

.header-content h2 {
  font-size: 1.75rem;
  font-weight: 700;
  color: var(--text-primary);
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-2) var(--spacing-0);
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
}

.header-content h2 i {
  color: var(--color-primary);
}

/* Health Dashboard Strip */
.health-dashboard {
  background: var(--bg-card);
  border-radius: var(--radius-xl);
  padding: var(--spacing-6);
  margin-bottom: var(--spacing-6);
  box-shadow: var(--shadow-sm);
}

.section-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-6);
}

.section-title h3 {
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--text-primary);
  margin: var(--spacing-0);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.health-status-badge {
  padding: var(--spacing-1-5) var(--spacing-3);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
}

.health-status-badge.healthy {
  background: var(--color-success-bg);
  color: var(--color-success-dark);
}

.health-status-badge.warning {
  background: var(--color-warning-bg);
  color: var(--color-warning-dark);
}

.health-status-badge.degraded {
  background: var(--color-error-bg);
  color: var(--color-error-dark);
}

.health-status-badge.error {
  background: var(--color-error-bg);
  color: var(--color-error-dark);
}

.loading-state,
.empty-state {
  text-align: center;
  padding: var(--spacing-12);
  color: var(--text-tertiary);
}

.loading-state i,
.empty-state i {
  font-size: 2.5rem;
  margin-bottom: var(--spacing-4);
  display: block;
}

/* Health Grid */
.health-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--spacing-6);
}

.health-card {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  padding: var(--spacing-4);
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-default);
}

.card-icon {
  width: 3rem;
  height: 3rem;
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-xl);
  color: var(--bg-card);
}

.card-icon.facts {
  background: var(--chart-pink);
}

.card-icon.vectors {
  background: var(--chart-cyan);
}

.card-icon.storage {
  background: var(--color-success);
}

.card-icon.quality {
  background: var(--chart-purple);
}

.card-icon.quality.good {
  background: var(--color-success);
}

.card-icon.quality.warning {
  background: var(--color-warning);
}

.card-icon.quality.critical {
  background: var(--color-error);
}

.card-content {
  display: flex;
  flex-direction: column;
}

.card-value {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--text-primary);
}

.card-label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

/* Quality Dimensions (expandable details) */
.quality-dimensions {
  grid-column: span 2;
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  border: 1px solid var(--border-default);
}

.quality-dimensions > summary {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-secondary);
  cursor: pointer;
  list-style: none;
  margin-bottom: var(--spacing-0);
}

.quality-dimensions[open] > summary {
  margin-bottom: var(--spacing-4);
}

.quality-dimensions > summary::-webkit-details-marker {
  display: none;
}

.dimension-bars {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.dimension-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.dimension-header {
  display: flex;
  justify-content: space-between;
  font-size: var(--text-xs);
}

.dimension-name {
  color: var(--text-secondary);
}

.dimension-score {
  font-weight: 600;
  color: var(--text-primary);
}

.dimension-bar {
  height: 0.5rem;
  background: var(--border-default);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.dimension-fill {
  height: 100%;
  border-radius: var(--radius-full);
  transition: width var(--duration-500) var(--ease-out);
}

.dimension-fill.good {
  background: var(--color-success);
}

.dimension-fill.warning {
  background: var(--color-warning);
}

.dimension-fill.critical {
  background: var(--color-error);
}

/* Issues Summary */
.issues-summary {
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  border: 1px solid var(--border-default);
}

.issues-summary h4 {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-secondary);
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-3) var(--spacing-0);
}

.issues-counts {
  display: flex;
  gap: var(--spacing-4);
}

.issue-count {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-sm);
  font-weight: 500;
}

.issue-count.critical {
  color: var(--color-error);
}

.issue-count.warning {
  color: var(--color-warning);
}

/* Recommendations (expandable details) */
.recommendations {
  grid-column: span 4;
  background: var(--color-info-bg);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  border: 1px solid var(--color-info-light);
}

.recommendations > summary {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-info-dark);
  cursor: pointer;
  list-style: none;
}

.recommendations > summary::-webkit-details-marker {
  display: none;
}

.recommendations[open] > summary {
  margin-bottom: var(--spacing-3);
}

.recommendation-list {
  margin: var(--spacing-0);
  padding: var(--spacing-0);
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.recommendation-list li {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-2);
  font-size: var(--text-sm);
  color: var(--color-info-dark);
}

.recommendation-list li i {
  color: var(--color-primary);
  margin-top: var(--spacing-0-5);
}

/* RAG Status Area */
.rag-status-area {
  margin-top: var(--spacing-6);
  padding-top: var(--spacing-6);
  border-top: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

/* Vectorization notice */
.vectorization-notice {
  display: flex;
  gap: var(--spacing-4);
  background: var(--color-warning-bg);
  border: 1px solid var(--color-warning-light);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
}

.notice-icon {
  color: var(--color-warning);
  font-size: var(--text-xl);
  flex-shrink: 0;
}

.notice-content h4 {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-warning-dark);
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-2) var(--spacing-0);
}

.notice-content p {
  font-size: var(--text-sm);
  color: var(--color-warning-dark);
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-2) var(--spacing-0);
}

.notice-hint {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-xs);
  color: var(--color-warning-dark);
}

/* RAG Badges */
.rag-badges {
  display: flex;
  gap: var(--spacing-3);
  flex-wrap: wrap;
}

.rag-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-1-5) var(--spacing-3);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: 600;
}

.rag-badge.available {
  background: var(--color-success-bg);
  color: var(--color-success-dark);
}

.rag-badge.unavailable {
  background: var(--color-error-bg);
  color: var(--color-error-dark);
}

/* Index Health Details (expandable) */
.index-health-details {
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  border: 1px solid var(--border-default);
}

.index-health-details > summary {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-secondary);
  cursor: pointer;
  list-style: none;
}

.index-health-details > summary::-webkit-details-marker {
  display: none;
}

.index-health-details[open] > summary {
  margin-bottom: var(--spacing-4);
}

.health-details {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--spacing-3);
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.detail-item label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  font-weight: 500;
}

.detail-item span {
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.mono {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
}

/* Tab Bar */
.health-tabs {
  display: flex;
  gap: var(--spacing-1);
  border-bottom: 2px solid var(--border-default);
  margin-bottom: var(--spacing-6);
}

.health-tab-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3) var(--spacing-4);
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: var(--radius-sm) var(--radius-sm) 0 0;
  transition: color var(--duration-150) var(--ease-in-out), border-color var(--duration-150) var(--ease-in-out);
  position: relative;
}

.health-tab-btn:hover {
  color: var(--text-primary);
  background: var(--bg-tertiary);
}

.health-tab-btn.active {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
}

.tab-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.25rem;
  height: 1.25rem;
  padding: 0 var(--spacing-1);
  background: var(--color-error);
  color: var(--bg-card);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: 700;
  line-height: 1;
}

/* Tab Content */
.health-tab-content {
  min-height: 400px;
}

/* Responsive */
@media (max-width: 1200px) {
  .health-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .recommendations {
    grid-column: span 2;
  }

  .health-details {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .maintenance-header {
    flex-direction: column;
    gap: var(--spacing-4);
  }

  .header-actions {
    width: 100%;
  }

  .health-grid {
    grid-template-columns: 1fr;
  }

  .quality-dimensions,
  .recommendations {
    grid-column: span 1;
  }

  .health-tabs {
    flex-wrap: wrap;
  }
}
</style>
