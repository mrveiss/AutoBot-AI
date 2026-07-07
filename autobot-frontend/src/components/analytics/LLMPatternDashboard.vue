<template>
  <div class="llm-pattern-dashboard">
    <!-- Header -->
    <div class="dashboard-header">
      <h2>{{ $t('analytics.llmPatterns.title') }}</h2>
      <p class="subtitle">{{ $t('analytics.llmPatterns.subtitle') }}</p>
    </div>

    <!-- Summary Cards -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-icon requests">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
          </svg>
        </div>
        <div class="stat-content">
          <span class="stat-value">{{ stats.total_requests }}</span>
          <span class="stat-label">{{ $t('analytics.llmPatterns.totalRequests') }}</span>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon cost">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 1v22M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/>
          </svg>
        </div>
        <div class="stat-content">
          <span class="stat-value">${{ formatCost(stats.total_cost) }}</span>
          <span class="stat-label">{{ $t('analytics.llmPatterns.totalCost7d') }}</span>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon avg">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M16 8v8m-4-6v6m-4-4v4m-2 4h16a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/>
          </svg>
        </div>
        <div class="stat-content">
          <span class="stat-value">${{ formatCost(stats.avg_cost_per_request) }}</span>
          <span class="stat-label">{{ $t('analytics.llmPatterns.avgCostPerRequest') }}</span>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon savings">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M13 17h8m0 0V9m0 8l-8-8-4 4-6-6"/>
          </svg>
        </div>
        <div class="stat-content">
          <span class="stat-value">${{ formatCost(potentialSavings) }}</span>
          <span class="stat-label">{{ $t('analytics.llmPatterns.potentialSavings') }}</span>
        </div>
      </div>
    </div>

    <!-- Main Content Grid -->
    <div class="content-grid">
      <!-- Left Column -->
      <div class="left-column">
        <!-- Prompt Analyzer -->
        <div class="panel">
          <div class="panel-header">
            <h3>{{ $t('analytics.llmPatterns.promptAnalyzer') }}</h3>
          </div>
          <div class="panel-content">
            <div class="form-group">
              <textarea
                v-model="analyzePrompt"
                :placeholder="$t('analytics.llmPatterns.promptPlaceholder')"
                rows="3"
              ></textarea>
            </div>
            <div class="form-row">
              <select v-model="analyzeModel">
                <option value="">{{ $t('analytics.llmPatterns.selectModel') }}</option>
                <option value="claude-3-opus">Claude 3 Opus</option>
                <option value="claude-3-sonnet">Claude 3 Sonnet</option>
                <option value="claude-3-haiku">Claude 3 Haiku</option>
                <option value="gpt-4o">GPT-4o</option>
                <option value="gpt-4o-mini">GPT-4o Mini</option>
                <option value="gpt-3.5-turbo">GPT-3.5 Turbo</option>
              </select>
              <button class="analyze-btn" :disabled="!analyzePrompt" @click="runAnalysis">
                {{ $t('analytics.llmPatterns.analyze') }}
              </button>
            </div>

            <!-- Analysis Result -->
            <div v-if="analysisResult" class="analysis-result">
              <div class="result-header">
                <span class="category-badge" :class="analysisResult.category">
                  {{ analysisResult.category }}
                </span>
                <span class="tokens-badge">~{{ analysisResult.estimated_tokens }} tokens</span>
                <span class="cost-badge">${{ formatCost(analysisResult.estimated_cost) }}</span>
              </div>

              <div v-if="analysisResult.issues?.length" class="issues-list">
                <div v-for="(issue, idx) in analysisResult.issues" :key="idx" class="issue-item" :class="issue.severity">
                  {{ issue.message }}
                </div>
              </div>

              <div v-if="analysisResult.recommendations?.length" class="recommendations-list">
                <div v-for="(rec, idx) in analysisResult.recommendations" :key="idx" class="recommendation-item">
                  {{ rec }}
                </div>
              </div>

              <div v-if="analysisResult.cache_potential" class="cache-indicator">
                {{ $t('analytics.llmPatterns.cachePotential') }}
              </div>
            </div>
          </div>
        </div>

        <!-- Optimization Recommendations -->
        <div class="panel">
          <div class="panel-header">
            <h3>{{ $t('analytics.llmPatterns.optimizationRecommendations') }}</h3>
            <button class="refresh-btn" @click="fetchRecommendations" :aria-label="$t('common.refresh')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
              </svg>
            </button>
          </div>
          <div class="panel-content">
            <div v-if="recommendations.length === 0" class="empty-state">
              <p>{{ $t('analytics.llmPatterns.noRecommendations') }}</p>
            </div>
            <div v-else class="recommendations-grid">
              <div
                v-for="rec in recommendations"
                :key="rec.type"
                class="recommendation-card"
                :class="'priority-' + rec.priority"
              >
                <div class="rec-header">
                  <span class="rec-type">{{ rec.type.replace(/_/g, ' ') }}</span>
                  <span class="rec-savings">${{ formatCost(rec.potential_savings) }}</span>
                </div>
                <h4>{{ rec.title }}</h4>
                <p>{{ rec.description }}</p>
                <div class="rec-meta">
                  <span>{{ $t('analytics.llmPatterns.promptsAffected', { count: rec.affected_prompts }) }}</span>
                </div>
                <button class="expand-btn" @click="toggleSteps(rec.type)">
                  {{ isRecExpanded(rec.type) ? $t('analytics.llmPatterns.hideSteps') : $t('analytics.llmPatterns.showSteps') }}
                </button>
                <div v-if="isRecExpanded(rec.type)" class="rec-steps">
                  <ol>
                    <li v-for="(step, idx) in rec.implementation_steps" :key="idx">
                      {{ step }}
                    </li>
                  </ol>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Right Column -->
      <div class="right-column">
        <!-- Model Comparison -->
        <div class="panel">
          <div class="panel-header">
            <h3>{{ $t('analytics.llmPatterns.modelComparison') }}</h3>
          </div>
          <div class="panel-content">
            <div v-if="modelComparison.length === 0" class="empty-state">
              <p>{{ $t('analytics.llmPatterns.noModelData') }}</p>
            </div>
            <div v-else class="model-list">
              <div
                v-for="model in modelComparison"
                :key="model.model"
                class="model-item"
              >
                <div class="model-header">
                  <span class="model-name">{{ model.model }}</span>
                  <span class="model-cost">${{ formatCost(model.total_cost) }}</span>
                </div>
                <div class="model-stats">
                  <span>{{ $t('analytics.llmPatterns.requests', { count: model.request_count }) }}</span>
                  <span>{{ $t('analytics.llmPatterns.tokens', { count: formatTokens(model.total_tokens) }) }}</span>
                  <span>{{ $t('analytics.llmPatterns.successRate', { rate: model.success_rate }) }}</span>
                </div>
                <div class="model-bar">
                  <div
                    class="model-bar-fill"
                    :style="{ width: getModelBarWidth(model) + '%' }"
                  ></div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Category Distribution -->
        <div class="panel">
          <div class="panel-header">
            <h3>{{ $t('analytics.llmPatterns.usageByCategory') }}</h3>
          </div>
          <div class="panel-content">
            <div v-if="categoryData.categories?.length === 0" class="empty-state">
              <p>{{ $t('analytics.llmPatterns.noCategoryData') }}</p>
            </div>
            <div v-else class="category-list">
              <div
                v-for="cat in categoryData.categories"
                :key="cat.category"
                class="category-item"
              >
                <div class="category-header">
                  <span class="category-name">{{ formatCategory(cat.category) }}</span>
                  <span class="category-count">{{ cat.count }}</span>
                </div>
                <div class="category-bar">
                  <div
                    class="category-bar-fill"
                    :style="{ width: cat.percentage + '%' }"
                  ></div>
                </div>
                <div class="category-meta">
                  <span>{{ cat.percentage }}%</span>
                  <span>${{ formatCost(cat.cost) }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Cache Opportunities -->
        <div class="panel">
          <div class="panel-header">
            <h3>{{ $t('analytics.llmPatterns.cachingOpportunities') }}</h3>
          </div>
          <div class="panel-content">
            <div v-if="cacheOpportunities.length === 0" class="empty-state">
              <p>{{ $t('analytics.llmPatterns.noCachingOpportunities') }}</p>
            </div>
            <div v-else class="cache-list">
              <div
                v-for="opp in cacheOpportunities.slice(0, 5)"
                :key="opp.prompt_hash"
                class="cache-item"
              >
                <div class="cache-header">
                  <span class="cache-count">{{ opp.occurrence_count }}x</span>
                  <span class="cache-savings">${{ formatCost(opp.potential_savings) }} {{ $t('analytics.llmPatterns.savings') }}</span>
                </div>
                <p class="cache-preview">{{ opp.prompt_preview }}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Cost Trend Chart -->
    <div class="panel trend-panel">
      <div class="panel-header">
        <h3>{{ $t('analytics.llmPatterns.dailyCostTrend') }}</h3>
      </div>
      <div class="panel-content">
        <div v-if="stats.by_date?.length === 0" class="empty-state">
          <p>{{ $t('analytics.llmPatterns.noTrendData') }}</p>
        </div>
        <div v-else class="trend-chart">
          <svg :viewBox="`0 0 ${chartWidth} ${chartHeight}`" class="chart-svg">
            <!-- Grid lines -->
            <line
              v-for="i in 5"
              :key="'grid-' + i"
              :x1="chartPadding"
              :x2="chartWidth - chartPadding"
              :y1="chartPadding + (i - 1) * ((chartHeight - 2 * chartPadding) / 4)"
              :y2="chartPadding + (i - 1) * ((chartHeight - 2 * chartPadding) / 4)"
              class="grid-line"
            />

            <!-- Cost line -->
            <path :d="costLinePath" class="cost-line" fill="none" />

            <!-- Data points -->
            <circle
              v-for="(point, idx) in chartPoints"
              :key="'point-' + idx"
              :cx="point.x"
              :cy="point.y"
              r="4"
              class="data-point"
            />

            <!-- X-axis labels -->
            <text
              v-for="(point, idx) in chartPoints"
              :key="'label-' + idx"
              :x="point.x"
              :y="chartHeight - 5"
              class="axis-label"
              text-anchor="middle"
            >
              {{ formatDateLabel(point.date) }}
            </text>
          </svg>

          <div class="trend-legend">
            <span class="legend-item">
              <span class="legend-dot"></span>
              {{ $t('analytics.llmPatterns.costPerDay') }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useExpansion } from '@/composables/useExpansion'
import {
  useLLMPatternData,
  type LLMPatternStats,
  type LLMPatternRecommendation,
  type LLMPatternModelData,
  type LLMPatternCategoryData,
  type LLMPatternCacheOpportunity,
  type LLMPatternAnalysisResult
} from '@/composables/analytics/useLLMPatternData'

// Types (aliases for component-local readability)
type Stats = LLMPatternStats
type Recommendation = LLMPatternRecommendation
type ModelData = LLMPatternModelData
type CategoryData = LLMPatternCategoryData
type CacheOpportunity = LLMPatternCacheOpportunity
type AnalysisResult = LLMPatternAnalysisResult

const {
  fetchStats: fetchStatsData,
  fetchRecommendations: fetchRecommendationsData,
  fetchModelComparison: fetchModelComparisonData,
  fetchCategoryDistribution,
  fetchCacheOpportunities: fetchCacheOpportunitiesData,
  analyzePrompt: analyzePromptData
} = useLLMPatternData()

// State
const stats = ref<Stats>({
  total_requests: 0,
  total_cost: 0,
  avg_cost_per_request: 0,
  success_rate: 100,
  by_date: [],
  by_model: {}
})

const recommendations = ref<Recommendation[]>([])
const modelComparison = ref<ModelData[]>([])
const categoryData = ref<CategoryData>({ categories: [], total_count: 0, total_cost: 0 })
const cacheOpportunities = ref<CacheOpportunity[]>([])

const analyzePrompt = ref('')
const analyzeModel = ref('')
const analysisResult = ref<AnalysisResult | null>(null)
const { isExpanded: isRecExpanded, expand: expandRec, collapseAll: collapseAllRecs } = useExpansion<string>()

// Chart configuration
const chartWidth = 800
const chartHeight = 200
const chartPadding = 40

// Computed
const potentialSavings = computed(() => {
  return recommendations.value.reduce((sum, r) => sum + r.potential_savings, 0)
})

const chartPoints = computed(() => {
  if (!stats.value.by_date?.length) return []

  const dates = [...stats.value.by_date].reverse()
  const maxCost = Math.max(...dates.map(d => d.cost), 0.01)
  const availableWidth = chartWidth - 2 * chartPadding
  const availableHeight = chartHeight - 2 * chartPadding

  return dates.map((d, idx) => ({
    x: chartPadding + (idx * availableWidth) / Math.max(dates.length - 1, 1),
    y: chartPadding + availableHeight - (d.cost / maxCost) * availableHeight,
    date: d.date,
    cost: d.cost
  }))
})

const costLinePath = computed(() => {
  if (chartPoints.value.length < 2) return ''

  let path = `M ${chartPoints.value[0].x} ${chartPoints.value[0].y}`
  for (let i = 1; i < chartPoints.value.length; i++) {
    path += ` L ${chartPoints.value[i].x} ${chartPoints.value[i].y}`
  }
  return path
})

// Methods
const formatCost = (cost: number): string => {
  if (cost >= 1) return cost.toFixed(2)
  if (cost >= 0.01) return cost.toFixed(3)
  return cost.toFixed(4)
}

const formatTokens = (tokens: number): string => {
  if (tokens >= 1000000) return (tokens / 1000000).toFixed(1) + 'M'
  if (tokens >= 1000) return (tokens / 1000).toFixed(1) + 'K'
  return String(tokens)
}

const formatCategory = (category: string): string => {
  return category.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

const formatDateLabel = (dateStr: string): string => {
  const date = new Date(dateStr)
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

const maxModelCost = computed((): number => {
  if (!modelComparison.value.length) return 0
  return Math.max(...modelComparison.value.map(m => m.total_cost))
})

const getModelBarWidth = (model: ModelData): number => {
  const maxCost = maxModelCost.value
  if (maxCost === 0) return 0
  return (model.total_cost / maxCost) * 100
}

const toggleSteps = (type: string) => {
  const wasExpanded = isRecExpanded(type)
  collapseAllRecs()
  if (!wasExpanded) expandRec(type)
}

// API Calls
const fetchStats = async () => {
  const data = await fetchStatsData(7)
  if (data) stats.value = data
}

const fetchRecommendations = async () => {
  recommendations.value = await fetchRecommendationsData()
}

const fetchModelComparison = async () => {
  modelComparison.value = await fetchModelComparisonData()
}

const fetchCategoryDistributionData = async () => {
  const data = await fetchCategoryDistribution()
  if (data) categoryData.value = data
}

const fetchCacheOpportunities = async () => {
  cacheOpportunities.value = await fetchCacheOpportunitiesData()
}

const runAnalysis = async () => {
  if (!analyzePrompt.value) return
  const result = await analyzePromptData(analyzePrompt.value, analyzeModel.value || null)
  if (result) analysisResult.value = result
}

// Lifecycle
onMounted(() => {
  fetchStats()
  fetchRecommendations()
  fetchModelComparison()
  fetchCategoryDistributionData()
  fetchCacheOpportunities()
})
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */

.llm-pattern-dashboard {
  padding: var(--spacing-6);
  background: var(--bg-primary);
  min-height: 100%;
  color: var(--text-primary);
}

.dashboard-header {
  margin-bottom: var(--spacing-6);
}

.dashboard-header h2 {
  font-size: var(--text-2xl);
  font-weight: 600;
  color: var(--text-primary);
  margin: var(--spacing-0);
}

.subtitle {
  color: var(--text-secondary);
  font-size: var(--text-sm);
  margin: var(--spacing-1) var(--spacing-0) var(--spacing-0) var(--spacing-0);
}

/* Stats Grid */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-6);
}

.stat-card {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  background: var(--bg-surface);
  border: 1px solid var(--border-secondary);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
}

.stat-icon {
  width: 2.5rem;
  height: 2.5rem;
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
}

.stat-icon svg {
  width: 1.25rem;
  height: 1.25rem;
}

.stat-icon.requests { background: var(--color-info-bg); color: var(--color-info); }
.stat-icon.cost { background: var(--color-error-bg); color: var(--color-error); }
.stat-icon.avg { background: rgba(168, 85, 247, 0.2); color: var(--color-purple-light); }
.stat-icon.savings { background: var(--color-success-bg); color: var(--chart-green); }

.stat-content {
  display: flex;
  flex-direction: column;
}

.stat-value {
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--text-primary);
}

