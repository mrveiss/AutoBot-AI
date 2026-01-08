<template>
  <div class="knowledge-maintenance">
    <!-- Header -->
    <div class="maintenance-header">
      <div class="header-content">
        <h2><i class="fas fa-tools"></i> Knowledge Base Maintenance</h2>
        <p class="header-subtitle">
          Monitor and maintain knowledge base health, handle duplicates, and clean up orphaned data
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
          <i v-if="!isRefreshing" class="fas fa-sync"></i>
          {{ isRefreshing ? 'Refreshing...' : 'Refresh All' }}
        </BaseButton>
      </div>
    </div>

    <!-- Health Dashboard Summary -->
    <div class="health-dashboard">
      <div class="section-title">
        <h3><i class="fas fa-heartbeat"></i> Health Dashboard</h3>
        <span v-if="healthDashboard" :class="['health-status-badge', healthDashboard.status]">
          {{ healthDashboard.status }}
        </span>
      </div>

      <div v-if="isLoadingHealth" class="loading-state">
        <i class="fas fa-spinner fa-spin"></i>
        <span>Loading health metrics...</span>
      </div>

      <div v-else-if="healthDashboard" class="health-grid">
        <!-- Stats Cards -->
        <div class="health-card">
          <div class="card-icon facts">
            <i class="fas fa-lightbulb"></i>
          </div>
          <div class="card-content">
            <span class="card-value">{{ healthDashboard.stats.total_facts }}</span>
            <span class="card-label">Total Facts</span>
          </div>
        </div>

        <div class="health-card">
          <div class="card-icon vectors">
            <i class="fas fa-cubes"></i>
          </div>
          <div class="card-content">
            <span class="card-value">{{ healthDashboard.stats.total_vectors }}</span>
            <span class="card-label">Total Vectors</span>
          </div>
        </div>

        <div class="health-card">
          <div class="card-icon storage">
            <i class="fas fa-database"></i>
          </div>
          <div class="card-content">
            <span class="card-value">{{ formatFileSize(healthDashboard.stats.db_size) }}</span>
            <span class="card-label">Database Size</span>
          </div>
        </div>

        <div v-if="healthDashboard?.quality" class="health-card">
          <div class="card-icon quality" :class="getQualityClass(healthDashboard.quality.overall_score)">
            <i class="fas fa-chart-line"></i>
          </div>
          <div class="card-content">
            <span class="card-value">{{ healthDashboard.quality.overall_score }}%</span>
            <span class="card-label">Quality Score</span>
          </div>
        </div>

        <!-- Quality Dimensions -->
        <div v-if="healthDashboard?.quality?.dimensions" class="quality-dimensions">
          <h4>Quality Dimensions</h4>
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
          <h4>Issues Found</h4>
          <div class="issues-counts">
            <div class="issue-count critical">
              <i class="fas fa-exclamation-circle"></i>
              <span>{{ healthDashboard.quality.critical_issues ?? 0 }} Critical</span>
            </div>
            <div class="issue-count warning">
              <i class="fas fa-exclamation-triangle"></i>
              <span>{{ healthDashboard.quality.warnings ?? 0 }} Warnings</span>
            </div>
          </div>
        </div>

        <!-- Recommendations -->
        <div v-if="healthDashboard.top_recommendations?.length" class="recommendations">
          <h4>Top Recommendations</h4>
          <ul class="recommendation-list">
            <li v-for="(rec, idx) in healthDashboard.top_recommendations" :key="idx">
              <i class="fas fa-lightbulb"></i>
              {{ rec }}
            </li>
          </ul>
        </div>
      </div>

      <div v-else class="empty-state">
        <i class="fas fa-info-circle"></i>
        <p>Unable to load health metrics. Click "Refresh All" to try again.</p>
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
        <h3><i class="fas fa-history"></i> Maintenance History</h3>
      </div>
      <div class="history-content">
        <div v-if="maintenanceHistory.length === 0" class="empty-history">
          <i class="fas fa-calendar-check"></i>
          <p>No maintenance operations recorded in this session</p>
        </div>
        <div v-else class="history-list">
          <div
            v-for="(entry, idx) in maintenanceHistory"
            :key="idx"
            class="history-item"
            :class="entry.type"
          >
            <div class="history-icon">
              <i :class="getHistoryIcon(entry.type)"></i>
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
import { ref, onMounted } from 'vue'
import apiClient from '@/utils/ApiClient'
import { parseApiResponse } from '@/utils/apiResponseHelpers'
import { formatFileSize, formatTimeAgo } from '@/utils/formatHelpers'
import BaseButton from '@/components/base/BaseButton.vue'
import DeduplicationManager from '@/components/knowledge/DeduplicationManager.vue'
import SessionOrphanManager from '@/components/knowledge/SessionOrphanManager.vue'
import CleanupStatistics from '@/components/knowledge/CleanupStatistics.vue'
import BackupManager from '@/components/knowledge/BackupManager.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('KnowledgeMaintenance')

// Types
interface HealthDashboard {
  status: 'healthy' | 'warning' | 'degraded' | 'error'
  last_updated: string
  stats: {
    total_facts: number
    total_vectors: number
    db_size: number
    categories: number
    embedding_cache: Record<string, any>
  }
  quality: {
    overall_score: number
    dimensions: Record<string, number>
    critical_issues: number
    warnings: number
  }
  top_recommendations: string[]
}

interface MaintenanceHistoryEntry {
  type: 'cleanup' | 'dedup' | 'backup' | 'restore' | 'orphan'
  action: string
  details: string
  timestamp: Date
}

