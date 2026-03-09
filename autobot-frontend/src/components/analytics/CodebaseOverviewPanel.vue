<template>
  <!-- Enhanced Analytics Dashboard Cards -->
  <div class="enhanced-analytics-grid">
      <!-- System Overview -->
      <BasePanel variant="dark" size="medium">
        <template #header>
          <div class="card-header-content">
            <h3><i class="fas fa-tachometer-alt"></i> {{ $t('analytics.codebase.overview.title') }}</h3>
            <div class="refresh-indicator" :class="{ active: realTimeEnabled }">
              <i class="fas fa-circle"></i>
              {{ realTimeEnabled ? $t('analytics.codebase.overview.live') : $t('analytics.codebase.overview.static') }}
            </div>
          </div>
        </template>
        <div v-if="systemOverview" class="metrics-grid">
          <div class="metric-item">
            <div class="metric-label">{{ $t('analytics.codebase.overview.apiRequestsPerMin') }}</div>
            <div class="metric-value">{{ systemOverview.api_requests_per_minute || 0 }}</div>
          </div>
          <div class="metric-item">
            <div class="metric-label">{{ $t('analytics.codebase.overview.avgResponseTime') }}</div>
            <div class="metric-value">{{ systemOverview.average_response_time || 0 }}ms</div>
          </div>
          <div class="metric-item">
            <div class="metric-label">{{ $t('analytics.codebase.overview.activeConnections') }}</div>
            <div class="metric-value">{{ systemOverview.active_connections || 0 }}</div>
          </div>
          <div class="metric-item">
            <div class="metric-label">{{ $t('analytics.codebase.overview.systemHealth') }}</div>
            <div class="metric-value" :class="getHealthClass(systemOverview.system_health)">
              {{ systemOverview.system_health || 'Unknown' }}
            </div>
          </div>
        </div>
        <EmptyState
          v-else
          icon="fas fa-database"
          :message="$t('analytics.codebase.overview.noMetrics')"
        >
          <template #actions>
            <button @click="emit('load-system-overview')" class="btn-link">
              {{ $t('analytics.codebase.actions.loadMetrics') }}
            </button>
          </template>
        </EmptyState>
      </BasePanel>

      <!-- Communication Patterns -->
      <BasePanel variant="dark" size="medium">
        <template #header>
          <div class="card-header-content">
            <h3><i class="fas fa-network-wired"></i> {{ $t('analytics.codebase.communication.title') }}</h3>
            <button @click="emit('load-communication-patterns')" class="refresh-btn">
              <i class="fas fa-sync"></i>
            </button>
          </div>
        </template>
        <div v-if="communicationPatterns" class="communication-metrics">
          <div class="pattern-item">
            <div class="pattern-label">{{ $t('analytics.codebase.communication.websocketConnections') }}</div>
            <div class="pattern-value">{{ communicationPatterns.websocket_connections || 0 }}</div>
          </div>
          <div class="pattern-item">
            <div class="pattern-label">{{ $t('analytics.codebase.communication.apiCallFrequency') }}</div>
            <div class="pattern-value">{{ communicationPatterns.api_call_frequency || 0 }}/min</div>
          </div>
          <div class="pattern-item">
            <div class="pattern-label">{{ $t('analytics.codebase.communication.dataTransferRate') }}</div>
            <div class="pattern-value">{{ communicationPatterns.data_transfer_rate || 0 }} KB/s</div>
          </div>
        </div>
        <EmptyState
          v-else
          icon="fas fa-wifi"
          :message="$t('analytics.codebase.communication.noData')"
        />
      </BasePanel>

      <!-- Code Quality -->
      <BasePanel variant="dark" size="medium">
        <template #header>
          <div class="card-header-content">
            <h3><i class="fas fa-code-branch"></i> {{ $t('analytics.codebase.quality.title') }}</h3>
            <button @click="emit('load-code-quality')" class="refresh-btn">
              <i class="fas fa-sync"></i>
            </button>
          </div>
        </template>
        <div v-if="codeQuality" class="quality-metrics">
          <div class="quality-score" :class="getQualityClass(codeQuality.overall_score)">
            <div class="score-value">{{ codeQuality.overall_score || 0 }}</div>
            <div class="score-label">{{ $t('analytics.codebase.quality.overallScore') }}</div>
          </div>
          <div class="quality-details">
            <div class="quality-item">
              <span class="quality-label">{{ $t('analytics.codebase.quality.testCoverage') }}:</span>
              <span class="quality-value">{{ codeQuality.test_coverage || 0 }}%</span>
            </div>
            <div class="quality-item">
              <span class="quality-label">{{ $t('analytics.codebase.quality.codeDuplicates') }}:</span>
              <span class="quality-value">{{ codeQuality.code_duplicates || 0 }}</span>
            </div>
            <div class="quality-item">
              <span class="quality-label">{{ $t('analytics.codebase.quality.technicalDebt') }}:</span>
              <span class="quality-value">{{ codeQuality.technical_debt || 0 }}h</span>
            </div>
          </div>
        </div>
        <EmptyState
          v-else
          icon="fas fa-star"
          :message="$t('analytics.codebase.quality.noMetrics')"
        />
      </BasePanel>

      <!-- Performance Metrics -->
      <BasePanel variant="dark" size="medium">
        <template #header>
          <div class="card-header-content">
            <h3><i class="fas fa-bolt"></i> {{ $t('analytics.codebase.performance.title') }}</h3>
            <button @click="emit('load-performance-metrics')" class="refresh-btn">
              <i class="fas fa-sync"></i>
            </button>
          </div>
        </template>
        <div v-if="performanceMetrics" class="performance-metrics-content">
          <div class="performance-gauge" :class="getEfficiencyClass(performanceMetrics.efficiency_score)">
            <div class="gauge-value">{{ performanceMetrics.efficiency_score || 0 }}%</div>
            <div class="gauge-label">{{ $t('analytics.codebase.performance.efficiency') }}</div>
          </div>
          <div class="performance-details">
            <div class="performance-item">
              <span class="performance-label">{{ $t('analytics.codebase.performance.memoryUsage') }}:</span>
              <span class="performance-value">{{ performanceMetrics.memory_usage || 0 }}MB</span>
            </div>
            <div class="performance-item">
              <span class="performance-label">{{ $t('analytics.codebase.performance.cpuUsage') }}:</span>
              <span class="performance-value">{{ performanceMetrics.cpu_usage || 0 }}%</span>
            </div>
            <div class="performance-item">
              <span class="performance-label">{{ $t('analytics.codebase.performance.loadTime') }}:</span>
              <span class="performance-value">{{ performanceMetrics.load_time || 0 }}ms</span>
            </div>
          </div>
        </div>
        <EmptyState
          v-else
          icon="fas fa-rocket"
          :message="$t('analytics.codebase.performance.noData')"
        />
      </BasePanel>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import EmptyState from '@/components/ui/EmptyState.vue'
