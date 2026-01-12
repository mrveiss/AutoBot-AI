<template>
  <div class="advanced-analytics">
    <!-- Header -->
    <div class="analytics-header">
      <h2><i class="fas fa-chart-pie"></i> Advanced Analytics & BI</h2>
      <div class="header-actions">
        <BaseButton variant="secondary" size="sm" @click="refreshAll" :loading="loading">
          <i class="fas fa-sync"></i> Refresh
        </BaseButton>
        <BaseButton variant="primary" size="sm" @click="showExportModal = true">
          <i class="fas fa-download"></i> Export
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
        <i :class="tab.icon"></i>
        {{ tab.label }}
      </button>
    </div>

    <!-- Cost Analytics Tab -->
    <div v-if="activeTab === 'cost'" class="tab-content">
      <div class="metrics-grid">
        <!-- Total Cost Card -->
        <BasePanel variant="bordered" size="small">
          <template #header>
            <h4><i class="fas fa-dollar-sign"></i> Total Cost (30 days)</h4>
          </template>
          <div class="metric-value large">
            ${{ costSummary?.total_cost_usd?.toFixed(2) || '0.00' }}
          </div>
          <div class="metric-trend" :class="costTrend">
            <i :class="trendIcon"></i>
            {{ costTrends?.growth_rate_percent?.toFixed(1) || 0 }}% vs previous period
          </div>
        </BasePanel>

        <!-- Daily Average Card -->
        <BasePanel variant="bordered" size="small">
          <template #header>
            <h4><i class="fas fa-calendar-day"></i> Daily Average</h4>
          </template>
          <div class="metric-value">
            ${{ costSummary?.avg_daily_cost?.toFixed(2) || '0.00' }}
          </div>
        </BasePanel>

        <!-- Trend Card -->
        <BasePanel variant="bordered" size="small">
          <template #header>
            <h4><i class="fas fa-trending-up"></i> Cost Trend</h4>
          </template>
          <div class="metric-value" :class="costTrend">
            {{ costTrends?.trend || 'stable' }}
          </div>
        </BasePanel>
      </div>

      <!-- Cost by Model Table -->
      <BasePanel variant="elevated" class="mt-4">
        <template #header>
          <h4><i class="fas fa-robot"></i> Cost by Model</h4>
        </template>
        <table class="data-table" v-if="modelCosts?.length">
          <thead>
            <tr>
              <th>Model</th>
              <th class="text-right">Cost (USD)</th>
              <th class="text-right">Input Tokens</th>
              <th class="text-right">Output Tokens</th>
              <th class="text-right">Calls</th>
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
        <EmptyState v-else icon="fas fa-chart-bar" message="No cost data available" />
      </BasePanel>
    </div>

    <!-- Agent Performance Tab -->
    <div v-if="activeTab === 'agents'" class="tab-content">
      <div class="metrics-grid">
        <!-- Total Agents -->
        <BasePanel variant="bordered" size="small">
          <template #header>
            <h4><i class="fas fa-users-cog"></i> Total Agents</h4>
          </template>
          <div class="metric-value large">{{ agentMetrics?.total_agents || 0 }}</div>
        </BasePanel>

        <!-- Total Tasks -->
        <BasePanel variant="bordered" size="small">
          <template #header>
            <h4><i class="fas fa-tasks"></i> Total Tasks</h4>
          </template>
          <div class="metric-value">
            {{ formatNumber(agentMetrics?.summary?.total_tasks || 0) }}
          </div>
        </BasePanel>

        <!-- Avg Success Rate -->
        <BasePanel variant="bordered" size="small">
          <template #header>
            <h4><i class="fas fa-check-circle"></i> Avg Success Rate</h4>
          </template>
          <div class="metric-value success">
            {{ agentMetrics?.summary?.avg_success_rate?.toFixed(1) || 0 }}%
          </div>
        </BasePanel>
      </div>

      <!-- Agent Performance Table -->
      <BasePanel variant="elevated" class="mt-4">
        <template #header>
          <h4><i class="fas fa-chart-line"></i> Agent Performance</h4>
        </template>
        <table class="data-table" v-if="agentMetrics?.agents?.length">
          <thead>
            <tr>
              <th>Agent ID</th>
              <th>Type</th>
              <th class="text-right">Tasks</th>
              <th class="text-right">Success Rate</th>
              <th class="text-right">Error Rate</th>
              <th class="text-right">Avg Duration</th>
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
        <EmptyState v-else icon="fas fa-robot" message="No agent data available" />
      </BasePanel>

      <!-- Recommendations -->
      <BasePanel variant="bordered" class="mt-4" v-if="recommendations?.recommendations?.length">
        <template #header>
          <h4><i class="fas fa-lightbulb"></i> Recommendations</h4>
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
                <i :class="getSeverityIcon(r.severity)"></i>
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
        <BasePanel variant="bordered" size="small">
          <template #header>
            <h4><i class="fas fa-users"></i> Total Sessions</h4>
          </template>
          <div class="metric-value large">
            {{ formatNumber(engagementMetrics?.metrics?.total_sessions || 0) }}
          </div>
        </BasePanel>

        <!-- Page Views -->
        <BasePanel variant="bordered" size="small">
          <template #header>
            <h4><i class="fas fa-eye"></i> Page Views</h4>
          </template>
          <div class="metric-value">
            {{ formatNumber(engagementMetrics?.metrics?.total_page_views || 0) }}
          </div>
        </BasePanel>

        <!-- Avg Session Duration -->
        <BasePanel variant="bordered" size="small">
          <template #header>
            <h4><i class="fas fa-clock"></i> Avg Session Duration</h4>
          </template>
          <div class="metric-value">
            {{ formatDuration(engagementMetrics?.metrics?.avg_session_duration_ms || 0) }}
          </div>
        </BasePanel>

        <!-- Pages Per Session -->
        <BasePanel variant="bordered" size="small">
          <template #header>
            <h4><i class="fas fa-file-alt"></i> Pages/Session</h4>
          </template>
          <div class="metric-value">
            {{ engagementMetrics?.metrics?.pages_per_session?.toFixed(1) || '0.0' }}
          </div>
        </BasePanel>
      </div>

      <!-- Feature Popularity -->
      <BasePanel variant="elevated" class="mt-4">
        <template #header>
          <h4><i class="fas fa-star"></i> Feature Popularity</h4>
        </template>
        <table class="data-table" v-if="engagementMetrics?.feature_popularity?.length">
          <thead>
            <tr>
              <th>Feature</th>
              <th class="text-right">Views</th>
              <th class="text-right">Popularity</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(feature, idx) in engagementMetrics.feature_popularity" :key="feature.feature">
              <td>
                <span class="rank-badge" :class="'rank-' + (idx + 1)">{{ idx + 1 }}</span>
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
        <EmptyState v-else icon="fas fa-chart-bar" message="No feature data available" />
      </BasePanel>

      <!-- Usage Heatmap -->
      <BasePanel variant="bordered" class="mt-4" v-if="usageHeatmap?.peak_hours?.length">
        <template #header>
          <h4><i class="fas fa-fire"></i> Peak Usage Hours</h4>
        </template>
        <div class="peak-hours-list">
          <div
            v-for="(peak, idx) in usageHeatmap.peak_hours"
            :key="peak.hour"
            class="peak-hour-item"
          >
            <span class="peak-rank">{{ idx + 1 }}</span>
            <span class="peak-time">{{ peak.hour }}:00</span>
            <span class="peak-events">{{ formatNumber(peak.total_events) }} events</span>
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
            <h4><i :class="format.icon"></i> {{ format.format }}</h4>
          </template>
          <p>{{ format.description }}</p>
          <div class="export-actions">
            <BaseButton
              v-for="endpoint in format.endpoints"
              :key="endpoint.path"
              variant="outline"
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
      <i class="fas fa-spinner fa-spin fa-2x"></i>
      <span>Loading analytics...</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import BasePanel from '@/components/base/BasePanel.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import api from '@/services/api'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('AdvancedAnalytics')

