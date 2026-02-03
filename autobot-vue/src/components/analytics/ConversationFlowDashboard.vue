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
/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 *
 * ConversationFlowDashboard.vue - Conversation flow analysis dashboard
 * Issue #704: Migrated to design tokens for centralized theming
 */
import { ref, onMounted, computed } from 'vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ConversationFlowDashboard')

/**
 * Helper to get CSS custom property value for dynamic JS usage.
 * Issue #704: Added for design token integration in JavaScript.
 *
 * @param varName - CSS variable name (e.g., '--color-success')
 * @returns The computed value of the CSS variable
 */
const getCssVar = (varName: string): string => {
  return getComputedStyle(document.documentElement).getPropertyValue(varName).trim()
}

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
    logger.error('Failed to analyze conversations:', error)
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

// Expose getCssVar for potential external usage (e.g., charts)
defineExpose({ getCssVar })
</script>

<style scoped>
/* Issue #704: Migrated all hardcoded colors to design tokens */

.conversation-flow-dashboard {
  padding: var(--spacing-6);
  background: var(--bg-primary);
  min-height: 100vh;
  color: var(--text-primary);
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-6);
  padding-bottom: var(--spacing-4);
  border-bottom: 1px solid var(--border-subtle);
}

.header-content h2 {
  margin: 0;
  font-size: var(--text-2xl);
  color: var(--text-primary);
}

.header-content h2 i {
  color: var(--chart-cyan);
  margin-right: var(--spacing-2);
}

.subtitle {
  margin: var(--spacing-1) 0 0;
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.header-actions {
  display: flex;
  gap: var(--spacing-4);
  align-items: center;
}

.time-select {
  padding: var(--spacing-2) var(--spacing-4);
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  cursor: pointer;
}

.analyze-btn {
  padding: var(--spacing-2) var(--spacing-5);
  background: linear-gradient(135deg, var(--chart-cyan) 0%, var(--color-info-dark) 100%);
  border: none;
  border-radius: var(--radius-md);
  color: var(--text-on-primary);
  font-weight: var(--font-medium);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  transition: var(--transition-all);
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
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-6);
}

.metric-card {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-xl);
  padding: var(--spacing-5);
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
}

.metric-icon {
  width: 56px;
  height: 56px;
  border-radius: var(--radius-xl);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-2xl);
}

.metric-icon.conversations {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.metric-icon.messages {
  background: var(--chart-purple-bg);
  color: var(--chart-purple);
}

.metric-icon.satisfaction {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.metric-icon.satisfaction.medium {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.metric-icon.satisfaction.low {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.metric-icon.resolution {
  background: rgba(6, 182, 212, 0.2);
  color: var(--chart-cyan);
}

.metric-value {
  font-size: var(--text-3xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
}

.metric-label {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
}

/* Content Grid */
.content-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-6);
}

.panel {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-xl);
  overflow: hidden;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-4) var(--spacing-5);
  border-bottom: 1px solid var(--border-subtle);
}

.panel-header h3 {
  margin: 0;
  font-size: var(--text-base);
  color: var(--text-primary);
}

.panel-header h3 i {
  margin-right: var(--spacing-2);
  color: var(--chart-cyan);
}

.count-badge {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  padding: var(--spacing-1) var(--spacing-3);
  border-radius: var(--radius-xl);
}

.panel-content {
  padding: var(--spacing-4);
  max-height: 400px;
  overflow-y: auto;
}

/* Intent List */
.intent-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.intent-item {
  background: var(--bg-primary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--spacing-3-5);
  cursor: pointer;
  transition: var(--transition-all);
}

.intent-item:hover {
  border-color: var(--chart-cyan);
  transform: translateX(2px);
}

.intent-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-2);
}

.intent-name {
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.occurrence-count {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-full);
}

.intent-progress {
  height: 4px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-xs);
  overflow: hidden;
  margin-bottom: var(--spacing-2);
}

.progress-bar {
  height: 100%;
  border-radius: var(--radius-xs);
  transition: width var(--duration-300);
}

.progress-bar.success-high {
  background: var(--color-success);
}

.progress-bar.success-medium {
  background: var(--color-warning);
}

.progress-bar.success-low {
  background: var(--color-error);
}

.intent-meta {
  display: flex;
  gap: var(--spacing-4);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.intent-meta i {
  margin-right: var(--spacing-1);
}

/* Flow List */
.flow-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.flow-item {
  background: var(--bg-primary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--spacing-3-5);
}

.flow-path {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--spacing-1);
  margin-bottom: var(--spacing-2);
}

