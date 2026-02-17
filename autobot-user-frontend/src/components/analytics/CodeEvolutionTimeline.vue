<template>
  <div class="code-evolution-timeline">
    <!-- Header with controls -->
    <div class="timeline-header">
      <h2><i class="fas fa-chart-line"></i> Code Evolution Timeline</h2>
      <div class="timeline-controls">
        <select v-model="selectedGranularity" class="control-select">
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
          <option value="monthly">Monthly</option>
        </select>
        <select v-model="selectedDays" class="control-select">
          <option value="7">Last 7 days</option>
          <option value="30">Last 30 days</option>
          <option value="90">Last 90 days</option>
          <option value="365">Last year</option>
        </select>
        <BaseButton variant="secondary" size="sm" @click="fetchTimeline" :loading="loading">
          <i class="fas fa-sync"></i> Refresh
        </BaseButton>
        <BaseButton variant="primary" size="sm" @click="exportData">
          <i class="fas fa-download"></i> Export
        </BaseButton>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="loading-state">
      <i class="fas fa-spinner fa-spin"></i>
      <span>Loading evolution data...</span>
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="error-state">
      <i class="fas fa-exclamation-triangle"></i>
      <span>{{ error }}</span>
      <BaseButton variant="secondary" size="sm" @click="fetchTimeline">Retry</BaseButton>
    </div>

    <!-- Main Content -->
    <div v-else class="timeline-content">
      <!-- Trend Summary Cards -->
      <div class="trends-grid">
        <div
          v-for="(trend, metric) in trends"
          :key="metric"
          class="trend-card"
          :class="getTrendClass(trend.direction)"
        >
          <div class="trend-header">
            <span class="metric-name">{{ formatMetricName(metric) }}</span>
            <i :class="getTrendIcon(trend.direction)"></i>
          </div>
          <div class="trend-value">{{ trend.last_value?.toFixed(1) || 0 }}</div>
          <div class="trend-change">
            <span :class="trend.direction">
              {{ trend.change >= 0 ? '+' : '' }}{{ trend.change?.toFixed(1) || 0 }}
            </span>
            <span class="percent">({{ trend.percent_change?.toFixed(1) || 0 }}%)</span>
          </div>
        </div>
      </div>

      <!-- Timeline Chart -->
      <div class="chart-container">
        <div class="chart-header">
          <h3>Quality Score Over Time</h3>
          <div class="metric-toggles">
            <label
              v-for="metric in availableMetrics"
              :key="metric"
              class="metric-toggle"
              :class="{ active: selectedMetrics.includes(metric) }"
            >
              <input
                type="checkbox"
                :value="metric"
                v-model="selectedMetrics"
              >
              <span :style="{ color: getMetricColor(metric) }">
                {{ formatMetricName(metric) }}
              </span>
            </label>
          </div>
        </div>

        <!-- SVG Chart -->
        <div class="chart-wrapper" ref="chartWrapper">
          <svg
            class="timeline-chart"
            :viewBox="`0 0 ${chartWidth} ${chartHeight}`"
            preserveAspectRatio="xMidYMid meet"
          >
            <!-- Grid lines -->
            <g class="grid-lines">
              <line
                v-for="i in 5"
                :key="'h-' + i"
                :x1="chartPadding.left"
                :y1="chartPadding.top + (i - 1) * (chartInnerHeight / 4)"
                :x2="chartWidth - chartPadding.right"
                :y2="chartPadding.top + (i - 1) * (chartInnerHeight / 4)"
                class="grid-line"
              />
            </g>

            <!-- Y-axis labels -->
            <g class="y-axis">
              <text
                v-for="i in 5"
                :key="'y-' + i"
                :x="chartPadding.left - 10"
                :y="chartPadding.top + (i - 1) * (chartInnerHeight / 4) + 4"
                class="axis-label"
              >
                {{ 100 - (i - 1) * 25 }}
              </text>
            </g>

            <!-- Data lines for each metric -->
            <g
              v-for="metric in selectedMetrics"
              :key="metric"
              class="data-line-group"
            >
              <path
                :d="getLinePath(metric)"
                :stroke="getMetricColor(metric)"
                fill="none"
                stroke-width="2"
                class="data-line"
              />
              <!-- Data points -->
              <circle
                v-for="(point, idx) in timelineData"
                :key="metric + '-' + idx"
                :cx="getX(idx)"
                :cy="getY((point as any)[metric])"
                r="4"
                :fill="getMetricColor(metric)"
                class="data-point"
                @mouseenter="showTooltip($event, point, metric)"
                @mouseleave="hideTooltip"
              />
            </g>

            <!-- X-axis labels -->
            <g class="x-axis">
              <text
                v-for="(point, idx) in xAxisLabels"
                :key="'x-' + idx"
                :x="getX(point.index)"
                :y="chartHeight - 10"
                class="axis-label x-label"
              >
                {{ point.label }}
              </text>
            </g>
          </svg>
        </div>
      </div>

      <!-- Pattern Evolution Section -->
      <div class="patterns-section" v-if="patterns && Object.keys(patterns).length">
        <h3><i class="fas fa-bug"></i> Anti-Pattern Evolution</h3>
        <div class="patterns-grid">
          <div
            v-for="(data, patternType) in patterns"
            :key="patternType"
            class="pattern-card"
          >
            <div class="pattern-header">
              <span class="pattern-name">{{ formatPatternName(patternType) }}</span>
              <span class="pattern-count" :class="getPatternTrend(data)">
                {{ getLatestCount(data) }}
              </span>
            </div>
            <div class="pattern-sparkline">
              <div
                v-for="(point, idx) in data.slice(-10)"
                :key="idx"
                class="sparkline-bar"
                :style="{ height: getSparklineHeight(point.count, data) + '%' }"
              ></div>
            </div>
            <div class="pattern-trend">
              <i :class="getPatternTrendIcon(data)"></i>
              {{ getPatternTrendText(data) }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Tooltip -->
    <div
      v-if="tooltip.visible"
      class="chart-tooltip"
      :style="{ left: tooltip.x + 'px', top: tooltip.y + 'px' }"
    >
      <div class="tooltip-date">{{ tooltip.date }}</div>
      <div class="tooltip-metric">
        <span class="metric-name">{{ formatMetricName(tooltip.metric) }}:</span>
        <span class="metric-value">{{ tooltip.value?.toFixed(1) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
// @ts-ignore - Component may not have type declarations
import BaseButton from '@/components/ui/BaseButton.vue'
import { useToast } from '@/composables/useToast'

interface TimelinePoint {
  timestamp: string
  overall_score?: number
  maintainability?: number
  testability?: number
  documentation?: number
  complexity?: number
  security?: number
  performance?: number
  total_files?: number
  total_lines?: number
}

interface TrendData {
  first_value: number
  last_value: number
  change: number
  percent_change: number
  direction: 'improving' | 'declining' | 'stable'
  data_points: number
}

interface PatternPoint {
  timestamp: string
  count: number
  pattern_type: string
}

const { showToast } = useToast()

// State
const loading = ref(false)
const error = ref<string | null>(null)
const timelineData = ref<TimelinePoint[]>([])
const trends = ref<Record<string, TrendData>>({})
const patterns = ref<Record<string, PatternPoint[]>>({})

// Controls
const selectedGranularity = ref('daily')
const selectedDays = ref('30')
const selectedMetrics = ref(['overall_score', 'maintainability', 'complexity'])

// Chart dimensions
const chartWrapper = ref<HTMLElement | null>(null)
const chartWidth = 800
const chartHeight = 300
const chartPadding = { top: 20, right: 30, bottom: 40, left: 50 }
const chartInnerWidth = computed(() => chartWidth - chartPadding.left - chartPadding.right)
const chartInnerHeight = computed(() => chartHeight - chartPadding.top - chartPadding.bottom)

// Tooltip
const tooltip = ref({
  visible: false,
  x: 0,
  y: 0,
  date: '',
  metric: '',
  value: 0
})

// Available metrics
const availableMetrics = [
  'overall_score',
  'maintainability',
  'testability',
  'documentation',
  'complexity',
  'security',
  'performance'
]

// Metric colors - Using CSS custom properties with fallbacks
const metricColors: Record<string, string> = {
  overall_score: 'var(--color-success, #10b981)',
  maintainability: 'var(--color-primary, #3b82f6)',
  testability: 'var(--chart-purple, #8b5cf6)',
  documentation: 'var(--color-warning, #f59e0b)',
  complexity: 'var(--color-error, #ef4444)',
  security: 'var(--chart-cyan, #06b6d4)',
  performance: 'var(--chart-pink, #ec4899)'
}

// X-axis labels (show every nth label based on data size)
const xAxisLabels = computed(() => {
  const data = timelineData.value
  if (!data.length) return []

  const step = Math.max(1, Math.floor(data.length / 6))
  return data
    .filter((_, idx) => idx % step === 0)
    .map((point, i) => ({
      index: i * step,
      label: formatDate(point.timestamp)
    }))
})

// API calls
async function fetchTimeline() {
  loading.value = true
  error.value = null

  try {
    const endDate = new Date().toISOString().split('T')[0]
    const startDate = new Date(Date.now() - parseInt(selectedDays.value) * 24 * 60 * 60 * 1000)
      .toISOString().split('T')[0]

    const params = new URLSearchParams({
      start_date: startDate,
      end_date: endDate,
      granularity: selectedGranularity.value,
      metrics: selectedMetrics.value.join(',')
    })

    // Issue #552: Fixed path - backend uses /api/evolution/* not /api/analytics/evolution/*
    const [timelineRes, trendsRes, patternsRes] = await Promise.all([
      fetch(`/api/evolution/timeline?${params}`),
      fetch(`/api/evolution/trends?days=${selectedDays.value}`),
      fetch('/api/evolution/patterns')
    ])

    if (!timelineRes.ok || !trendsRes.ok) {
      throw new Error('Failed to fetch evolution data')
    }

    const timelineJson = await timelineRes.json()
    const trendsJson = await trendsRes.json()
    const patternsJson = await patternsRes.json()

    timelineData.value = timelineJson.timeline || []
    trends.value = trendsJson.trends || {}
    patterns.value = patternsJson.patterns || {}

    if (timelineJson.status === 'demo') {
      showToast('Using demo data - Redis unavailable', 'warning')
    }

  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Failed to load evolution data'
  } finally {
    loading.value = false
  }
}

async function exportData() {
  try {
    const startDate = new Date(Date.now() - parseInt(selectedDays.value) * 24 * 60 * 60 * 1000)
      .toISOString().split('T')[0]
    const endDate = new Date().toISOString().split('T')[0]

    // Issue #552: Fixed path - backend uses /api/evolution/* not /api/analytics/evolution/*
    const response = await fetch(
      `/api/evolution/export?format=csv&start_date=${startDate}&end_date=${endDate}`
    )

    if (!response.ok) throw new Error('Export failed')

    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `code_evolution_${endDate}.csv`
    a.click()
    URL.revokeObjectURL(url)

    showToast('Data exported successfully', 'success')
  } catch (e) {
    showToast('Export failed', 'error')
  }
}

// Chart helpers
function getX(index: number): number {
  const data = timelineData.value
  if (!data.length) return chartPadding.left
  return chartPadding.left + (index / (data.length - 1 || 1)) * chartInnerWidth.value
}

function getY(value: number | undefined): number {
  const v = value ?? 0
  return chartPadding.top + (1 - v / 100) * chartInnerHeight.value
}

function getLinePath(metric: string): string {
  const data = timelineData.value
  if (!data.length) return ''

  return data
    .map((point, idx) => {
      const x = getX(idx)
      const y = getY(point[metric as keyof TimelinePoint] as number)
      return `${idx === 0 ? 'M' : 'L'} ${x} ${y}`
    })
    .join(' ')
}

function getMetricColor(metric: string): string {
  return metricColors[metric] || 'var(--text-tertiary, #6b7280)'
}

// Tooltip
function showTooltip(event: MouseEvent, point: TimelinePoint, metric: string) {
  const rect = (event.target as HTMLElement).getBoundingClientRect()
  tooltip.value = {
    visible: true,
    x: rect.left + 10,
    y: rect.top - 50,
    date: formatDate(point.timestamp),
    metric,
    value: point[metric as keyof TimelinePoint] as number
  }
}

function hideTooltip() {
  tooltip.value.visible = false
}

// Formatting helpers
function formatMetricName(metric: string): string {
  return metric
    .split('_')
    .map(w => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

function formatPatternName(pattern: string): string {
  return pattern
    .split('_')
    .map(w => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

function formatDate(timestamp: string): string {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

// Trend helpers
function getTrendClass(direction: string): string {
  switch (direction) {
    case 'improving': return 'trend-positive'
    case 'declining': return 'trend-negative'
    default: return 'trend-stable'
  }
}

function getTrendIcon(direction: string): string {
  switch (direction) {
    case 'improving': return 'fas fa-arrow-up trend-up'
    case 'declining': return 'fas fa-arrow-down trend-down'
    default: return 'fas fa-minus trend-stable'
  }
}

// Pattern helpers
function getLatestCount(data: PatternPoint[]): number {
  return data[data.length - 1]?.count ?? 0
}

function getPatternTrend(data: PatternPoint[]): string {
  if (data.length < 2) return ''
  const first = data[0].count
  const last = data[data.length - 1].count
  if (last < first) return 'declining'
  if (last > first) return 'increasing'
  return ''
}

function getPatternTrendIcon(data: PatternPoint[]): string {
  const trend = getPatternTrend(data)
  if (trend === 'declining') return 'fas fa-arrow-down text-green-500'
  if (trend === 'increasing') return 'fas fa-arrow-up text-red-500'
  return 'fas fa-minus text-autobot-text-muted'
}

function getPatternTrendText(data: PatternPoint[]): string {
  if (data.length < 2) return 'No trend data'
  const first = data[0].count
  const last = data[data.length - 1].count
  const change = last - first
  if (change === 0) return 'Stable'
  return `${change > 0 ? '+' : ''}${change} since start`
}

function getSparklineHeight(count: number, data: PatternPoint[]): number {
  const max = Math.max(...data.map(p => p.count), 1)
  return (count / max) * 100
}

// Lifecycle
onMounted(() => {
  fetchTimeline()
})

// Watch for control changes
watch([selectedGranularity, selectedDays], () => {
  fetchTimeline()
})
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.code-evolution-timeline {
  padding: 1.5rem;
  background: var(--bg-secondary);
  border-radius: 8px;
}

.timeline-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
}

.timeline-header h2 {
  font-size: 1.5rem;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.timeline-controls {
  display: flex;
  gap: 0.75rem;
  align-items: center;
}

.control-select {
  padding: 0.5rem 0.75rem;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.875rem;
}

.loading-state,
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem;
  gap: 1rem;
  color: var(--text-secondary);
}

.trends-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.trend-card {
  background: var(--bg-tertiary);
  border-radius: 8px;
  padding: 1rem;
  border: 1px solid var(--border-default);
}

.trend-card.trend-positive {
  border-color: var(--color-success);
}

.trend-card.trend-negative {
  border-color: var(--color-error);
}

.trend-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.metric-name {
  font-size: 0.75rem;
  color: var(--text-secondary);
  text-transform: uppercase;
}

.trend-value {
  font-size: 1.75rem;
  font-weight: 600;
  color: var(--text-primary);
}

.trend-change {
  font-size: 0.875rem;
  margin-top: 0.25rem;
}

.trend-change .improving {
  color: var(--color-success);
}

.trend-change .declining {
  color: var(--color-error);
}

.trend-change .percent {
  color: var(--text-secondary);
  margin-left: 0.25rem;
}

.trend-up {
  color: var(--color-success);
}

.trend-down {
  color: var(--color-error);
}

.chart-container {
  background: var(--bg-tertiary);
  border-radius: 8px;
  padding: 1.5rem;
  margin-bottom: 1.5rem;
}

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.chart-header h3 {
  font-size: 1.125rem;
  color: var(--text-primary);
}

.metric-toggles {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
}

.metric-toggle {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.75rem;
  cursor: pointer;
  opacity: 0.6;
  transition: opacity 0.2s;
}

.metric-toggle.active {
  opacity: 1;
}

.metric-toggle input {
  display: none;
}

.chart-wrapper {
  width: 100%;
  overflow-x: auto;
}

.timeline-chart {
  width: 100%;
  min-width: 600px;
  height: auto;
}

.grid-line {
  stroke: var(--border-default);
  stroke-dasharray: 4 4;
}

.axis-label {
  fill: var(--text-secondary);
  font-size: 10px;
  text-anchor: end;
}

.x-label {
  text-anchor: middle;
}

.data-line {
  transition: stroke-width 0.2s;
}

.data-line:hover {
  stroke-width: 3;
}

.data-point {
  cursor: pointer;
  transition: r 0.2s;
}

.data-point:hover {
  r: 6;
}

.chart-tooltip {
  position: fixed;
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  padding: 0.75rem;
  z-index: 1000;
  pointer-events: none;
}

.tooltip-date {
  font-size: 0.75rem;
  color: var(--text-secondary);
  margin-bottom: 0.25rem;
}

.tooltip-metric {
  display: flex;
  gap: 0.5rem;
}

.tooltip-metric .metric-value {
  font-weight: 600;
  color: var(--text-primary);
}

.patterns-section h3 {
  font-size: 1.125rem;
  color: var(--text-primary);
  margin-bottom: 1rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.patterns-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
}

.pattern-card {
  background: var(--bg-tertiary);
  border-radius: 8px;
  padding: 1rem;
  border: 1px solid var(--border-default);
}

.pattern-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.75rem;
}

.pattern-name {
  font-size: 0.875rem;
  color: var(--text-primary);
}

.pattern-count {
  font-size: 1.25rem;
  font-weight: 600;
}

.pattern-count.declining {
  color: var(--color-success);
}

.pattern-count.increasing {
  color: var(--color-error);
}

.pattern-sparkline {
  display: flex;
  align-items: flex-end;
  height: 40px;
  gap: 2px;
  margin-bottom: 0.5rem;
}

.sparkline-bar {
  flex: 1;
  background: linear-gradient(to top, var(--color-primary), var(--chart-purple));
  border-radius: 2px 2px 0 0;
  min-height: 2px;
}

.pattern-trend {
  font-size: 0.75rem;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 0.25rem;
}
</style>