import BasePanel from '@/components/base/BasePanel.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('CodebaseOverviewPanel')

useI18n()

interface SystemOverviewData {
  api_requests_per_minute: number
  average_response_time: number
  active_connections: number
  system_health: string
}

interface CommunicationPatternsData {
  websocket_connections: number
  api_call_frequency: number
  data_transfer_rate: number
}

interface CodeQualityData {
  overall_score: number
  test_coverage: number
  code_duplicates: number
  technical_debt: number
}

interface PerformanceMetricsData {
  efficiency_score: number
  memory_usage: number
  cpu_usage: number
  load_time: number
}

interface Props {
  systemOverview: SystemOverviewData | null
  communicationPatterns: CommunicationPatternsData | null
  codeQuality: CodeQualityData | null
  performanceMetrics: PerformanceMetricsData | null
}

defineProps<Props>()

const emit = defineEmits<{
  'load-system-overview': []
  'load-communication-patterns': []
  'load-code-quality': []
  'load-performance-metrics': []
}>()

const getHealthClass = (health: string | undefined): string => {
  logger.debug('getHealthClass called', { health })
  switch (health?.toLowerCase()) {
    case 'healthy':
      return 'health-good'
    case 'warning':
      return 'health-warning'
    case 'critical':
      return 'health-critical'
    default:
      return 'health-unknown'
  }
}

const getEfficiencyClass = (score: number): string => {
  if (score >= 80) return 'efficiency-high'
  if (score >= 60) return 'efficiency-medium'
  return 'efficiency-low'
}

const getQualityClass = (score: number): string => {
  if (score >= 80) return 'quality-high'
  if (score >= 60) return 'quality-medium'
  return 'quality-low'
}
</script>

<style scoped>
.enhanced-analytics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 20px;
  margin-bottom: 32px;
}

.card-header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.card-header-content h3 {
  margin: 0;
  color: var(--text-primary);
  font-size: 1.1em;
  font-weight: 600;
}

.refresh-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.8em;
  color: var(--text-muted);
}

.refresh-indicator.active {
  color: var(--chart-green);
}

.refresh-indicator .fas {
  font-size: 0.7em;
}