.stat-label {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

/* Content Grid */
.content-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-6);
  margin-bottom: var(--spacing-6);
}

.left-column,
.right-column {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-6);
}

/* Panels */
.panel {
  background: var(--bg-surface);
  border: 1px solid var(--border-secondary);
  border-radius: var(--radius-lg);
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-4);
  border-bottom: 1px solid var(--border-secondary);
}

.panel-header h3 {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
  margin: var(--spacing-0);
}

.panel-content {
  padding: var(--spacing-4);
}

.empty-state {
  text-align: center;
  color: var(--text-tertiary);
  padding: var(--spacing-8);
}

.refresh-btn {
  background: transparent;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: var(--spacing-1);
}

.refresh-btn:hover {
  color: var(--text-primary);
}

.refresh-btn svg {
  width: 1rem;
  height: 1rem;
}

/* Prompt Analyzer */
.form-group {
  margin-bottom: var(--spacing-3);
}

.form-group textarea,
.form-row select {
  width: 100%;
  padding: var(--spacing-3);
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: var(--text-sm);
  resize: vertical;
}

.form-group textarea:focus,
.form-row select:focus {
  outline: none;
  border-color: var(--color-info);
}
.form-group textarea:focus-visible,
.form-row select:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.form-row {
  display: flex;
  gap: var(--spacing-2);
}

