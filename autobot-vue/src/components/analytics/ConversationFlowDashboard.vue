<template>
  <div class="conversation-flow-dashboard">
    <!-- Header -->
    <div class="dashboard-header">
      <div class="header-content">
        <h2><i class="fas fa-comments"></i> Conversation Flow Analyzer</h2>
        <p class="subtitle">Understand user intents, conversation patterns, and bottlenecks</p>
      </div>
      <div class="header-actions">
        <select v-model="timeRange" class="time-select" @change="runAnalysis">
          <option value="6">Last 6 hours</option>
          <option value="24">Last 24 hours</option>
          <option value="72">Last 3 days</option>
          <option value="168">Last 7 days</option>
        </select>
        <button @click="runAnalysis" class="analyze-btn" :disabled="isLoading">
          <i :class="isLoading ? 'fas fa-spinner fa-spin' : 'fas fa-chart-line'"></i>
          {{ isLoading ? 'Analyzing...' : 'Analyze' }}
        </button>
      </div>
    </div>

    <!-- Metrics Cards -->
    <div class="metrics-grid" v-if="analysisResult?.metrics">
      <div class="metric-card">
        <div class="metric-icon conversations">
          <i class="fas fa-comment-dots"></i>
        </div>
        <div class="metric-content">
          <div class="metric-value">{{ analysisResult.metrics.total_conversations }}</div>
          <div class="metric-label">Total Conversations</div>
        </div>
      </div>
      <div class="metric-card">
        <div class="metric-icon messages">
          <i class="fas fa-envelope"></i>
        </div>
        <div class="metric-content">
          <div class="metric-value">{{ analysisResult.metrics.avg_messages_per_conversation }}</div>
          <div class="metric-label">Avg Messages/Conv</div>
        </div>
      </div>
      <div class="metric-card">
        <div class="metric-icon satisfaction" :class="getSatisfactionClass(analysisResult.metrics.user_satisfaction_estimate)">
          <i class="fas fa-smile"></i>
        </div>
        <div class="metric-content">
          <div class="metric-value">{{ analysisResult.metrics.user_satisfaction_estimate }}%</div>
          <div class="metric-label">Satisfaction</div>
        </div>
      </div>
      <div class="metric-card">
        <div class="metric-icon resolution">
          <i class="fas fa-check-circle"></i>
        </div>
        <div class="metric-content">
          <div class="metric-value">{{ analysisResult.metrics.resolution_rate }}%</div>
          <div class="metric-label">Resolution Rate</div>
        </div>
      </div>
    </div>

    <!-- Main Content -->
    <div class="content-grid" v-if="analysisResult">
      <!-- Intent Patterns -->
      <div class="panel intents-panel">
        <div class="panel-header">
          <h3><i class="fas fa-bullseye"></i> User Intents</h3>
          <span class="count-badge">{{ analysisResult.intent_patterns.length }} detected</span>
        </div>
        <div class="panel-content">
          <div class="intent-list">
            <div
              v-for="intent in analysisResult.intent_patterns"
              :key="intent.intent_id"
              class="intent-item"
              @click="selectedIntent = intent"
            >
              <div class="intent-header">
                <span class="intent-name">{{ intent.intent_name }}</span>
                <span class="occurrence-count">{{ intent.occurrences }}x</span>
              </div>
              <div class="intent-progress">
                <div
                  class="progress-bar"
                  :style="{ width: intent.success_rate + '%' }"
                  :class="getSuccessClass(intent.success_rate)"
                ></div>
              </div>
              <div class="intent-meta">
                <span><i class="fas fa-check"></i> {{ intent.success_rate }}% success</span>
                <span><i class="fas fa-exchange-alt"></i> {{ intent.avg_turns_to_resolve }} turns avg</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Common Flows -->
      <div class="panel flows-panel">
        <div class="panel-header">
          <h3><i class="fas fa-route"></i> Common Flow Paths</h3>
        </div>
        <div class="panel-content">
          <div v-if="analysisResult.common_flows.length === 0" class="empty-state">
            <i class="fas fa-route"></i>
            <p>Not enough data for flow analysis</p>
          </div>
          <div v-else class="flow-list">
            <div
              v-for="flow in analysisResult.common_flows"
              :key="flow.flow_id"
              class="flow-item"
            >
              <div class="flow-path">
                <span
                  v-for="(step, idx) in flow.path"
                  :key="idx"
                  class="flow-step"
                >
                  {{ formatIntentName(step) }}
                  <i v-if="idx < flow.path.length - 1" class="fas fa-chevron-right"></i>
                </span>
              </div>
              <div class="flow-stats">
                <span class="stat">
                  <i class="fas fa-redo"></i> {{ flow.frequency }}x
                </span>
                <span class="stat">
                  <i class="fas fa-check-circle"></i> {{ flow.completion_rate }}%
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Bottlenecks -->
      <div class="panel bottlenecks-panel">
        <div class="panel-header">
          <h3><i class="fas fa-exclamation-triangle"></i> Identified Bottlenecks</h3>
        </div>
        <div class="panel-content">
          <div v-if="analysisResult.bottlenecks.length === 0" class="empty-state success">
            <i class="fas fa-thumbs-up"></i>
            <p>No significant bottlenecks detected</p>
          </div>
          <div v-else class="bottleneck-list">
            <div
              v-for="bottleneck in analysisResult.bottlenecks"
              :key="bottleneck.bottleneck_id"
              class="bottleneck-item"
              :class="getImpactClass(bottleneck.impact_score)"
            >
              <div class="bottleneck-header">
                <span class="impact-badge" :class="getImpactClass(bottleneck.impact_score)">
                  {{ Math.round(bottleneck.impact_score) }}
                </span>
                <span class="location">{{ formatIntentName(bottleneck.location) }}</span>
              </div>
              <p class="description">{{ bottleneck.description }}</p>
              <div class="suggestions">
                <span class="suggestion-label">Suggestions:</span>
                <ul>
                  <li v-for="(suggestion, idx) in bottleneck.suggested_improvements" :key="idx">
                    {{ suggestion }}
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Hourly Distribution -->
      <div class="panel distribution-panel">
        <div class="panel-header">
          <h3><i class="fas fa-clock"></i> Activity Distribution</h3>
        </div>
        <div class="panel-content">
          <div class="distribution-chart">
            <div
              v-for="(count, hour) in analysisResult.hourly_distribution"
              :key="hour"
              class="hour-bar"
            >
              <div
                class="bar-fill"
                :style="{ height: getBarHeight(count) + '%' }"
              ></div>
              <span class="hour-label">{{ hour }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Intent Detail Modal -->
    <div v-if="selectedIntent" class="modal-overlay" @click="selectedIntent = null">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h3>{{ selectedIntent.intent_name }}</h3>
          <button @click="selectedIntent = null" class="close-btn">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="modal-body">
          <div class="detail-grid">
            <div class="detail-item">
              <span class="label">Intent ID</span>
              <span class="value">{{ selectedIntent.intent_id }}</span>
            </div>
            <div class="detail-item">
              <span class="label">Total Occurrences</span>
              <span class="value">{{ selectedIntent.occurrences }}</span>
            </div>
            <div class="detail-item">
              <span class="label">Success Rate</span>
              <span class="value" :class="getSuccessClass(selectedIntent.success_rate)">
                {{ selectedIntent.success_rate }}%
              </span>
            </div>
            <div class="detail-item">
              <span class="label">Avg Turns to Resolve</span>
              <span class="value">{{ selectedIntent.avg_turns_to_resolve }}</span>
            </div>
          </div>
          <div v-if="selectedIntent.sample_queries?.length" class="samples-section">
            <h4>Sample Queries</h4>
            <div class="sample-list">
              <div v-for="(sample, idx) in selectedIntent.sample_queries" :key="idx" class="sample-item">
                {{ sample }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="isLoading && !analysisResult" class="loading-state">
      <i class="fas fa-cog fa-spin fa-3x"></i>
      <p>Analyzing conversation patterns...</p>
    </div>

    <!-- Empty State -->
    <div v-if="!isLoading && !analysisResult" class="empty-state-full">
      <i class="fas fa-comments"></i>
      <h3>No Analysis Data</h3>
      <p>Click "Analyze" to start analyzing conversation patterns</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'

// Types
interface IntentPattern {
  intent_id: string
  intent_name: string
  pattern_regex: string
  occurrences: number
  success_rate: number
  avg_turns_to_resolve: number
  sample_queries: string[]
}

interface ConversationFlow {
  flow_id: string
  path: string[]
  frequency: number
  avg_duration_seconds: number
  completion_rate: number
  drop_off_point: string | null
}

interface FlowBottleneck {
  bottleneck_id: string
  location: string
  description: string
  impact_score: number
  affected_conversations: number
  suggested_improvements: string[]
}

interface ConversationMetrics {
  total_conversations: number
  total_messages: number
  avg_messages_per_conversation: number
  avg_conversation_duration_seconds: number
  user_satisfaction_estimate: number
  resolution_rate: number
  escalation_rate: number
}

interface AnalysisResult {
  metrics: ConversationMetrics
  intent_patterns: IntentPattern[]
  common_flows: ConversationFlow[]
  bottlenecks: FlowBottleneck[]
  hourly_distribution: Record<string, number>
  analysis_period: string
  conversations_analyzed: number
}

// State
const timeRange = ref(24)
const isLoading = ref(false)
const analysisResult = ref<AnalysisResult | null>(null)
const selectedIntent = ref<IntentPattern | null>(null)

// Computed
const maxHourlyCount = computed(() => {
  if (!analysisResult.value?.hourly_distribution) return 1
  return Math.max(...Object.values(analysisResult.value.hourly_distribution), 1)
})

// Methods
const runAnalysis = async () => {
  isLoading.value = true
  try {
    const response = await fetch(`/api/conversation-flow/analyze?hours=${timeRange.value}`)
    if (response.ok) {
      analysisResult.value = await response.json()
    }
  } catch (error) {
    console.error('Failed to analyze conversations:', error)
  } finally {
    isLoading.value = false
  }
}

const formatIntentName = (intentId: string): string => {
  return intentId
    .replace(/_/g, ' ')
    .replace(/\b\w/g, l => l.toUpperCase())
}

const getSatisfactionClass = (score: number): string => {
  if (score >= 80) return 'high'
  if (score >= 50) return 'medium'
  return 'low'
}

const getSuccessClass = (rate: number): string => {
  if (rate >= 80) return 'success-high'
  if (rate >= 50) return 'success-medium'
  return 'success-low'
}

const getImpactClass = (score: number): string => {
  if (score >= 70) return 'impact-high'
  if (score >= 40) return 'impact-medium'
  return 'impact-low'
}

const getBarHeight = (count: number): number => {
  return (count / maxHourlyCount.value) * 100
}

// Lifecycle
onMounted(() => {
  runAnalysis()
})
</script>

<style scoped>
.conversation-flow-dashboard {
  padding: 1.5rem;
  background: #0f0f1a;
  min-height: 100vh;
  color: #e5e7eb;
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid #2a2a3e;
}

.header-content h2 {
  margin: 0;
  font-size: 1.5rem;
  color: #f9fafb;
}

.header-content h2 i {
  color: #06b6d4;
  margin-right: 0.5rem;
}

.subtitle {
  margin: 0.25rem 0 0;
  color: #9ca3af;
  font-size: 0.875rem;
}

.header-actions {
  display: flex;
  gap: 1rem;
  align-items: center;
}

.time-select {
  padding: 0.5rem 1rem;
  background: #1a1a2e;
  border: 1px solid #2a2a3e;
  border-radius: 6px;
  color: #e5e7eb;
  cursor: pointer;
}

.analyze-btn {
  padding: 0.5rem 1.25rem;
  background: linear-gradient(135deg, #06b6d4 0%, #0891b2 100%);
  border: none;
  border-radius: 6px;
  color: white;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  transition: all 0.2s;
}

.analyze-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(6, 182, 212, 0.4);
}

.analyze-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

/* Metrics Grid */
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.metric-card {
  background: #1a1a2e;
  border: 1px solid #2a2a3e;
  border-radius: 12px;
  padding: 1.25rem;
  display: flex;
  align-items: center;
  gap: 1rem;
}

.metric-icon {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.5rem;
}

.metric-icon.conversations {
  background: rgba(59, 130, 246, 0.2);
  color: #3b82f6;
}

.metric-icon.messages {
  background: rgba(139, 92, 246, 0.2);
  color: #8b5cf6;
}

.metric-icon.satisfaction {
  background: rgba(34, 197, 94, 0.2);
  color: #22c55e;
}

.metric-icon.satisfaction.medium {
  background: rgba(245, 158, 11, 0.2);
  color: #f59e0b;
}

.metric-icon.satisfaction.low {
  background: rgba(239, 68, 68, 0.2);
  color: #ef4444;
}

.metric-icon.resolution {
  background: rgba(6, 182, 212, 0.2);
  color: #06b6d4;
}

.metric-value {
  font-size: 1.75rem;
  font-weight: 700;
  color: #f9fafb;
}

.metric-label {
  font-size: 0.75rem;
  color: #9ca3af;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* Content Grid */
.content-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
}

.panel {
  background: #1a1a2e;
  border: 1px solid #2a2a3e;
  border-radius: 12px;
  overflow: hidden;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid #2a2a3e;
}

.panel-header h3 {
  margin: 0;
  font-size: 1rem;
  color: #f9fafb;
}

.panel-header h3 i {
  margin-right: 0.5rem;
  color: #06b6d4;
}

.count-badge {
  font-size: 0.75rem;
  color: #9ca3af;
  background: #2a2a3e;
  padding: 0.25rem 0.75rem;
  border-radius: 12px;
}

.panel-content {
  padding: 1rem;
  max-height: 400px;
  overflow-y: auto;
}

/* Intent List */
.intent-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.intent-item {
  background: #111827;
  border: 1px solid #2a2a3e;
  border-radius: 8px;
  padding: 0.875rem;
  cursor: pointer;
  transition: all 0.2s;
}

.intent-item:hover {
  border-color: #06b6d4;
  transform: translateX(2px);
}

.intent-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.intent-name {
  font-weight: 500;
  color: #f9fafb;
}

.occurrence-count {
  font-size: 0.75rem;
  color: #9ca3af;
  background: #2a2a3e;
  padding: 0.125rem 0.5rem;
  border-radius: 10px;
}

.intent-progress {
  height: 4px;
  background: #374151;
  border-radius: 2px;
  overflow: hidden;
  margin-bottom: 0.5rem;
}

.progress-bar {
  height: 100%;
  border-radius: 2px;
  transition: width 0.3s;
}

.progress-bar.success-high {
  background: #22c55e;
}

.progress-bar.success-medium {
  background: #f59e0b;
}

.progress-bar.success-low {
  background: #ef4444;
}

.intent-meta {
  display: flex;
  gap: 1rem;
  font-size: 0.7rem;
  color: #9ca3af;
}

.intent-meta i {
  margin-right: 0.25rem;
}

/* Flow List */
.flow-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.flow-item {
  background: #111827;
  border: 1px solid #2a2a3e;
  border-radius: 8px;
  padding: 0.875rem;
}

.flow-path {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem;
  margin-bottom: 0.5rem;
}

.flow-step {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.75rem;
  color: #d1d5db;
  background: #2a2a3e;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
}

.flow-step i {
  font-size: 0.6rem;
  color: #6b7280;
}

.flow-stats {
  display: flex;
  gap: 1rem;
}

.flow-stats .stat {
  font-size: 0.7rem;
  color: #9ca3af;
}

.flow-stats .stat i {
  margin-right: 0.25rem;
}

/* Bottleneck List */
.bottleneck-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.bottleneck-item {
  background: #111827;
  border: 1px solid #2a2a3e;
  border-radius: 8px;
  padding: 0.875rem;
}

.bottleneck-item.impact-high {
  border-left: 3px solid #ef4444;
}

.bottleneck-item.impact-medium {
  border-left: 3px solid #f59e0b;
}

.bottleneck-item.impact-low {
  border-left: 3px solid #22c55e;
}

.bottleneck-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
}

.impact-badge {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.75rem;
  font-weight: 700;
}

.impact-badge.impact-high {
  background: rgba(239, 68, 68, 0.2);
  color: #ef4444;
}

.impact-badge.impact-medium {
  background: rgba(245, 158, 11, 0.2);
  color: #f59e0b;
}

.impact-badge.impact-low {
  background: rgba(34, 197, 94, 0.2);
  color: #22c55e;
}

.bottleneck-item .location {
  font-weight: 500;
  color: #f9fafb;
}

.bottleneck-item .description {
  margin: 0 0 0.75rem;
  font-size: 0.85rem;
  color: #d1d5db;
}

.suggestions {
  font-size: 0.75rem;
}

.suggestion-label {
  color: #9ca3af;
  font-weight: 500;
}

.suggestions ul {
  margin: 0.25rem 0 0;
  padding-left: 1.25rem;
  color: #6b7280;
}

.suggestions li {
  margin-bottom: 0.125rem;
}

/* Distribution Chart */
.distribution-chart {
  display: flex;
  align-items: flex-end;
  height: 120px;
  gap: 4px;
  padding-top: 1rem;
}

.hour-bar {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  height: 100%;
}

.bar-fill {
  width: 100%;
  background: linear-gradient(to top, #06b6d4, #0891b2);
  border-radius: 2px 2px 0 0;
  transition: height 0.3s;
  min-height: 2px;
}

.hour-label {
  font-size: 0.6rem;
  color: #6b7280;
  margin-top: 0.25rem;
  writing-mode: vertical-lr;
  transform: rotate(180deg);
}

/* Empty State */
.empty-state {
  text-align: center;
  padding: 2rem;
  color: #6b7280;
}

.empty-state i {
  font-size: 2rem;
  margin-bottom: 0.5rem;
}

.empty-state.success {
  color: #22c55e;
}

.empty-state.success i {
  color: #22c55e;
}

.empty-state-full {
  text-align: center;
  padding: 4rem;
  color: #6b7280;
}

.empty-state-full i {
  font-size: 4rem;
  margin-bottom: 1rem;
  color: #2a2a3e;
}

.empty-state-full h3 {
  margin: 0 0 0.5rem;
  color: #9ca3af;
}

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: #1a1a2e;
  border: 1px solid #2a2a3e;
  border-radius: 12px;
  width: 90%;
  max-width: 500px;
  max-height: 80vh;
  overflow-y: auto;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid #2a2a3e;
}

.modal-header h3 {
  margin: 0;
  color: #f9fafb;
}

.close-btn {
  background: none;
  border: none;
  color: #9ca3af;
  font-size: 1.25rem;
  cursor: pointer;
}

.close-btn:hover {
  color: #f9fafb;
}

.modal-body {
  padding: 1.25rem;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.detail-item {
  background: #111827;
  padding: 0.75rem;
  border-radius: 6px;
}

.detail-item .label {
  display: block;
  font-size: 0.7rem;
  color: #9ca3af;
  margin-bottom: 0.25rem;
}

.detail-item .value {
  font-weight: 600;
  color: #f9fafb;
}

.detail-item .value.success-high {
  color: #22c55e;
}

.detail-item .value.success-medium {
  color: #f59e0b;
}

.detail-item .value.success-low {
  color: #ef4444;
}

.samples-section h4 {
  margin: 0 0 0.75rem;
  font-size: 0.875rem;
  color: #f9fafb;
}

.sample-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.sample-item {
  background: #0f0f1a;
  padding: 0.5rem;
  border-radius: 4px;
  font-size: 0.8rem;
  color: #d1d5db;
}

/* Loading */
.loading-state {
  text-align: center;
  padding: 4rem;
  color: #06b6d4;
}

.loading-state p {
  margin-top: 1rem;
  color: #9ca3af;
}

/* Responsive */
@media (max-width: 1024px) {
  .content-grid {
    grid-template-columns: 1fr;
  }

  .metrics-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 640px) {
  .dashboard-header {
    flex-direction: column;
    gap: 1rem;
    align-items: flex-start;
  }

  .metrics-grid {
    grid-template-columns: 1fr;
  }
}
</style>