.refresh-btn {
  background: var(--bg-tertiary);
  border: 1px solid var(--bg-hover);
  color: var(--text-secondary);
  padding: 6px 8px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.refresh-btn:hover {
  background: var(--bg-hover);
  color: var(--text-on-primary);
}

/* Issue #609: Section Export Buttons */
.section-export-buttons {
  display: inline-flex;
  gap: 4px;
  margin-left: 10px;
}

.export-btn {
  background: var(--bg-secondary);
  border: 1px solid var(--bg-tertiary);
  color: var(--text-muted);
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.2s;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.export-btn:hover {
  background: var(--bg-tertiary);
  color: var(--color-info);
  border-color: var(--color-info);
}

.export-btn i {
  font-size: 0.7rem;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.metric-item {
  text-align: center;
}

.metric-label {
  font-size: 0.8em;
  color: var(--text-muted);
  margin-bottom: 4px;
}

.metric-value {
  font-size: 1.4em;
  font-weight: 700;
  color: var(--text-on-primary);
}

.metric-value.health-good { color: var(--chart-green); }
.metric-value.health-warning { color: var(--color-warning); }
.metric-value.health-critical { color: var(--color-error); }
.metric-value.health-unknown { color: var(--text-tertiary); }

.communication-metrics,
.performance-details,
.quality-details {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.pattern-item,
.performance-item,
.quality-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid var(--bg-tertiary);
}

.pattern-item:last-child,
.performance-item:last-child,
.quality-item:last-child {
  border-bottom: none;
}

.pattern-label,
.performance-label,
.quality-label {
  color: var(--text-secondary);
  font-size: 0.9em;
}

.pattern-value,
.performance-value,
.quality-value {
  color: var(--text-on-primary);
  font-weight: 600;
}

.quality-score,
.performance-gauge {
  text-align: center;
  margin-bottom: 16px;
  padding: 16px;
  border-radius: 8px;
}

.score-value,
.gauge-value {
  font-size: 2.5em;
  font-weight: 700;
  margin-bottom: 4px;
}

.score-label,
.gauge-label {
  font-size: 0.9em;
  color: var(--text-muted);
}

.quality-high,
.efficiency-high {
  background: rgba(34, 197, 94, 0.1);
  color: var(--chart-green);
}

.quality-medium,
.efficiency-medium {
  background: rgba(251, 191, 36, 0.1);
  color: var(--color-warning-light);
}

.quality-low,
.efficiency-low {
  background: rgba(239, 68, 68, 0.1);
  color: var(--color-error);
}

.btn-link {
  background: none;
  border: none;
  color: var(--chart-blue);
  cursor: pointer;
  text-decoration: underline;
  font-size: 0.9em;
}

.btn-link:hover {
  color: var(--color-info-dark);
}

/* Traditional Analytics Section */
.analytics-section {
  background: var(--bg-secondary);
  border-radius: 12px;
  padding: 24px;
  border: 1px solid var(--bg-tertiary);
}

.real-time-controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--bg-tertiary);
}

.toggle-switch {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  color: var(--text-secondary);
}

.toggle-switch input {
  display: none;
}

.toggle-slider {
  width: 40px;
  height: 20px;
  background: var(--bg-tertiary);
  border-radius: 10px;
  position: relative;
  transition: all 0.3s;
}

.toggle-slider:before {
  content: '';
  width: 16px;
  height: 16px;
  background: var(--text-on-primary);
  border-radius: 50%;
  position: absolute;
  top: 2px;
  left: 2px;
  transition: all 0.3s;
}

.toggle-switch input:checked + .toggle-slider {
  background: var(--chart-green);
}

.toggle-switch input:checked + .toggle-slider:before {
  transform: translateX(20px);
}

.refresh-all-btn {
  background: var(--chart-indigo);
  color: var(--text-on-primary);
  border: none;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 8px;
}

.refresh-all-btn:hover {
  background: var(--chart-indigo-dark);
}

.stats-section {
  margin-bottom: 32px;
}

.stats-section h3 {
  color: var(--text-primary);
  margin-bottom: 16px;
  font-size: 1.2em;
  font-weight: 600;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 16px;
}

.stat-value {
  font-size: 2em;
  font-weight: 700;
  color: var(--chart-green);
  margin-bottom: 4px;
  text-align: center;
}

.stat-label {
  color: var(--text-muted);
  font-size: 0.9em;
  text-align: center;
}

.performance-metrics-content {
  display: flex;
  flex-direction: column;
}

@media (max-width: 768px) {
  .enhanced-analytics-grid {
    grid-template-columns: 1fr;
  }

  .metrics-grid {
    grid-template-columns: 1fr;
  }

  .real-time-controls {
    flex-direction: column;
    gap: 12px;
    align-items: stretch;
  }

  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 480px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }
}
</style>