.form-row select {
  flex: 1;
}

.analyze-btn {
  padding: var(--spacing-3) var(--spacing-6);
  background: var(--color-info);
  border: none;
  border-radius: var(--radius-md);
  color: #fff;
  font-size: var(--text-sm);
  cursor: pointer;
  transition: background var(--duration-200);
}

.analyze-btn:hover:not(:disabled) {
  background: var(--color-info-hover);
}

.analyze-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Analysis Result */
.analysis-result {
  margin-top: var(--spacing-4);
  padding: var(--spacing-4);
  background: var(--bg-primary);
  border: 1px solid var(--border-secondary);
  border-radius: var(--radius-md);
}

.result-header {
  display: flex;
  gap: var(--spacing-2);
  flex-wrap: wrap;
  margin-bottom: var(--spacing-3);
}

.category-badge,
.tokens-badge,
.cost-badge {
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-default);
  font-size: var(--text-xs);
}

.category-badge {
  background: rgba(168, 85, 247, 0.2);
  color: var(--color-purple-light);
  text-transform: capitalize;
}

.tokens-badge {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.cost-badge {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.issues-list,
.recommendations-list {
  margin-bottom: var(--spacing-3);
}

.issue-item {
  padding: var(--spacing-2);
  border-radius: var(--radius-default);
  font-size: 0.8125rem;
  margin-bottom: var(--spacing-1);
}

.issue-item.warning {
  background: var(--color-warning-alpha-10);
  color: var(--color-warning-light);
}

.issue-item.info {
  background: var(--color-info-bg);
  color: var(--color-info-light);
}

.recommendation-item {
  padding: var(--spacing-2);
  background: var(--color-success-alpha-10);
  border-radius: var(--radius-default);
  font-size: 0.8125rem;
  color: var(--chart-green-light);
  margin-bottom: var(--spacing-1);
}

.cache-indicator {
  padding: var(--spacing-2);
  background: rgba(168, 85, 247, 0.1);
  border-radius: var(--radius-default);
  font-size: 0.8125rem;
  color: var(--chart-purple-light);
  text-align: center;
}

/* Recommendations Grid */
.recommendations-grid {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

.recommendation-card {
  padding: var(--spacing-4);
  background: var(--bg-primary);
  border: 1px solid var(--border-secondary);
  border-radius: var(--radius-md);
}

.recommendation-card.priority-1 { border-left: 3px solid var(--color-error); }
.recommendation-card.priority-2 { border-left: 3px solid var(--color-warning); }
.recommendation-card.priority-3 { border-left: 3px solid var(--color-info); }
.recommendation-card.priority-4 { border-left: 3px solid var(--text-tertiary); }

.rec-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: var(--spacing-2);
}

.rec-type {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  text-transform: uppercase;
}

.rec-savings {
  font-size: var(--text-sm);
  color: var(--chart-green);
  font-weight: 500;
}

.recommendation-card h4 {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-2) var(--spacing-0);
}

.recommendation-card p {
  font-size: 0.8125rem;
  color: var(--text-secondary);
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-2) var(--spacing-0);
}