// Issue #701: Type for API response with data property
interface ApiDataResponse {
  data?: any
  [key: string]: any
}

// State
const loading = ref(false)
const activeTab = ref('cost')
const showExportModal = ref(false)

// Data
const costSummary = ref<any>(null)
const costTrends = ref<any>(null)
const modelCosts = ref<any[]>([])
const agentMetrics = ref<any>(null)
const recommendations = ref<any>(null)
const exportFormats = ref<any[]>([])
const behaviorMetrics = ref<any>(null)
const engagementMetrics = ref<any>(null)
const usageHeatmap = ref<any>(null)

// Tabs configuration
const tabs = [
  { id: 'cost', label: 'Cost Analytics', icon: 'fas fa-dollar-sign' },
  { id: 'agents', label: 'Agent Performance', icon: 'fas fa-robot' },
  { id: 'behavior', label: 'User Behavior', icon: 'fas fa-users' },
  { id: 'export', label: 'Export Data', icon: 'fas fa-download' }
]

// Computed
const costTrend = computed(() => {
  const trend = costTrends.value?.trend
  if (trend === 'increasing') return 'trend-up'
  if (trend === 'decreasing') return 'trend-down'
  return 'trend-stable'
})

const trendIcon = computed(() => {
  const trend = costTrends.value?.trend
  if (trend === 'increasing') return 'fas fa-arrow-up'
  if (trend === 'decreasing') return 'fas fa-arrow-down'
  return 'fas fa-minus'
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

const getSeverityIcon = (severity: string): string => {
  if (severity === 'high') return 'fas fa-exclamation-circle'
  if (severity === 'medium') return 'fas fa-exclamation-triangle'
  return 'fas fa-info-circle'
}

const fetchCostData = async () => {
  try {
    // Issue #552: Fixed missing /api prefix in analytics endpoints
    // Issue #701: Added type assertions for Promise.all results
    const [summaryRes, trendsRes, modelsRes] = await Promise.all([
      api.get<ApiDataResponse>('/api/analytics/cost/summary'),
      api.get<ApiDataResponse>('/api/analytics/cost/trends'),
      api.get<ApiDataResponse>('/api/analytics/cost/by-model')
    ])
    costSummary.value = (summaryRes as ApiDataResponse).data
    costTrends.value = (trendsRes as ApiDataResponse).data
    modelCosts.value = (modelsRes as ApiDataResponse).data?.models || []
  } catch (error) {
    logger.error('Failed to fetch cost data:', error)
  }
}

const fetchAgentData = async () => {
  try {
    // Issue #552: Fixed missing /api prefix in analytics endpoints
    // Issue #701: Added type assertions for Promise.all results
    const [metricsRes, recsRes] = await Promise.all([
      api.get<ApiDataResponse>('/api/analytics/agents/performance'),
      api.get<ApiDataResponse>('/api/analytics/agents/recommendations')
    ])
    agentMetrics.value = (metricsRes as ApiDataResponse).data
    recommendations.value = (recsRes as ApiDataResponse).data
  } catch (error) {
    logger.error('Failed to fetch agent data:', error)
  }
}

const fetchExportFormats = async () => {
  try {
    // Issue #552: Fixed missing /api prefix in analytics endpoints
    // Issue #701: Added type assertion for response
    const res = await api.get<ApiDataResponse>('/api/analytics/export/formats')
    exportFormats.value = (res as ApiDataResponse).data?.formats || []
    // Add icons
    exportFormats.value.forEach((f: any) => {
      if (f.format === 'CSV') f.icon = 'fas fa-file-csv'
      else if (f.format === 'JSON') f.icon = 'fas fa-file-code'
      else if (f.format === 'Prometheus') f.icon = 'fas fa-chart-area'
      else if (f.format === 'Grafana') f.icon = 'fas fa-tachometer-alt'
      else f.icon = 'fas fa-file'
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
      api.get<ApiDataResponse>('/api/analytics/behavior/engagement'),
      api.get<ApiDataResponse>('/api/analytics/behavior/features'),
      api.get<ApiDataResponse>('/api/analytics/behavior/stats/heatmap')
    ])
    engagementMetrics.value = (engagementRes as ApiDataResponse).data
    behaviorMetrics.value = (featuresRes as ApiDataResponse).data
    usageHeatmap.value = (heatmapRes as ApiDataResponse).data
  } catch (error) {
    logger.error('Failed to fetch behavior data:', error)
  }
}

const getPopularityWidth = (views: number): string => {
  if (!engagementMetrics.value?.feature_popularity?.length) return '0%'
  const maxViews = Math.max(...engagementMetrics.value.feature_popularity.map((f: any) => f.views || 0))
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
  padding: 1.5rem;
  position: relative;
}

.analytics-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
}

.analytics-header h2 {
  margin: 0;
  color: var(--text-primary);
}

.header-actions {
  display: flex;
  gap: 0.5rem;
}

.analytics-tabs {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1.5rem;
  border-bottom: 1px solid var(--border-color);
  padding-bottom: 0.5rem;
}

.tab-btn {
  padding: 0.5rem 1rem;
  border: none;
  background: none;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: 4px;
  transition: all 0.2s;
}

.tab-btn:hover {
  background: var(--bg-tertiary);
}

.tab-btn.active {
  background: var(--primary-color);
  color: white;
}

.tab-btn i {
  margin-right: 0.5rem;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
}

.metric-value {
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--text-primary);
}

