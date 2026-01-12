<template>
  <div class="enhanced-analytics-grid">
    <!-- System Overview -->
    <BasePanel variant="dark" size="medium">
      <template #header>
        <div class="card-header-content">
          <h3><i class="fas fa-tachometer-alt"></i> System Overview</h3>
          <div class="refresh-indicator" :class="{ active: realTimeEnabled }">
            <i class="fas fa-circle"></i>
            {{ realTimeEnabled ? 'Live' : 'Static' }}
          </div>
        </div>
      </template>
      <div v-if="systemOverview" class="metrics-grid">
        <div class="metric-item">
          <div class="metric-label">API Requests/Min</div>
          <div class="metric-value">{{ systemOverview.api_requests_per_minute || 0 }}</div>
        </div>
        <div class="metric-item">
          <div class="metric-label">Avg Response Time</div>
          <div class="metric-value">{{ systemOverview.average_response_time || 0 }}ms</div>
        </div>
        <div class="metric-item">
          <div class="metric-label">Active Connections</div>
          <div class="metric-value">{{ systemOverview.active_connections || 0 }}</div>
        </div>
        <div class="metric-item">
          <div class="metric-label">System Health</div>
          <div class="metric-value" :class="getHealthClass(systemOverview.system_health)">
            {{ systemOverview.system_health || 'Unknown' }}
          </div>
        </div>
      </div>
      <EmptyState
        v-else
        icon="fas fa-database"
        message="No system metrics available"
      >
        <template #actions>
          <button @click="$emit('load-system-overview')" class="btn-link">Load Metrics</button>
        </template>
      </EmptyState>
    </BasePanel>

    <!-- Communication Patterns -->
    <BasePanel variant="dark" size="medium">
      <template #header>
        <div class="card-header-content">
          <h3><i class="fas fa-network-wired"></i> Communication Patterns</h3>
          <button @click="$emit('load-communication-patterns')" class="refresh-btn">
            <i class="fas fa-sync"></i>
          </button>
        </div>
      </template>
      <div v-if="communicationPatterns" class="communication-metrics">
        <div class="pattern-item">
          <div class="pattern-label">WebSocket Connections</div>
          <div class="pattern-value">{{ communicationPatterns.websocket_connections || 0 }}</div>
        </div>
        <div class="pattern-item">
          <div class="pattern-label">API Call Frequency</div>
          <div class="pattern-value">{{ communicationPatterns.api_call_frequency || 0 }}/min</div>
        </div>
        <div class="pattern-item">
          <div class="pattern-label">Data Transfer Rate</div>
          <div class="pattern-value">{{ communicationPatterns.data_transfer_rate || 0 }} KB/s</div>
        </div>
      </div>
      <EmptyState
        v-else
        icon="fas fa-wifi"
        message="No communication data"
      />
    </BasePanel>

    <!-- Code Quality -->
    <BasePanel variant="dark" size="medium">
      <template #header>
        <div class="card-header-content">
          <h3><i class="fas fa-code-branch"></i> Code Quality</h3>
          <button @click="$emit('load-code-quality')" class="refresh-btn">
            <i class="fas fa-sync"></i>
          </button>
        </div>
      </template>
      <div v-if="codeQuality" class="quality-metrics">
        <div class="quality-score" :class="getQualityClass(codeQuality.overall_score)">
          <div class="score-value">{{ codeQuality.overall_score || 0 }}</div>
          <div class="score-label">Overall Score</div>
        </div>
        <div class="quality-details">
          <div class="quality-item">
            <span class="quality-label">Test Coverage:</span>
            <span class="quality-value">{{ codeQuality.test_coverage || 0 }}%</span>
          </div>
          <div class="quality-item">
            <span class="quality-label">Code Duplicates:</span>
            <span class="quality-value">{{ codeQuality.code_duplicates || 0 }}</span>
          </div>
          <div class="quality-item">
            <span class="quality-label">Technical Debt:</span>
            <span class="quality-value">{{ codeQuality.technical_debt || 0 }}h</span>
          </div>
        </div>
      </div>
      <EmptyState
        v-else
        icon="fas fa-star"
        message="No quality metrics"
      />
    </BasePanel>

    <!-- Performance Metrics -->
    <BasePanel variant="dark" size="medium">
      <template #header>
        <div class="card-header-content">
          <h3><i class="fas fa-bolt"></i> Performance Metrics</h3>
          <button @click="$emit('load-performance-metrics')" class="refresh-btn">
            <i class="fas fa-sync"></i>
          </button>
        </div>
      </template>
      <div v-if="performanceMetrics" class="performance-metrics">
        <div class="performance-gauge" :class="getEfficiencyClass(performanceMetrics.efficiency_score)">
          <div class="gauge-value">{{ performanceMetrics.efficiency_score || 0 }}%</div>
          <div class="gauge-label">Efficiency</div>
        </div>
        <div class="performance-details">
          <div class="performance-item">
            <span class="performance-label">Memory Usage:</span>
            <span class="performance-value">{{ performanceMetrics.memory_usage || 0 }}MB</span>
          </div>
          <div class="performance-item">
            <span class="performance-label">CPU Usage:</span>
            <span class="performance-value">{{ performanceMetrics.cpu_usage || 0 }}%</span>
          </div>
          <div class="performance-item">
            <span class="performance-label">Load Time:</span>
            <span class="performance-value">{{ performanceMetrics.load_time || 0 }}ms</span>
          </div>
        </div>
      </div>
      <EmptyState
        v-else
        icon="fas fa-rocket"
        message="No performance data"
      />
    </BasePanel>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Enhanced Analytics Grid Component
 *
 * Dashboard cards showing system overview, communication, quality, and performance.
 * Extracted from CodebaseAnalytics.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