// State
const isRefreshing = ref(false)
const isLoadingHealth = ref(false)
const healthDashboard = ref<HealthDashboard | null>(null)
const maintenanceHistory = ref<MaintenanceHistoryEntry[]>([])
const cleanupStatsRef = ref<InstanceType<typeof CleanupStatistics> | null>(null)

// Methods
const loadHealthDashboard = async () => {
  isLoadingHealth.value = true

  try {
    const response = await apiClient.get('/api/knowledge-maintenance/health/dashboard')
    const data = await parseApiResponse(response)

    if (data) {
      healthDashboard.value = data
      logger.info('Health dashboard loaded:', data.status)
    }
  } catch (error) {
    logger.error('Failed to load health dashboard:', error)
  } finally {
    isLoadingHealth.value = false
  }
}

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
    cleanup: 'fas fa-broom',
    dedup: 'fas fa-copy',
    backup: 'fas fa-download',
    restore: 'fas fa-upload',
    orphan: 'fas fa-unlink'
  }
  return icons[type] || 'fas fa-cog'
}

// Lifecycle
onMounted(() => {
  loadHealthDashboard()
})
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.knowledge-maintenance {
  padding: 1.5rem;
  max-width: 1400px;
  margin: 0 auto;
}

/* Header */
.maintenance-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 2rem;
  padding-bottom: 1rem;
  border-bottom: 2px solid var(--border-default);
}

.header-content h2 {
  font-size: 1.75rem;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 0.5rem 0;
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.header-content h2 i {
  color: var(--color-primary);
}

.header-subtitle {
  color: var(--text-tertiary);
  margin: 0;
  font-size: 0.95rem;
}

/* Health Dashboard */
.health-dashboard {
  background: var(--bg-card);
  border-radius: 0.75rem;
  padding: 1.5rem;
  margin-bottom: 2rem;
  box-shadow: var(--shadow-sm);
}

.section-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
}

.section-title h3 {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.health-status-badge {
  padding: 0.375rem 0.75rem;
  border-radius: 9999px;
  font-size: 0.75rem;
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
  padding: 3rem;
  color: var(--text-tertiary);
}

.loading-state i,
.empty-state i {
  font-size: 2.5rem;
  margin-bottom: 1rem;
  display: block;
}

/* Health Grid */
.health-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1.5rem;
}

.health-card {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  background: var(--bg-tertiary);
  border-radius: 0.5rem;
  border: 1px solid var(--border-default);
}

.card-icon {
  width: 3rem;
  height: 3rem;
  border-radius: 0.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.25rem;
  color: var(--bg-card);
}

.card-icon.facts {
  background: linear-gradient(135deg, #f093fb, #f5576c);
}

.card-icon.vectors {
  background: linear-gradient(135deg, #4facfe, #00f2fe);
}

.card-icon.storage {
  background: linear-gradient(135deg, #43e97b, #38f9d7);
}

.card-icon.quality {
  background: linear-gradient(135deg, #667eea, #764ba2);
}

.card-icon.quality.good {
  background: linear-gradient(135deg, #10b981, #34d399);
}

.card-icon.quality.warning {
  background: linear-gradient(135deg, #f59e0b, #fbbf24);
}

.card-icon.quality.critical {
  background: linear-gradient(135deg, #ef4444, #f87171);
}

.card-content {
  display: flex;
  flex-direction: column;
}

.card-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-primary);
}

.card-label {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

/* Quality Dimensions */
.quality-dimensions {
  grid-column: span 2;
  background: var(--bg-tertiary);
  border-radius: 0.5rem;
  padding: 1rem;
  border: 1px solid var(--border-default);
}

.quality-dimensions h4 {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 0 0 1rem 0;
}

.dimension-bars {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.dimension-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.dimension-header {
  display: flex;
  justify-content: space-between;
  font-size: 0.75rem;
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
  border-radius: 9999px;
  overflow: hidden;
}

.dimension-fill {
  height: 100%;
  border-radius: 9999px;
  transition: width 0.5s ease;
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
  border-radius: 0.5rem;
  padding: 1rem;
  border: 1px solid var(--border-default);
}

.issues-summary h4 {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 0 0 0.75rem 0;
}

.issues-counts {
  display: flex;
  gap: 1rem;
}

.issue-count {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
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
  border-radius: 0.5rem;
  padding: 1rem;
  border: 1px solid var(--color-info-light);
}

.recommendations h4 {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-info-dark);
  margin: 0 0 0.75rem 0;
}

.recommendation-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.recommendation-list li {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  font-size: 0.875rem;
  color: var(--color-info-dark);
}

.recommendation-list li i {
  color: var(--color-primary);
  margin-top: 0.125rem;
}

/* Maintenance Sections */
.maintenance-sections {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.maintenance-section {
  background: var(--bg-card);
  border-radius: 0.75rem;
  overflow: hidden;
  box-shadow: var(--shadow-sm);
}

/* Maintenance History */
.maintenance-history {
  background: var(--bg-card);
  border-radius: 0.75rem;
  padding: 1.5rem;
  box-shadow: var(--shadow-sm);
}

.history-content {
  margin-top: 1rem;
}

.empty-history {
  text-align: center;
  padding: 2rem;
  color: var(--text-muted);
}

.empty-history i {
  font-size: 2rem;
  margin-bottom: 0.75rem;
  display: block;
}

.empty-history p {
  margin: 0;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.history-item {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem 1rem;
  background: var(--bg-tertiary);
  border-radius: 0.5rem;
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
  font-size: 0.875rem;
}

.history-content {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.history-action {
  font-weight: 500;
  color: var(--text-primary);
  font-size: 0.875rem;
}

.history-details {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.history-time {
  font-size: 0.75rem;
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
    gap: 1rem;
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