.rec-meta {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  margin-bottom: var(--spacing-2);
}

.expand-btn {
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-default);
  color: var(--text-secondary);
  font-size: var(--text-xs);
  padding: var(--spacing-1) var(--spacing-2);
  cursor: pointer;
}

.expand-btn:hover {
  background: var(--border-secondary);
  color: var(--text-primary);
}

.rec-steps {
  margin-top: var(--spacing-3);
  padding-top: var(--spacing-3);
  border-top: 1px solid var(--border-secondary);
}

.rec-steps ol {
  margin: var(--spacing-0);
  padding-left: var(--spacing-5);
  font-size: 0.8125rem;
  color: var(--text-tertiary);
}

.rec-steps li {
  margin-bottom: var(--spacing-1);
}

/* Model List */
.model-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.model-item {
  padding: var(--spacing-3);
  background: var(--bg-primary);
  border-radius: var(--radius-md);
}

.model-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: var(--spacing-2);
}

.model-name {
  font-weight: 500;
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.model-cost {
  color: var(--color-warning);
  font-size: var(--text-sm);
}

.model-stats {
  display: flex;
  gap: var(--spacing-4);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-2);
}

.model-bar {
  height: 4px;
  background: var(--border-secondary);
  border-radius: var(--radius-xs);
  overflow: hidden;
}