.flow-step {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-default);
}

.flow-step i {
  font-size: 0.6rem;
  color: var(--text-muted);
}

.flow-stats {
  display: flex;
  gap: var(--spacing-4);
}

.flow-stats .stat {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.flow-stats .stat i {
  margin-right: var(--spacing-1);
}

/* Bottleneck List */
.bottleneck-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.bottleneck-item {
  background: var(--bg-primary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--spacing-3-5);
}

.bottleneck-item.impact-high {
  border-left: 3px solid var(--color-error);
}

.bottleneck-item.impact-medium {
  border-left: 3px solid var(--color-warning);
}

.bottleneck-item.impact-low {
  border-left: 3px solid var(--color-success);
}

.bottleneck-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  margin-bottom: var(--spacing-2);
}

.impact-badge {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-full);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-xs);
  font-weight: var(--font-bold);
}

.impact-badge.impact-high {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.impact-badge.impact-medium {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.impact-badge.impact-low {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.bottleneck-item .location {
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.bottleneck-item .description {
  margin: 0 0 var(--spacing-3);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.suggestions {
  font-size: var(--text-xs);
}

.suggestion-label {
  color: var(--text-secondary);
  font-weight: var(--font-medium);
}

.suggestions ul {
  margin: var(--spacing-1) 0 0;
  padding-left: var(--spacing-5);
  color: var(--text-muted);
}

.suggestions li {
  margin-bottom: var(--spacing-0-5);
}

/* Distribution Chart */
.distribution-chart {
  display: flex;
  align-items: flex-end;
  height: 120px;
  gap: 4px;
  padding-top: var(--spacing-4);
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
  background: linear-gradient(to top, var(--chart-cyan), var(--color-info-dark));
  border-radius: var(--radius-xs) var(--radius-xs) 0 0;
  transition: height var(--duration-300);
  min-height: 2px;
}

.hour-label {
  font-size: 0.6rem;
  color: var(--text-muted);
  margin-top: var(--spacing-1);
  writing-mode: vertical-lr;
  transform: rotate(180deg);
}

/* Empty State */
.empty-state {
  text-align: center;
  padding: var(--spacing-8);
  color: var(--text-muted);
}

.empty-state i {
  font-size: var(--text-3xl);
  margin-bottom: var(--spacing-2);
}

.empty-state.success {
  color: var(--color-success);
}

.empty-state.success i {
  color: var(--color-success);
}

.empty-state-full {
  text-align: center;
  padding: var(--spacing-16);
  color: var(--text-muted);
}

.empty-state-full i {
  font-size: var(--text-5xl);
  margin-bottom: var(--spacing-4);
  color: var(--border-subtle);
}

.empty-state-full h3 {
  margin: 0 0 var(--spacing-2);
  color: var(--text-secondary);
}

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: var(--overlay-backdrop);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal);
}

.modal-content {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-xl);
  width: 90%;
  max-width: 500px;
  max-height: 80vh;
  overflow-y: auto;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-4) var(--spacing-5);
  border-bottom: 1px solid var(--border-subtle);
}

.modal-header h3 {
  margin: 0;
  color: var(--text-primary);
}

.close-btn {
  background: none;
  border: none;
  color: var(--text-secondary);
  font-size: var(--text-xl);
  cursor: pointer;
}

.close-btn:hover {
  color: var(--text-primary);
}

.modal-body {
  padding: var(--spacing-5);
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-6);
}

.detail-item {
  background: var(--bg-primary);
  padding: var(--spacing-3);
  border-radius: var(--radius-md);
}

.detail-item .label {
  display: block;
  font-size: var(--text-xs);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-1);
}

.detail-item .value {
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.detail-item .value.success-high {
  color: var(--color-success);
}

.detail-item .value.success-medium {
  color: var(--color-warning);
}

.detail-item .value.success-low {
  color: var(--color-error);
}

.samples-section h4 {
  margin: 0 0 var(--spacing-3);
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.sample-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.sample-item {
  background: var(--bg-primary);
  padding: var(--spacing-2);
  border-radius: var(--radius-default);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

/* Loading */
.loading-state {
  text-align: center;
  padding: var(--spacing-16);
  color: var(--chart-cyan);
}

.loading-state p {
  margin-top: var(--spacing-4);
  color: var(--text-secondary);
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
    gap: var(--spacing-4);
    align-items: flex-start;
  }

  .metrics-grid {
    grid-template-columns: 1fr;
  }
}
</style>