import BasePanel from '@/components/base/BasePanel.vue'
import EmptyState from '@/components/ui/EmptyState.vue'

interface SystemOverview {
  api_requests_per_minute: number
  average_response_time: number
  active_connections: number
  system_health: string
}

interface CommunicationPatterns {
  websocket_connections: number
  api_call_frequency: number
  data_transfer_rate: number
}

interface CodeQuality {
  overall_score: number
  test_coverage: number
  code_duplicates: number
  technical_debt: number
}

interface PerformanceMetrics {
  efficiency_score: number
  memory_usage: number
  cpu_usage: number
  load_time: number
}

interface Props {
  systemOverview: SystemOverview | null
  communicationPatterns: CommunicationPatterns | null
  codeQuality: CodeQuality | null
  performanceMetrics: PerformanceMetrics | null
  realTimeEnabled: boolean
}

interface Emits {
  (e: 'load-system-overview'): void
  (e: 'load-communication-patterns'): void
  (e: 'load-code-quality'): void
  (e: 'load-performance-metrics'): void
}

defineProps<Props>()
defineEmits<Emits>()

const getHealthClass = (health: string): string => {
  if (!health) return ''
  const h = health.toLowerCase()
  if (h === 'healthy' || h === 'good') return 'health-good'
  if (h === 'warning' || h === 'degraded') return 'health-warning'
  return 'health-critical'
}

const getQualityClass = (score: number): string => {
  if (score >= 80) return 'quality-excellent'
  if (score >= 60) return 'quality-good'
  if (score >= 40) return 'quality-fair'
  return 'quality-poor'
}

const getEfficiencyClass = (score: number): string => {
  if (score >= 80) return 'efficiency-high'
  if (score >= 50) return 'efficiency-medium'
  return 'efficiency-low'
}
</script>

<style scoped>
/** Issue #704: Migrated to design tokens */
.enhanced-analytics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--spacing-5);
  margin-bottom: var(--spacing-6);
}

.card-header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.card-header-content h3 {
  margin: 0;
  color: var(--color-info);
  font-size: var(--text-base);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.refresh-indicator {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.refresh-indicator.active {
  color: var(--color-success);
}

.refresh-indicator i {
  font-size: 8px;
}

.refresh-btn {
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-default);
  transition: all var(--duration-200);
}

.refresh-btn:hover {
  color: var(--color-info);
  background: var(--color-info-bg);
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--spacing-4);
}

.metric-item,
.pattern-item {
  text-align: center;
}

.metric-label,
.pattern-label {
  font-size: var(--text-xs);
  color: var(--text-muted);
  margin-bottom: var(--spacing-1);
}

.metric-value,
.pattern-value {
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
  color: var(--color-info);
}

.health-good { color: var(--color-success); }
.health-warning { color: var(--color-warning); }
.health-critical { color: var(--color-error); }

.communication-metrics {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.quality-metrics {
  display: flex;
  gap: var(--spacing-5);
  align-items: flex-start;
}

.quality-score {
  text-align: center;
  padding: var(--spacing-3) var(--spacing-5);
  border-radius: var(--radius-lg);
}

.quality-excellent { background: var(--color-success-bg); }
.quality-good { background: var(--color-info-bg); }
.quality-fair { background: var(--color-warning-bg); }
.quality-poor { background: var(--color-error-bg); }

.score-value {
  font-size: var(--text-3xl);
  font-weight: var(--font-bold);
  color: var(--text-on-primary);
}

.score-label {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.quality-details,
.performance-details {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.quality-item,
.performance-item {
  display: flex;
  justify-content: space-between;
  font-size: var(--text-sm);
}

.quality-label,
.performance-label {
  color: var(--text-muted);
}

.quality-value,
.performance-value {
  color: var(--text-on-primary);
  font-weight: var(--font-semibold);
}

.performance-metrics {
  display: flex;
  gap: var(--spacing-5);
  align-items: flex-start;
}

.performance-gauge {
  text-align: center;
  padding: var(--spacing-3) var(--spacing-5);
  border-radius: var(--radius-lg);
}

.efficiency-high { background: var(--color-success-bg); }
.efficiency-medium { background: var(--color-warning-bg); }
.efficiency-low { background: var(--color-error-bg); }

.gauge-value {
  font-size: var(--text-3xl);
  font-weight: var(--font-bold);
  color: var(--text-on-primary);
}

.gauge-label {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.btn-link {
  background: transparent;
  border: 1px solid var(--color-info-border);
  color: var(--color-info);
  padding: var(--spacing-1-5) var(--spacing-3);
  border-radius: var(--radius-default);
  cursor: pointer;
  font-size: var(--text-xs);
}

.btn-link:hover {
  background: var(--color-info-bg);
}
</style>