.model-bar-fill {
  height: 100%;
  background: var(--color-info);
  border-radius: var(--radius-xs);
  transition: width var(--duration-300);
}

/* Category List */
.category-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.category-item {
  padding: var(--spacing-2) var(--spacing-0);
}

.category-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: var(--spacing-1);
}

.category-name {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

.category-count {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.category-bar {
  height: 4px;
  background: var(--border-secondary);
  border-radius: var(--radius-xs);
  overflow: hidden;
  margin-bottom: var(--spacing-1);
}

.category-bar-fill {
  height: 100%;
  background: var(--color-success);
  border-radius: var(--radius-xs);
  transition: width var(--duration-300);
}

.category-meta {
  display: flex;
  justify-content: space-between;
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

/* Cache List */
.cache-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.cache-item {
  padding: var(--spacing-3);
  background: var(--bg-primary);
  border-radius: var(--radius-md);
}

.cache-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: var(--spacing-2);
}

.cache-count {
  font-weight: 500;
  color: var(--color-purple-light);
  font-size: var(--text-sm);
}

.cache-savings {
  color: var(--chart-green);
  font-size: var(--text-xs);
}

.cache-preview {
  font-size: 0.8125rem;
  color: var(--text-secondary);
  margin: var(--spacing-0);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Trend Panel */
.trend-panel {
  margin-top: var(--spacing-6);
}

.trend-chart {
  padding: var(--spacing-4);
}

.chart-svg {
  width: 100%;
  height: auto;
}

.grid-line {
  stroke: var(--border-secondary);
  stroke-width: 1;
}

.cost-line {
  stroke: var(--color-info);
  stroke-width: 2;
}

.data-point {
  fill: var(--color-info);
}

.axis-label {
  font-size: var(--text-xs);
  fill: var(--text-secondary);
}

.trend-legend {
  display: flex;
  justify-content: center;
  gap: var(--spacing-4);
  margin-top: var(--spacing-2);
}

.legend-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.legend-dot {
  width: 8px;
  height: 8px;
  background: var(--color-info);
  border-radius: 50%;
}

/* Responsive */
@media (max-width: 1024px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .content-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }

  .form-row {
    flex-direction: column;
  }
}
</style>
