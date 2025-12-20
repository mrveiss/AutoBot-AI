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
.enhanced-analytics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 20px;
  margin-bottom: 24px;
}

.card-header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.card-header-content h3 {
  margin: 0;
  color: #00d4ff;
  font-size: 1rem;
  display: flex;
  align-items: center;
  gap: 8px;
}

.refresh-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.5);
}

.refresh-indicator.active {
  color: #4caf50;
}

.refresh-indicator i {
  font-size: 8px;
}

.refresh-btn {
  background: transparent;
  border: none;
  color: rgba(255, 255, 255, 0.6);
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
  transition: all 0.2s;
}

.refresh-btn:hover {
  color: #00d4ff;
  background: rgba(0, 212, 255, 0.1);
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.metric-item,
.pattern-item {
  text-align: center;
}

.metric-label,
.pattern-label {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.5);
  margin-bottom: 4px;
}

.metric-value,
.pattern-value {
  font-size: 1.25rem;
  font-weight: 700;
  color: #00d4ff;
}

.health-good { color: #4caf50; }
.health-warning { color: #ff9800; }
.health-critical { color: #f44336; }

.communication-metrics {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.quality-metrics {
  display: flex;
  gap: 20px;
  align-items: flex-start;
}

.quality-score {
  text-align: center;
  padding: 12px 20px;
  border-radius: 8px;
}

.quality-excellent { background: rgba(76, 175, 80, 0.2); }
.quality-good { background: rgba(0, 212, 255, 0.2); }
.quality-fair { background: rgba(255, 152, 0, 0.2); }
.quality-poor { background: rgba(244, 67, 54, 0.2); }

.score-value {
  font-size: 2rem;
  font-weight: 700;
  color: white;
}

.score-label {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.6);
}

.quality-details,
.performance-details {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.quality-item,
.performance-item {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
}

.quality-label,
.performance-label {
  color: rgba(255, 255, 255, 0.6);
}

.quality-value,
.performance-value {
  color: white;
  font-weight: 600;
}

.performance-metrics {
  display: flex;
  gap: 20px;
  align-items: flex-start;
}

.performance-gauge {
  text-align: center;
  padding: 12px 20px;
  border-radius: 8px;
}

.efficiency-high { background: rgba(76, 175, 80, 0.2); }
.efficiency-medium { background: rgba(255, 152, 0, 0.2); }
.efficiency-low { background: rgba(244, 67, 54, 0.2); }

.gauge-value {
  font-size: 2rem;
  font-weight: 700;
  color: white;
}

.gauge-label {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.6);
}

.btn-link {
  background: transparent;
  border: 1px solid rgba(0, 212, 255, 0.3);
  color: #00d4ff;
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}

.btn-link:hover {
  background: rgba(0, 212, 255, 0.1);
}
</style>
