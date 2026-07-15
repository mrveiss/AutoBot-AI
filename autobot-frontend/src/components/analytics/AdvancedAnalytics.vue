<template>
  <div class="advanced-analytics">
    <!-- Header -->
    <div class="analytics-header">
      <h2><Icon name="chart-pie" /> {{ $t('analytics.advanced.title') }}</h2>
      <div class="header-actions">
        <BaseButton variant="secondary" size="sm" @click="refreshAll" :loading="loading">
          <Icon name="sync" /> {{ $t('analytics.advanced.refresh') }}
        </BaseButton>
        <BaseButton variant="primary" size="sm" @click="showExportModal = true">
          <Icon name="download" /> {{ $t('analytics.advanced.export') }}
        </BaseButton>
      </div>
    </div>

    <!-- Tab Navigation -->
    <div class="analytics-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        :class="['tab-btn', { active: activeTab === tab.id }]"
        @click="activeTab = tab.id"
      >
        <Icon :name="tab.icon" />
        {{ tab.label }}
      </button>
    </div>

    <!-- Cost Analytics Tab -->
    <div v-if="activeTab === 'cost'" class="tab-content">
      <div class="metrics-grid">
        <!-- Total Cost Card -->
        <BasePanel variant="bordered" size="sm">
          <template #header>
            <h4><Icon name="dollar-sign" /> {{ $t('analytics.advanced.totalCost30d') }}</h4>
          </template>
          <div class="metric-value large">
            ${{ costSummary?.total_cost_usd?.toFixed(2) || '0.00' }}
          </div>
          <div class="metric-trend" :class="costTrend">
            <Icon :name="trendIcon" />
            {{ costTrends?.growth_rate_percent?.toFixed(1) || 0 }}% {{ $t('analytics.advanced.vsPreviousPeriod') }}
          </div>
        </BasePanel>

        <!-- Daily Average Card -->
        <BasePanel variant="bordered" size="sm">
          <template #header>
            <h4><Icon name="calendar" /> {{ $t('analytics.advanced.dailyAverage') }}</h4>
          </template>
          <div class="metric-value">
            ${{ costSummary?.avg_daily_cost?.toFixed(2) || '0.00' }}
          </div>
        </BasePanel>

        <!-- Trend Card -->
        <BasePanel variant="bordered" size="sm">
          <template #header>
            <h4><Icon name="arrow-trend-up" /> {{ $t('analytics.advanced.costTrend') }}</h4>
          </template>
          <div class="metric-value" :class="costTrend">
            {{ costTrends?.trend || 'stable' }}
          </div>
        </BasePanel>
      </div>

      <!-- Cost by Model Table -->
      <BasePanel variant="elevated" class="mt-4">
        <template #header>
          <h4><Icon name="robot" /> {{ $t('analytics.advanced.costByModel') }}</h4>
        </template>
        <table class="data-table" v-if="modelCosts?.length">
          <thead>
            <tr>
              <th>{{ $t('analytics.advanced.model') }}</th>
              <th class="text-right">{{ $t('analytics.advanced.costUsd') }}</th>
              <th class="text-right">{{ $t('analytics.advanced.inputTokens') }}</th>
              <th class="text-right">{{ $t('analytics.advanced.outputTokens') }}</th>
              <th class="text-right">{{ $t('analytics.advanced.calls') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="model in modelCosts" :key="model.model">
              <td>{{ model.model }}</td>
              <td class="text-right">${{ model.cost_usd?.toFixed(4) }}</td>
              <td class="text-right">{{ formatNumber(model.input_tokens) }}</td>
              <td class="text-right">{{ formatNumber(model.output_tokens) }}</td>
              <td class="text-right">{{ formatNumber(model.call_count) }}</td>
            </tr>
          </tbody>
        </table>
        <EmptyState v-else icon="chart-bar" :message="$t('analytics.advanced.noCostData')" />
      </BasePanel>
    </div>

    <!-- Agent Performance Tab -->
    <div v-if="activeTab === 'agents'" class="tab-content">
      <div class="metrics-grid">
        <!-- Total Agents -->
        <BasePanel variant="bordered" size="sm">
          <template #header>
            <h4><Icon name="users-cog" /> {{ $t('analytics.advanced.totalAgents') }}</h4>
          </template>
          <div class="metric-value large">{{ agentMetrics?.total_agents || 0 }}</div>
        </BasePanel>

        <!-- Total Tasks -->
        <BasePanel variant="bordered" size="sm">
          <template #header>
            <h4><Icon name="tasks" /> {{ $t('analytics.advanced.totalTasks') }}</h4>
          </template>
          <div class="metric-value">
            {{ formatNumber(agentMetrics?.summary?.total_tasks || 0) }}
          </div>
        </BasePanel>

        <!-- Avg Success Rate -->
        <BasePanel variant="bordered" size="sm">
          <template #header>
            <h4><Icon name="check-circle" /> {{ $t('analytics.advanced.avgSuccessRate') }}</h4>
          </template>
          <div class="metric-value success">
            {{ agentMetrics?.summary?.avg_success_rate?.toFixed(1) || 0 }}%
          </div>
        </BasePanel>
      </div>

      <!-- Agent Performance Table -->
      <BasePanel variant="elevated" class="mt-4">
        <template #header>
          <h4><Icon name="chart-line" /> {{ $t('analytics.advanced.agentPerformance') }}</h4>
        </template>
        <table class="data-table" v-if="agentMetrics?.agents?.length">
          <thead>
            <tr>
              <th>{{ $t('analytics.advanced.agentId') }}</th>
              <th>{{ $t('analytics.advanced.type') }}</th>
              <th class="text-right">{{ $t('analytics.advanced.tasks') }}</th>
              <th class="text-right">{{ $t('analytics.advanced.successRate') }}</th>
              <th class="text-right">{{ $t('analytics.advanced.errorRate') }}</th>
              <th class="text-right">{{ $t('analytics.advanced.avgDuration') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="agent in agentMetrics.agents" :key="agent.agent_id">
              <td>{{ agent.agent_id }}</td>
              <td><span class="badge">{{ agent.agent_type }}</span></td>
              <td class="text-right">{{ agent.total_tasks }}</td>
              <td class="text-right" :class="getSuccessClass(agent.success_rate)">
                {{ agent.success_rate?.toFixed(1) }}%
              </td>
              <td class="text-right" :class="getErrorClass(agent.error_rate)">
                {{ agent.error_rate?.toFixed(1) }}%
              </td>
              <td class="text-right">{{ formatDuration(agent.avg_duration_ms) }}</td>
            </tr>
          </tbody>
        </table>
        <EmptyState v-else icon="robot" :message="$t('analytics.advanced.noAgentData')" />
      </BasePanel>

      <!-- Recommendations -->
      <BasePanel variant="bordered" class="mt-4" v-if="recommendations?.recommendations?.length">
        <template #header>
          <h4><Icon name="lightbulb" /> {{ $t('analytics.advanced.recommendations') }}</h4>
        </template>
        <div class="recommendations-list">
          <div
            v-for="rec in recommendations.recommendations"
            :key="rec.agent_id"
            class="recommendation-item"
          >
            <strong>{{ rec.agent_id }}</strong> ({{ rec.agent_type }})
            <ul>
              <li
                v-for="(r, idx) in rec.recommendations"
                :key="idx"
                :class="'severity-' + r.severity"
              >
                <Icon :name="getSeverityIcon(r.severity)" />
                {{ r.message }} - <em>{{ r.suggestion }}</em>
              </li>
            </ul>
          </div>
        </div>
      </BasePanel>
    </div>

    <!-- User Behavior Tab -->
    <div v-if="activeTab === 'behavior'" class="tab-content">
      <div class="metrics-grid">
        <!-- Total Sessions -->
        <BasePanel variant="bordered" size="sm">
          <template #header>
            <h4><Icon name="users" /> {{ $t('analytics.advanced.totalSessions') }}</h4>
          </template>
          <div class="metric-value large">
            {{ formatNumber(engagementMetrics?.metrics?.total_sessions || 0) }}
          </div>
        </BasePanel>

        <!-- Page Views -->
        <BasePanel variant="bordered" size="sm">
          <template #header>
            <h4><Icon name="eye" /> {{ $t('analytics.advanced.pageViews') }}</h4>
          </template>
          <div class="metric-value">
            {{ formatNumber(engagementMetrics?.metrics?.total_page_views || 0) }}
          </div>
        </BasePanel>

        <!-- Avg Session Duration -->
        <BasePanel variant="bordered" size="sm">
          <template #header>
            <h4><Icon name="clock" /> {{ $t('analytics.advanced.avgSessionDuration') }}</h4>
          </template>
          <div class="metric-value">
            {{ formatDuration(engagementMetrics?.metrics?.avg_session_duration_ms || 0) }}
          </div>
        </BasePanel>

        <!-- Pages Per Session -->
        <BasePanel variant="bordered" size="sm">
          <template #header>
            <h4><Icon name="file-alt" /> {{ $t('analytics.advanced.pagesPerSession') }}</h4>
          </template>
          <div class="metric-value">
            {{ engagementMetrics?.metrics?.pages_per_session?.toFixed(1) || '0.0' }}
          </div>
        </BasePanel>
      </div>

      <!-- Feature Popularity -->
      <BasePanel variant="elevated" class="mt-4">
        <template #header>
          <h4><Icon name="star" /> {{ $t('analytics.advanced.featurePopularity') }}</h4>
        </template>
        <table class="data-table" v-if="engagementMetrics?.feature_popularity?.length">
          <thead>
            <tr>
              <th>{{ $t('analytics.advanced.feature') }}</th>
              <th class="text-right">{{ $t('analytics.advanced.views') }}</th>
              <th class="text-right">{{ $t('analytics.advanced.popularity') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(feature, idx) in engagementMetrics.feature_popularity" :key="feature.feature">
              <td>
                <span class="rank-badge" :class="'rank-' + ((idx as number) + 1)">{{ (idx as number) + 1 }}</span>
                {{ feature.feature }}
              </td>
              <td class="text-right">{{ formatNumber(feature.views) }}</td>
              <td class="text-right">
                <div class="popularity-bar">
                  <div
                    class="popularity-fill"
                    :style="{ width: getPopularityWidth(feature.views) }"
                  ></div>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        <EmptyState v-else icon="chart-bar" :message="$t('analytics.advanced.noFeatureData')" />
      </BasePanel>

      <!-- Usage Heatmap -->
      <BasePanel variant="bordered" class="mt-4" v-if="usageHeatmap?.peak_hours?.length">
        <template #header>
          <h4><Icon name="bolt" /> {{ $t('analytics.advanced.peakUsageHours') }}</h4>
        </template>
        <div class="peak-hours-list">
          <div
            v-for="(peak, idx) in usageHeatmap.peak_hours"
            :key="peak.hour"
            class="peak-hour-item"
          >
            <span class="peak-rank">{{ (idx as number) + 1 }}</span>
            <span class="peak-time">{{ peak.hour }}:00</span>
            <span class="peak-events">{{ formatNumber(peak.total_events) }} {{ $t('analytics.advanced.events') }}</span>
          </div>
        </div>
      </BasePanel>
    </div>

    <!-- Export Tab -->
    <div v-if="activeTab === 'export'" class="tab-content">
      <div class="export-grid">
        <BasePanel
          v-for="format in exportFormats"
          :key="format.format"
          variant="bordered"
          class="export-card"
        >
          <template #header>
            <h4><Icon :name="format.icon" /> {{ format.format }}</h4>
          </template>
          <p>{{ format.description }}</p>
          <div class="export-actions">
            <BaseButton
              v-for="endpoint in format.endpoints"
              :key="endpoint.path"
              variant="outline-solid"
              size="sm"
              @click="downloadExport(endpoint.path)"
            >
              {{ endpoint.description }}
            </BaseButton>
          </div>
        </BasePanel>
      </div>
    </div>

    <!-- Loading Overlay -->
    <div v-if="loading" class="loading-overlay">
      <Icon name="spinner" class="animate-spin" />
      <span>{{ $t('analytics.advanced.loading') }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { IconName } from '@/components/ui/Icon.vue'
import Icon from '@/components/ui/Icon.vue'
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import BasePanel from '@/components/base/BasePanel.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import api from '@/services/api'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'

const { t } = useI18n()

const logger = createLogger('AdvancedAnalytics')

// Issue #701: Type for API response with data property
interface ApiDataResponse {
  data?: unknown
  [key: string]: unknown
}

// Domain shapes for analytics responses (fields consumed by the template)
interface CostSummary {
  total_cost_usd?: number
  avg_daily_cost?: number
}

interface CostTrends {
  trend?: string
  growth_rate_percent?: number
}

interface ModelCost {
  model: string
  cost_usd?: number
  input_tokens: number
  output_tokens: number
  call_count: number
}

interface ModelCostsData {
  models?: ModelCost[]
}

interface AgentPerformance {
  agent_id: string
  agent_type?: string
  total_tasks?: number
  success_rate: number
  error_rate: number
  avg_duration_ms: number
}

interface AgentMetrics {
  total_agents?: number
  summary?: {
    total_tasks?: number
    avg_success_rate?: number
  }
  agents?: AgentPerformance[]
}

interface AgentRecommendationDetail {
  severity: string
  message: string
  suggestion: string
}

interface AgentRecommendation {
  agent_id: string
  agent_type?: string
  recommendations: AgentRecommendationDetail[]
}

interface Recommendations {
  recommendations?: AgentRecommendation[]
}

interface ExportEndpoint {
  path: string
  description: string
}

interface ExportFormat {
  format: string
  description: string
  icon: IconName
  endpoints: ExportEndpoint[]
}

interface ExportFormatsData {
  formats?: ExportFormat[]
}

interface EngagementMetricsData {
  metrics?: {
    total_sessions?: number
    total_page_views?: number
    avg_session_duration_ms?: number
    pages_per_session?: number
  }
  feature_popularity?: FeaturePopularity[]
}

interface FeaturePopularity {
  feature: string
  views: number
}

interface PeakHour {
  hour: number
  total_events: number
}

interface UsageHeatmap {
  peak_hours?: PeakHour[]
}

// State
const loading = ref(false)
const activeTab = ref('cost')
const showExportModal = ref(false)

// Data
const costSummary = ref<CostSummary | null>(null)
const costTrends = ref<CostTrends | null>(null)
const modelCosts = ref<ModelCost[]>([])
const agentMetrics = ref<AgentMetrics | null>(null)
const recommendations = ref<Recommendations | null>(null)
const exportFormats = ref<ExportFormat[]>([])
const behaviorMetrics = ref<unknown>(null)
const engagementMetrics = ref<EngagementMetricsData | null>(null)
const usageHeatmap = ref<UsageHeatmap | null>(null)

// Tabs configuration
const tabs = computed(() => [
  { id: 'cost', label: t('analytics.advanced.tabs.cost'), icon: 'dollar-sign' as const },
  { id: 'agents', label: t('analytics.advanced.tabs.agents'), icon: 'robot' as const },
  { id: 'behavior', label: t('analytics.advanced.tabs.behavior'), icon: 'users' as const },
  { id: 'export', label: t('analytics.advanced.tabs.export'), icon: 'download' as const }
])

// Computed
const costTrend = computed(() => {
  const trend = costTrends.value?.trend
  if (trend === 'increasing') return 'trend-up'
  if (trend === 'decreasing') return 'trend-down'
  return 'trend-stable'
})

const trendIcon = computed(() => {
  const trend = costTrends.value?.trend
  if (trend === 'increasing') return 'arrow-up'
  if (trend === 'decreasing') return 'arrow-down'
  return 'minus'
})

// Methods
const formatNumber = (num: number): string => {
  if (!num) return '0'
  return num.toLocaleString()
}

const formatDuration = (ms: number): string => {
  if (!ms) return '0ms'
  if (ms < 1000) return `${ms.toFixed(0)}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

const getSuccessClass = (rate: number): string => {
  if (rate >= 90) return 'success'
  if (rate >= 70) return 'warning'
  return 'error'
}

const getErrorClass = (rate: number): string => {
  if (rate < 5) return 'success'
  if (rate < 15) return 'warning'
  return 'error'
}

const getSeverityIcon = (severity: string): IconName => {
  if (severity === 'high') return 'exclamation-circle'
  if (severity === 'medium') return 'exclamation-triangle'
  return 'info-circle'
}

const fetchCostData = async () => {
  try {
    // Issue #552: Fixed missing /api prefix in analytics endpoints
    // Issue #701: Added type assertions for Promise.all results
    const [summaryRes, trendsRes, modelsRes] = await Promise.all([
      api.get<ApiDataResponse>(`${getApiBase()}/analytics/cost/summary`),
      api.get<ApiDataResponse>(`${getApiBase()}/analytics/cost/trends`),
      api.get<ApiDataResponse>(`${getApiBase()}/analytics/cost/by-model`)
    ])
    costSummary.value = (summaryRes as ApiDataResponse).data as CostSummary | null
    costTrends.value = (trendsRes as ApiDataResponse).data as CostTrends | null
    modelCosts.value = ((modelsRes as ApiDataResponse).data as ModelCostsData | undefined)?.models || []
  } catch (error) {
    logger.error('Failed to fetch cost data:', error)
  }
}

const fetchAgentData = async () => {
  try {
    // Issue #552: Fixed missing /api prefix in analytics endpoints
    // Issue #701: Added type assertions for Promise.all results
    const [metricsRes, recsRes] = await Promise.all([
      api.get<ApiDataResponse>(`${getApiBase()}/analytics/agents/performance`),
      api.get<ApiDataResponse>(`${getApiBase()}/analytics/agents/recommendations`)
    ])
    agentMetrics.value = (metricsRes as ApiDataResponse).data as AgentMetrics | null
    recommendations.value = (recsRes as ApiDataResponse).data as Recommendations | null
  } catch (error) {
    logger.error('Failed to fetch agent data:', error)
  }
}

const fetchExportFormats = async () => {
  try {
    // Issue #552: Fixed missing /api prefix in analytics endpoints
    // Issue #701: Added type assertion for response
    const res = await api.get<ApiDataResponse>(`${getApiBase()}/analytics/export/formats`)
    exportFormats.value = ((res as ApiDataResponse).data as ExportFormatsData | undefined)?.formats || []
    // Add icons
    exportFormats.value.forEach((f: ExportFormat) => {
      if (f.format === 'CSV') f.icon = 'file-csv'
      else if (f.format === 'JSON') f.icon = 'file-code'
      else if (f.format === 'Prometheus') f.icon = 'chart-area'
      else if (f.format === 'Grafana') f.icon = 'tachometer-alt'
      else f.icon = 'file'
    })
  } catch (error) {
    logger.error('Failed to fetch export formats:', error)
  }
}

const fetchBehaviorData = async () => {
  try {
    // Issue #552: Fixed missing /api prefix in analytics endpoints
    // Issue #701: Added type assertions for Promise.all results
    const [engagementRes, featuresRes, heatmapRes] = await Promise.all([
      api.get<ApiDataResponse>(`${getApiBase()}/analytics/behavior/engagement`),
      api.get<ApiDataResponse>(`${getApiBase()}/analytics/behavior/features`),
      api.get<ApiDataResponse>(`${getApiBase()}/analytics/behavior/stats/heatmap`)
    ])
    engagementMetrics.value = (engagementRes as ApiDataResponse).data as EngagementMetricsData | null
    behaviorMetrics.value = (featuresRes as ApiDataResponse).data
    usageHeatmap.value = (heatmapRes as ApiDataResponse).data as UsageHeatmap | null
  } catch (error) {
    logger.error('Failed to fetch behavior data:', error)
  }
}

const maxFeatureViews = computed((): number => {
  if (!engagementMetrics.value?.feature_popularity?.length) return 0
  return Math.max(...engagementMetrics.value.feature_popularity.map((f: FeaturePopularity) => f.views || 0))
})

const getPopularityWidth = (views: number): string => {
  const maxViews = maxFeatureViews.value
  if (maxViews === 0) return '0%'
  return `${(views / maxViews) * 100}%`
}

const downloadExport = async (path: string) => {
  try {
    // Issue #701: Fixed api.get call - use responseType option properly
    const response = await api.get<Blob>(path, { responseType: 'blob' })
    const url = window.URL.createObjectURL(new Blob([response as unknown as BlobPart]))
    const link = document.createElement('a')
    link.href = url
    // Extract filename from path
    const filename = path.split('/').pop() + (path.includes('csv') ? '.csv' : '.json')
    link.setAttribute('download', filename)
    document.body.appendChild(link)
    link.click()
    link.remove()
  } catch (error) {
    logger.error('Failed to download export:', error)
  }
}

const refreshAll = async () => {
  loading.value = true
  try {
    await Promise.all([
      fetchCostData(),
      fetchAgentData(),
      fetchBehaviorData(),
      fetchExportFormats()
    ])
  } finally {
    loading.value = false
  }
}

// Lifecycle
onMounted(() => {
  refreshAll()
})
</script>

<style scoped>
.advanced-analytics {
  padding: var(--spacing-6);
  position: relative;
}

.analytics-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-6);
}

.analytics-header h2 {
  margin: var(--spacing-0);
  color: var(--text-primary);
}

.header-actions {
  display: flex;
  gap: var(--spacing-2);
}

.analytics-tabs {
  display: flex;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-6);
  border-bottom: 1px solid var(--border-default);
  padding-bottom: var(--spacing-2);
}

.tab-btn {
  padding: var(--spacing-2) var(--spacing-4);
  border: none;
  background: none;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: var(--radius-default);
  transition: all var(--duration-200);
}

.tab-btn:hover {
  background: var(--bg-tertiary);
}

.tab-btn.active {
  background: var(--color-primary);
  color: var(--text-on-primary);
}

.tab-btn i {
  margin-right: var(--spacing-2);
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--spacing-4);
}

.metric-value {
  font-size: var(--text-2xl);
  font-weight: 600;
  color: var(--text-primary);
}

.metric-value.large {
  font-size: 2rem;
}

.metric-value.success {
  color: var(--color-success);
}

.metric-trend {
  margin-top: var(--spacing-2);
  font-size: var(--text-sm);
}

.trend-up {
  color: var(--color-error);
}

.trend-down {
  color: var(--color-success);
}

.trend-stable {
  color: var(--text-secondary);
}

.data-table {
  width: 100%;
  border-collapse: collapse;
}

.data-table th,
.data-table td {
  padding: var(--spacing-3);
  text-align: left;
  border-bottom: 1px solid var(--border-default);
}

.data-table th {
  font-weight: 600;
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.text-right {
  text-align: right;
}

.badge {
  display: inline-block;
  padding: var(--spacing-1) var(--spacing-2);
  background: var(--bg-tertiary);
  border-radius: var(--radius-default);
  font-size: var(--text-xs);
}

.success {
  color: var(--color-success);
}

.warning {
  color: var(--color-warning);
}

.error {
  color: var(--color-error);
}

.mt-4 {
  margin-top: var(--spacing-4);
}

.recommendations-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

.recommendation-item ul {
  margin: var(--spacing-2) var(--spacing-0) var(--spacing-0) var(--spacing-6);
  padding: var(--spacing-0);
}

.recommendation-item li {
  margin: var(--spacing-1) var(--spacing-0);
}

.severity-high {
  color: var(--color-error);
}

.severity-medium {
  color: var(--color-warning);
}

.severity-low {
  color: var(--text-secondary);
}

.export-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: var(--spacing-4);
}

.export-card p {
  color: var(--text-secondary);
  margin: var(--spacing-2) var(--spacing-0) var(--spacing-4);
}

.export-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
}

/* Issue #704: Migrated to CSS design tokens */
.loading-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--overlay-bg, rgba(0, 0, 0, 0.5));
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-4);
  color: var(--text-on-primary);
  z-index: 100;
}

/* User Behavior Tab Styles */
.rank-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.5rem;
  height: 1.5rem;
  border-radius: 50%;
  font-size: var(--text-xs);
  font-weight: 600;
  margin-right: var(--spacing-2);
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.rank-1 {
  background: var(--color-warning);
  color: var(--text-primary);
}

.rank-2 {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.rank-3 {
  background: var(--chart-orange, #f97316);
  color: var(--text-on-primary);
}

.popularity-bar {
  width: 100px;
  height: 8px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-default);
  overflow: hidden;
}

.popularity-fill {
  height: 100%;
  background: var(--color-primary);
  border-radius: var(--radius-default);
  transition: width var(--duration-300) var(--ease-out);
}

.peak-hours-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.peak-hour-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  padding: var(--spacing-3);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
}

.peak-rank {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.5rem;
  height: 1.5rem;
  background: var(--color-primary);
  color: var(--text-on-primary);
  border-radius: 50%;
  font-size: var(--text-xs);
  font-weight: 600;
}

.peak-time {
  font-weight: 600;
  color: var(--text-primary);
  min-width: 60px;
}

.peak-events {
  color: var(--text-secondary);
  font-size: var(--text-sm);
}
</style>