.metric-value.large {
  font-size: 2rem;
}

.metric-value.success {
  color: var(--success-color);
}

.metric-trend {
  margin-top: 0.5rem;
  font-size: 0.875rem;
}

.trend-up {
  color: var(--danger-color);
}

.trend-down {
  color: var(--success-color);
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
  padding: 0.75rem;
  text-align: left;
  border-bottom: 1px solid var(--border-color);
}

.data-table th {
  font-weight: 600;
  color: var(--text-secondary);
  font-size: 0.875rem;
}

.text-right {
  text-align: right;
}

.badge {
  display: inline-block;
  padding: 0.25rem 0.5rem;
  background: var(--bg-tertiary);
  border-radius: 4px;
  font-size: 0.75rem;
}

.success {
  color: var(--success-color);
}

.warning {
  color: var(--warning-color);
}

.error {
  color: var(--danger-color);
}

.mt-4 {
  margin-top: 1rem;
}

.recommendations-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.recommendation-item ul {
  margin: 0.5rem 0 0 1.5rem;
  padding: 0;
}

.recommendation-item li {
  margin: 0.25rem 0;
}

.severity-high {
  color: var(--danger-color);
}

.severity-medium {
  color: var(--warning-color);
}

.severity-low {
  color: var(--text-secondary);
}

