<template>
  <div class="conversation-flow-dashboard">
    <!-- Header -->
    <div class="dashboard-header">
      <div class="header-content">
        <h2><Icon name="comments" /> {{ $t('analytics.conversationFlow.title') }}</h2>
        <p class="subtitle">{{ $t('analytics.conversationFlow.subtitle') }}</p>
      </div>
      <div class="header-actions">
        <select v-model="timeRange" class="time-select" @change="runAnalysis">
          <option value="6">{{ $t('analytics.conversationFlow.last6Hours') }}</option>
          <option value="24">{{ $t('analytics.conversationFlow.last24Hours') }}</option>
          <option value="72">{{ $t('analytics.conversationFlow.last3Days') }}</option>
          <option value="168">{{ $t('analytics.conversationFlow.last7Days') }}</option>
        </select>
        <button @click="runAnalysis" class="analyze-btn" :disabled="isLoading">
          <i :class="isLoading ? 'fas fa-spinner fa-spin' : 'chart-line'"></i>
          {{ isLoading ? $t('analytics.conversationFlow.analyzing') : $t('analytics.conversationFlow.analyze') }}
        </button>
      </div>
    </div>

    <!-- Metrics Cards -->
    <div class="metrics-grid" v-if="analysisResult?.metrics">
      <div class="metric-card">
        <div class="metric-icon conversations">
          <Icon name="comment" />
        </div>
        <div class="metric-content">
          <div class="metric-value">{{ analysisResult.metrics.total_conversations }}</div>
          <div class="metric-label">{{ $t('analytics.conversationFlow.totalConversations') }}</div>
        </div>
      </div>
      <div class="metric-card">
        <div class="metric-icon messages">
          <Icon name="envelope" />
        </div>
        <div class="metric-content">
          <div class="metric-value">{{ analysisResult.metrics.avg_messages_per_conversation }}</div>
          <div class="metric-label">{{ $t('analytics.conversationFlow.avgMessages') }}</div>
        </div>
      </div>
      <div class="metric-card">
        <div class="metric-icon satisfaction" :class="getSatisfactionClass(analysisResult.metrics.user_satisfaction_estimate)">
          <Icon name="user" />
        </div>
        <div class="metric-content">
          <div class="metric-value">{{ analysisResult.metrics.user_satisfaction_estimate }}%</div>
          <div class="metric-label">{{ $t('analytics.conversationFlow.satisfaction') }}</div>
        </div>
      </div>
      <div class="metric-card">
        <div class="metric-icon resolution">
          <Icon name="check-circle" />
        </div>
        <div class="metric-content">
          <div class="metric-value">{{ analysisResult.metrics.resolution_rate }}%</div>
          <div class="metric-label">{{ $t('analytics.conversationFlow.resolutionRate') }}</div>
        </div>
      </div>
    </div>

    <!-- Main Content -->
    <div class="content-grid" v-if="analysisResult">
      <!-- Intent Patterns -->
      <div class="panel intents-panel">
        <div class="panel-header">
          <h3><Icon name="bullseye" /> {{ $t('analytics.conversationFlow.userIntents') }}</h3>
          <span class="count-badge">{{ analysisResult.intent_patterns.length }} {{ $t('analytics.conversationFlow.detected') }}</span>
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
                <span><Icon name="check" /> {{ intent.success_rate }}% {{ $t('analytics.conversationFlow.success') }}</span>
                <span><Icon name="exchange-alt" /> {{ intent.avg_turns_to_resolve }} {{ $t('analytics.conversationFlow.turnsAvg') }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Common Flows -->
      <div class="panel flows-panel">
        <div class="panel-header">
          <h3><Icon name="sitemap" /> {{ $t('analytics.conversationFlow.commonFlowPaths') }}</h3>
        </div>
        <div class="panel-content">
          <div v-if="analysisResult.common_flows.length === 0" class="empty-state">
            <Icon name="sitemap" />
            <p>{{ $t('analytics.conversationFlow.notEnoughData') }}</p>
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
                  <Icon name="chevron-right" v-if="idx < flow.path.length - 1" />
                </span>
              </div>
              <div class="flow-stats">
                <span class="stat">
                  <Icon name="redo" /> {{ flow.frequency }}x
                </span>
                <span class="stat">
                  <Icon name="check-circle" /> {{ flow.completion_rate }}%
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Bottlenecks -->
      <div class="panel bottlenecks-panel">
        <div class="panel-header">
          <h3><Icon name="exclamation-triangle" /> {{ $t('analytics.conversationFlow.identifiedBottlenecks') }}</h3>
        </div>
        <div class="panel-content">
          <div v-if="analysisResult.bottlenecks.length === 0" class="empty-state success">
            <Icon name="check" />
            <p>{{ $t('analytics.conversationFlow.noBottlenecks') }}</p>
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
                <span class="suggestion-label">{{ $t('analytics.conversationFlow.suggestions') }}:</span>
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
          <h3><Icon name="clock" /> {{ $t('analytics.conversationFlow.activityDistribution') }}</h3>
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
    <BaseModal
      :model-value="!!selectedIntent"
      :title="selectedIntent?.intent_name ?? ''"
      size="sm"
      @close="selectedIntent = null"
    >
      <template v-if="selectedIntent">
          <div class="detail-grid">
            <div class="detail-item">
              <span class="label">{{ $t('analytics.conversationFlow.intentId') }}</span>
              <span class="value">{{ selectedIntent.intent_id }}</span>
            </div>
            <div class="detail-item">
              <span class="label">{{ $t('analytics.conversationFlow.totalOccurrences') }}</span>
              <span class="value">{{ selectedIntent.occurrences }}</span>
            </div>
            <div class="detail-item">
              <span class="label">{{ $t('analytics.conversationFlow.successRateLabel') }}</span>
              <span class="value" :class="getSuccessClass(selectedIntent.success_rate)">
                {{ selectedIntent.success_rate }}%
              </span>
            </div>
            <div class="detail-item">
              <span class="label">{{ $t('analytics.conversationFlow.avgTurnsToResolve') }}</span>
              <span class="value">{{ selectedIntent.avg_turns_to_resolve }}</span>
            </div>
          </div>
          <div v-if="selectedIntent.sample_queries?.length" class="samples-section">
            <h4>{{ $t('analytics.conversationFlow.sampleQueries') }}</h4>
            <div class="sample-list">
              <div v-for="(sample, idx) in selectedIntent.sample_queries" :key="idx" class="sample-item">
                {{ sample }}
              </div>
            </div>
          </div>
      </template>
    </BaseModal>

    <!-- Loading State -->
    <div v-if="isLoading && !analysisResult" class="loading-state">
      <Icon name="cog" class="animate-spin" />
      <p>{{ $t('analytics.conversationFlow.analyzingPatterns') }}</p>
    </div>

    <!-- Empty State -->
    <div v-if="!isLoading && !analysisResult" class="empty-state-full">
      <Icon name="comments" />
      <h3>{{ $t('analytics.conversationFlow.noData') }}</h3>
      <p>{{ $t('analytics.conversationFlow.noDataDescription') }}</p>
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
import Icon from '@/components/ui/Icon.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import { ref, onMounted, computed } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import {
  useConversationFlowData,
  type IntentPattern,
} from '@/composables/analytics/useConversationFlowData'

const logger = createLogger('ConversationFlowDashboard')

// State
const timeRange = ref(24)
const { isLoading, analysisResult, runAnalysis: fetchAnalysis } = useConversationFlowData()
const selectedIntent = ref<IntentPattern | null>(null)

// Computed
const maxHourlyCount = computed(() => {
  if (!analysisResult.value?.hourly_distribution) return 1
  return Math.max(...Object.values(analysisResult.value.hourly_distribution), 1)
})

// Methods
const runAnalysis = async () => {
  await fetchAnalysis(timeRange.value)
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
/* Issue #704: Migrated all hardcoded colors to design tokens */

.conversation-flow-dashboard {
  padding: var(--spacing-6);
  background: var(--bg-primary);
  min-height: 100%;
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
  margin: var(--spacing-0);
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
  background: var(--chart-cyan);
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
  margin: var(--spacing-0);
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
  gap: var(--spacing-1);
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
  background: var(--chart-cyan);
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
