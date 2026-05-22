<template>
  <div class="knowledge-maintenance">
    <!-- Header -->
    <div class="maintenance-header">
      <div class="header-content">
        <h2><Icon name="tools" /> {{ $t('knowledge.maintenance.title') }}</h2>
        <p class="header-subtitle">
          {{ $t('knowledge.maintenance.subtitle') }}
        </p>
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

    <!-- Health Dashboard Summary -->
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

        <!-- Quality Dimensions -->
        <div v-if="healthDashboard?.quality?.dimensions" class="quality-dimensions">
          <h4>{{ $t('knowledge.maintenance.qualityDimensions') }}</h4>
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
        </div>

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

        <!-- Recommendations -->
        <div v-if="healthDashboard.top_recommendations?.length" class="recommendations">
          <h4>{{ $t('knowledge.maintenance.topRecommendations') }}</h4>
          <ul class="recommendation-list">
            <li v-for="(rec, idx) in healthDashboard.top_recommendations" :key="idx">
              <Icon name="lightbulb" />
              {{ rec }}
            </li>
          </ul>
        </div>
      </div>

      <div v-else class="empty-state">
        <Icon name="info-circle" />
        <p>{{ $t('knowledge.maintenance.healthError') }}</p>
      </div>
    </div>

    <!-- Maintenance Actions -->
    <div class="maintenance-sections">
      <!-- Deduplication Manager -->
      <div class="maintenance-section">
        <DeduplicationManager />
      </div>

      <!-- Session Orphan Manager -->
      <div class="maintenance-section">
        <SessionOrphanManager />
      </div>

      <!-- Cleanup Statistics -->
      <div class="maintenance-section">
        <CleanupStatistics
          ref="cleanupStatsRef"
          @cleanup-complete="handleCleanupComplete"
        />
      </div>

      <!-- Backup Management -->
      <div class="maintenance-section">
        <BackupManager />
      </div>
    </div>

    <!-- Maintenance History (future enhancement) -->
    <div class="maintenance-history">
      <div class="section-title">
        <h3><Icon name="history" /> {{ $t('knowledge.maintenance.maintenanceHistory') }}</h3>
      </div>
      <div class="history-content">
        <div v-if="maintenanceHistory.length === 0" class="empty-history">
          <Icon name="calendar" />
          <p>{{ $t('knowledge.maintenance.noHistory') }}</p>
        </div>
        <div v-else class="history-list">
          <div
            v-for="(entry, idx) in maintenanceHistory"
            :key="idx"
            class="history-item"
            :class="entry.type"
          >
            <div class="history-icon">
              <Icon :name="getHistoryIcon(entry.type)" />
            </div>
            <div class="history-content">
              <span class="history-action">{{ entry.action }}</span>
              <span class="history-details">{{ entry.details }}</span>
            </div>
            <span class="history-time">{{ formatTimeAgo(entry.timestamp) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref, onMounted } from 'vue'
import { formatFileSize, formatTimeAgo } from '@/utils/formatHelpers'
import BaseButton from '@/components/base/BaseButton.vue'
import DeduplicationManager from '@/components/knowledge/DeduplicationManager.vue'
import SessionOrphanManager from '@/components/knowledge/SessionOrphanManager.vue'
import CleanupStatistics from '@/components/knowledge/CleanupStatistics.vue'
import BackupManager from '@/components/knowledge/BackupManager.vue'
import { createLogger } from '@/utils/debugUtils'
import { useKnowledgeMaintenance } from '@/composables/knowledge/useKnowledgeMaintenance'

const logger = createLogger('KnowledgeMaintenance')

// Types
interface MaintenanceHistoryEntry {
  type: 'cleanup' | 'dedup' | 'backup' | 'restore' | 'orphan'
  action: string
  details: string
  timestamp: Date
}

// Composable — health dashboard fetch
const { healthDashboard, isLoadingHealth, loadHealthDashboard } = useKnowledgeMaintenance()

// State
const isRefreshing = ref(false)
const maintenanceHistory = ref<MaintenanceHistoryEntry[]>([])
const cleanupStatsRef = ref<InstanceType<typeof CleanupStatistics> | null>(null)

// Methods
const refreshAll = async () => {
  isRefreshing.value = true

  try {
    await loadHealthDashboard()
    logger.info('All maintenance data refreshed')
  } catch (error) {
    logger.error('Error refreshing maintenance data:', error)
  } finally {
    isRefreshing.value = false
  }
}

const handleCleanupComplete = (result: { action: string; details: string }) => {
  // Add to maintenance history (limit to 50 entries to prevent memory leak)
  maintenanceHistory.value.unshift({
    type: 'cleanup',
    action: result.action,
    details: result.details,
    timestamp: new Date()
  })
  if (maintenanceHistory.value.length > 50) {
    maintenanceHistory.value = maintenanceHistory.value.slice(0, 50)
  }

  // Refresh health dashboard after cleanup
  loadHealthDashboard()
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

const getHistoryIcon = (type: string): string => {
  const icons: Record<string, string> = {
    cleanup: 'broom',
    dedup: 'copy',
    backup: 'download',
    restore: 'upload',
    orphan: 'unlink'
  }
  return icons[type] || 'cog'
}

// Lifecycle
onMounted(() => {
  loadHealthDashboard()
})
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.knowledge-maintenance {
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

.header-subtitle {
  color: var(--text-tertiary);
  margin: var(--spacing-0);
  font-size: 0.95rem;
}

/* Health Dashboard */
.health-dashboard {
  background: var(--bg-card);
  border-radius: var(--radius-xl);
  padding: var(--spacing-6);
  margin-bottom: var(--spacing-8);
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

/* Quality Dimensions */
.quality-dimensions {
  grid-column: span 2;
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  border: 1px solid var(--border-default);
}

.quality-dimensions h4 {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-secondary);
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-4) var(--spacing-0);
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

/* Recommendations */
.recommendations {
  grid-column: span 4;
  background: var(--color-info-bg);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  border: 1px solid var(--color-info-light);
}

.recommendations h4 {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-info-dark);
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-3) var(--spacing-0);
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

/* Maintenance Sections */
.maintenance-sections {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--spacing-6);
  margin-bottom: var(--spacing-8);
}

.maintenance-section {
  background: var(--bg-card);
  border-radius: var(--radius-xl);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
}

/* Maintenance History */
.maintenance-history {
  background: var(--bg-card);
  border-radius: var(--radius-xl);
  padding: var(--spacing-6);
  box-shadow: var(--shadow-sm);
}

.history-content {
  margin-top: var(--spacing-4);
}

.empty-history {
  text-align: center;
  padding: var(--spacing-8);
  color: var(--text-muted);
}

.empty-history i {
  font-size: 2rem;
  margin-bottom: var(--spacing-3);
  display: block;
}

.empty-history p {
  margin: var(--spacing-0);
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.history-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  padding: var(--spacing-3) var(--spacing-4);
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
  border-left: 3px solid var(--border-light);
}

.history-item.cleanup {
  border-left-color: var(--color-success);
}

.history-item.dedup {
  border-left-color: var(--color-primary);
}

.history-item.backup {
  border-left-color: #8b5cf6;
}

.history-item.orphan {
  border-left-color: var(--color-warning);
}

.history-icon {
  width: 2rem;
  height: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--border-default);
  border-radius: 50%;
  color: var(--border-secondary);
  font-size: var(--text-sm);
}

.history-content {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.history-action {
  font-weight: 500;
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.history-details {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.history-time {
  font-size: var(--text-xs);
  color: var(--text-muted);
  white-space: nowrap;
}

/* Responsive */
@media (max-width: 1200px) {
  .health-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .recommendations {
    grid-column: span 2;
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

  .header-actions button {
    width: 100%;
  }

  .health-grid {
    grid-template-columns: 1fr;
  }

  .quality-dimensions,
  .recommendations {
    grid-column: span 1;
  }

  .maintenance-sections {
    grid-template-columns: 1fr;
  }
}
</style>