.export-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 1rem;
}

.export-card p {
  color: var(--text-secondary);
  margin: 0.5rem 0 1rem;
}

.export-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
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
  font-size: 0.75rem;
  font-weight: 600;
  margin-right: 0.5rem;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.rank-1 {
  background: linear-gradient(135deg, var(--color-rank-gold, #ffd700), var(--color-rank-gold-dark, #ffb700));
  color: var(--text-dark, #1a1a1a);
}

.rank-2 {
  background: linear-gradient(135deg, var(--color-rank-silver, #c0c0c0), var(--color-rank-silver-dark, #a0a0a0));
  color: var(--text-dark, #1a1a1a);
}

.rank-3 {
  background: linear-gradient(135deg, var(--color-rank-bronze, #cd7f32), var(--color-rank-bronze-dark, #b87333));
  color: var(--text-on-primary);
}

.popularity-bar {
  width: 100px;
  height: 8px;
  background: var(--bg-tertiary);
  border-radius: 4px;
  overflow: hidden;
}

.popularity-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--primary-color), var(--success-color));
  border-radius: 4px;
  transition: width 0.3s ease;
}

.peak-hours-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.peak-hour-item {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem;
  background: var(--bg-secondary);
  border-radius: 6px;
}

.peak-rank {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.5rem;
  height: 1.5rem;
  background: var(--primary-color);
  color: white;
  border-radius: 50%;
  font-size: 0.75rem;
  font-weight: 600;
}

.peak-time {
  font-weight: 600;
  color: var(--text-primary);
  min-width: 60px;
}

.peak-events {
  color: var(--text-secondary);
  font-size: 0.875rem;
}
</style>
