<template>
  <div class="bi-view">
    <!-- Health Overview Cards -->
    <div class="health-overview" v-if="dashboard">
      <div class="health-card" :class="dashboard.health?.status">
        <div class="health-score">{{ dashboard.health?.score || 0 }}</div>
        <div class="health-label">Health Score</div>
        <div class="health-grade">Grade: {{ dashboard.health?.grade || 'N/A' }}</div>
      </div>

      <div class="overview-cards">
        <div class="overview-card">
          <i class="fas fa-dollar-sign"></i>
          <div class="card-content">
            <div class="card-value">${{ (dashboard.cost?.total_usd || 0).toFixed(2) }}</div>
            <div class="card-label">Total Cost (30d)</div>
            <div class="card-trend" :class="getTrendClass(dashboard.cost?.trend)">
              <i :class="getTrendIcon(dashboard.cost?.trend)"></i>
              {{ (dashboard.cost?.growth_rate || 0).toFixed(1) }}%
            </div>
          </div>
        </div>

        <div class="overview-card">
          <i class="fas fa-robot"></i>
          <div class="card-content">
            <div class="card-value">{{ dashboard.agents?.total_agents || 0 }}</div>
            <div class="card-label">Active Agents</div>
            <div class="card-meta">{{ formatNumber(dashboard.agents?.total_tasks || 0) }} tasks</div>
          </div>
        </div>

        <div class="overview-card">
          <i class="fas fa-check-circle"></i>
          <div class="card-content">
            <div class="card-value">{{ (dashboard.agents?.avg_success_rate || 0).toFixed(1) }}%</div>
            <div class="card-label">Avg Success Rate</div>
          </div>
        </div>

        <div class="overview-card">
          <i class="fas fa-users"></i>
          <div class="card-content">
            <div class="card-value">{{ formatNumber(dashboard.engagement?.total_sessions || 0) }}</div>
            <div class="card-label">Total Sessions</div>
            <div class="card-meta">{{ formatNumber(dashboard.engagement?.page_views || 0) }} views</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Refresh Button -->
    <div class="actions-bar">
      <BaseButton variant="secondary" size="sm" @click="refreshAll" :loading="loading">
        <i class="fas fa-sync"></i> Refresh All
      </BaseButton>
    </div>

    <!-- Main Content Tabs -->
    <div class="bi-content">
      <div class="tab-nav">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          :class="['tab-btn', { active: activeTab === tab.id }]"
          @click="activeTab = tab.id"
        >
          <i :class="tab.icon"></i>
          {{ tab.label }}
          <span v-if="tab.badge" class="tab-badge" :class="tab.badgeClass">{{ tab.badge }}</span>
        </button>
      </div>

      <!-- Advanced Analytics Component -->
      <div v-if="activeTab === 'analytics'" class="tab-panel">
        <AdvancedAnalytics />
      </div>

      <!-- Predictive Maintenance -->
      <div v-if="activeTab === 'maintenance'" class="tab-panel">
        <div class="maintenance-section">
          <div class="section-header">
            <h3><i class="fas fa-tools"></i> Predictive Maintenance</h3>
            <BaseButton variant="outline" size="sm" @click="fetchMaintenance">
              <i class="fas fa-refresh"></i> Refresh
            </BaseButton>
          </div>

          <div class="priority-summary" v-if="maintenance">
            <div class="priority-card critical" v-if="maintenance.by_priority?.critical > 0">
              <span class="count">{{ maintenance.by_priority.critical }}</span>
              <span class="label">Critical</span>
            </div>
            <div class="priority-card high" v-if="maintenance.by_priority?.high > 0">
              <span class="count">{{ maintenance.by_priority.high }}</span>
              <span class="label">High</span>
            </div>
            <div class="priority-card medium">
              <span class="count">{{ maintenance.by_priority?.medium || 0 }}</span>
              <span class="label">Medium</span>
            </div>
            <div class="priority-card low">
              <span class="count">{{ maintenance.by_priority?.low || 0 }}</span>
              <span class="label">Low</span>
            </div>
          </div>

          <div class="recommendations-list" v-if="maintenance?.recommendations?.length">
            <div
              v-for="rec in maintenance.recommendations"
              :key="rec.id"
              class="recommendation-card"
              :class="'priority-' + rec.priority"
            >
              <div class="rec-header">
                <span class="priority-badge" :class="rec.priority">{{ rec.priority }}</span>
                <span class="category">{{ rec.category }}</span>
              </div>
              <h4>{{ rec.title }}</h4>
              <p class="description">{{ rec.description }}</p>
              <div class="rec-details">
                <div class="detail">
                  <i class="fas fa-cog"></i>
                  <span>{{ rec.affected_component }}</span>
                </div>
                <div class="detail">
                  <i class="fas fa-exclamation-triangle"></i>
                  <span>{{ rec.predicted_issue }}</span>
                </div>
                <div class="detail confidence">
                  <i class="fas fa-chart-pie"></i>
                  <span>{{ (rec.confidence * 100).toFixed(0) }}% confidence</span>
                </div>
              </div>
              <div class="rec-action">
                <i class="fas fa-lightbulb"></i>
                <span>{{ rec.recommended_action }}</span>
              </div>
            </div>
          </div>
          <EmptyState
            v-else
            icon="fas fa-check-circle"
            message="No maintenance recommendations at this time"
          />
        </div>
      </div>

      <!-- Resource Optimization -->
      <div v-if="activeTab === 'optimization'" class="tab-panel">
        <div class="optimization-section">
          <div class="section-header">
            <h3><i class="fas fa-rocket"></i> Resource Optimization</h3>
            <BaseButton variant="outline" size="sm" @click="fetchOptimization">
              <i class="fas fa-refresh"></i> Refresh
            </BaseButton>
          </div>

          <div class="savings-summary" v-if="optimization">
            <div class="savings-card">
              <i class="fas fa-dollar-sign"></i>
              <div class="savings-content">
                <div class="savings-value">${{ (optimization.potential_savings?.cost_usd || 0).toFixed(2) }}</div>
                <div class="savings-label">Potential Cost Savings</div>
              </div>
            </div>
            <div class="savings-card">
              <i class="fas fa-tachometer-alt"></i>
              <div class="savings-content">
                <div class="savings-value">{{ (optimization.potential_savings?.performance_improvement_percent || 0).toFixed(1) }}%</div>
                <div class="savings-label">Performance Improvement</div>
              </div>
            </div>
          </div>

          <div class="optimizations-list" v-if="optimization?.recommendations?.length">
            <div
              v-for="opt in optimization.recommendations"
              :key="opt.id"
              class="optimization-card"
            >
              <div class="opt-header">
                <span class="resource-type" :class="opt.resource_type">{{ opt.resource_type }}</span>
                <span class="effort-badge" :class="opt.implementation_effort">{{ opt.implementation_effort }} effort</span>
              </div>
              <h4>{{ opt.title }}</h4>
              <p class="details">{{ opt.details }}</p>
              <div class="opt-metrics">
                <div class="metric" v-if="opt.expected_savings?.cost_usd">
                  <i class="fas fa-piggy-bank"></i>
                  <span>Save ${{ opt.expected_savings.cost_usd.toFixed(2) }}</span>
                </div>
                <div class="metric" v-if="opt.expected_savings?.performance_percent">
                  <i class="fas fa-bolt"></i>
                  <span>{{ opt.expected_savings.performance_percent }}% faster</span>
                </div>
              </div>
              <div class="opt-action">
                <i class="fas fa-arrow-right"></i>
                <span>{{ opt.recommended_change }}</span>
              </div>
            </div>
          </div>
          <EmptyState
            v-else
            icon="fas fa-check-circle"
            message="No optimization recommendations at this time"
          />
        </div>
      </div>

      <!-- Insights -->
      <div v-if="activeTab === 'insights'" class="tab-panel">
        <div class="insights-section">
          <div class="section-header">
            <h3><i class="fas fa-lightbulb"></i> Actionable Insights</h3>
            <BaseButton variant="outline" size="sm" @click="fetchInsights">
              <i class="fas fa-refresh"></i> Refresh
            </BaseButton>
          </div>

          <div class="insights-list" v-if="insights?.insights?.length">
            <div
              v-for="(insight, idx) in insights.insights"
              :key="idx"
              class="insight-card"
              :class="'priority-' + insight.priority"
            >
              <div class="insight-header">
                <span class="insight-type" :class="insight.type">{{ insight.type }}</span>
                <span class="priority-badge" :class="insight.priority">{{ insight.priority }}</span>
              </div>
              <h4>{{ insight.title }}</h4>
              <div class="insight-action">
                <i class="fas fa-play"></i>
                <span>{{ insight.action }}</span>
              </div>
              <div class="insight-impact">
                <i class="fas fa-chart-line"></i>
                <span>{{ insight.impact }}</span>
              </div>
            </div>
          </div>
          <EmptyState
            v-else
            icon="fas fa-sparkles"
            message="No insights available at this time"
          />
        </div>
      </div>

      <!-- Reports -->
      <div v-if="activeTab === 'reports'" class="tab-panel">
        <div class="reports-section">
          <div class="section-header">
            <h3><i class="fas fa-file-alt"></i> Custom Reports</h3>
          </div>

          <div class="report-options">
            <div class="report-card" @click="generateReport('executive')">
              <i class="fas fa-briefcase"></i>
              <h4>Executive Summary</h4>
              <p>High-level overview with key metrics and recommendations</p>
            </div>
            <div class="report-card" @click="generateReport('technical')">
              <i class="fas fa-cogs"></i>
              <h4>Technical Report</h4>
              <p>Detailed technical analysis and system metrics</p>
            </div>
            <div class="report-card" @click="generateReport('cost')">
              <i class="fas fa-dollar-sign"></i>
              <h4>Cost Report</h4>
              <p>Cost breakdown, trends, and optimization opportunities</p>
            </div>
            <div class="report-card" @click="generateReport('performance')">
              <i class="fas fa-tachometer-alt"></i>
              <h4>Performance Report</h4>
              <p>Agent and system performance metrics</p>
            </div>
          </div>

          <div class="generated-report" v-if="generatedReport">
            <div class="report-header">
              <h4>{{ generatedReport.report_type }} Report</h4>
              <span class="report-date">{{ formatDate(generatedReport.generated_at) }}</span>
            </div>
            <pre class="report-content">{{ JSON.stringify(generatedReport, null, 2) }}</pre>
            <BaseButton variant="primary" size="sm" @click="downloadReport">
              <i class="fas fa-download"></i> Download JSON
            </BaseButton>
          </div>
        </div>
      </div>
    </div>

    <!-- Loading Overlay -->
    <div v-if="loading" class="loading-overlay">
      <i class="fas fa-spinner fa-spin fa-2x"></i>
      <span>Loading analytics data...</span>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, computed, onMounted } from 'vue'
import BaseButton from '@/components/base/BaseButton.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import AdvancedAnalytics from '@/components/analytics/AdvancedAnalytics.vue'
import api from '@/services/api'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('BusinessIntelligenceView')

// State
const loading = ref(false)
const activeTab = ref('analytics')
const dashboard = ref<any>(null)
const maintenance = ref<any>(null)
const optimization = ref<any>(null)
const insights = ref<any>(null)
const generatedReport = ref<any>(null)

// Tab configuration with badges
const tabs = computed(() => [
  { id: 'analytics', label: 'Analytics', icon: 'fas fa-chart-pie' },
  {
    id: 'maintenance',
    label: 'Maintenance',
    icon: 'fas fa-tools',
    badge: maintenance.value?.by_priority?.critical || 0,
    badgeClass: maintenance.value?.by_priority?.critical > 0 ? 'critical' : ''
  },
  {
    id: 'optimization',
    label: 'Optimization',
    icon: 'fas fa-rocket',
    badge: optimization.value?.total_recommendations || 0,
    badgeClass: ''
  },
  { id: 'insights', label: 'Insights', icon: 'fas fa-lightbulb' },
  { id: 'reports', label: 'Reports', icon: 'fas fa-file-alt' }
])

// Methods
const formatNumber = (num: number): string => {
  if (!num) return '0'
  return num.toLocaleString()
}

const formatDate = (dateStr: string): string => {
  return new Date(dateStr).toLocaleString()
}

const getTrendClass = (trend: string): string => {
  if (trend === 'increasing') return 'trend-up'
  if (trend === 'decreasing') return 'trend-down'
  return 'trend-stable'
}

const getTrendIcon = (trend: string): string => {
  if (trend === 'increasing') return 'fas fa-arrow-up'
  if (trend === 'decreasing') return 'fas fa-arrow-down'
  return 'fas fa-minus'
}

const fetchDashboard = async () => {
  try {
    // Issue #552: Fixed path - backend uses /api/advanced/* not /api/analytics/advanced/*
    const res = await api.get<{ data: any }>('/api/advanced/dashboard')
    dashboard.value = res.data
  } catch (error) {
    logger.error('Failed to fetch dashboard:', error)
  }
}

const fetchMaintenance = async () => {
  try {
    // Issue #552: Fixed path - backend uses /api/advanced/* not /api/analytics/advanced/*
    const res = await api.get<{ data: any }>('/api/advanced/maintenance')
    maintenance.value = res.data
  } catch (error) {
    logger.error('Failed to fetch maintenance:', error)
  }
}

const fetchOptimization = async () => {
  try {
    // Issue #552: Fixed path - backend uses /api/advanced/* not /api/analytics/advanced/*
    const res = await api.get<{ data: any }>('/api/advanced/optimization')
    optimization.value = res.data
  } catch (error) {
    logger.error('Failed to fetch optimization:', error)
  }
}

const fetchInsights = async () => {
  try {
    // Issue #552: Fixed path - backend uses /api/advanced/* not /api/analytics/advanced/*
    const res = await api.get<{ data: any }>('/api/advanced/insights')
    insights.value = res.data
  } catch (error) {
    logger.error('Failed to fetch insights:', error)
  }
}

const generateReport = async (reportType: string) => {
  try {
    loading.value = true
    // Issue #552: Fixed path - backend uses /api/advanced/* not /api/analytics/advanced/*
    const res = await api.post<{ data: any }>('/api/advanced/report', {
      report_type: reportType,
      days: 30
    })
    generatedReport.value = res.data
  } catch (error) {
    logger.error('Failed to generate report:', error)
  } finally {
    loading.value = false
  }
}

const downloadReport = () => {
  if (!generatedReport.value) return
  const blob = new Blob([JSON.stringify(generatedReport.value, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `autobot_${generatedReport.value.report_type}_report.json`
  a.click()
  URL.revokeObjectURL(url)
}

const refreshAll = async () => {
  loading.value = true
  try {
    await Promise.all([
      fetchDashboard(),
      fetchMaintenance(),
      fetchOptimization(),
      fetchInsights()
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
.bi-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: var(--spacing-4);
  background: var(--bg-primary);
  overflow-y: auto;
}

/* Actions Bar */
.actions-bar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: var(--spacing-4);
}

/* Health Overview */
.health-overview {
  display: flex;
  gap: var(--spacing-5);
  margin-bottom: var(--spacing-5);
}

.health-card {
  background: var(--color-primary);
  border-radius: var(--radius-lg);
  padding: var(--spacing-5);
  color: white;
  min-width: 150px;
  text-align: center;
}

.health-card.healthy { background: var(--color-success); }
.health-card.warning { background: var(--color-warning); }
.health-card.critical { background: var(--color-error); }

.health-score {
  font-size: var(--text-5xl);
  font-weight: var(--font-bold);
  line-height: var(--leading-none);
}

.health-label {
  font-size: var(--text-sm);
  opacity: 0.9;
  margin-top: var(--spacing-1);
}

.health-grade {
  font-size: var(--text-xs);
  opacity: 0.8;
  margin-top: var(--spacing-2);
}

.overview-cards {
  display: flex;
  gap: var(--spacing-4);
  flex: 1;
}

.overview-card {
  flex: 1;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: var(--spacing-4);
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
}

.overview-card > i {
  font-size: var(--text-xl);
  color: var(--color-primary);
  opacity: 0.8;
}

.card-value {
  font-size: var(--text-xl);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.card-label {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.card-trend {
  font-size: var(--text-xs);
  margin-top: var(--spacing-1);
}

.card-trend.trend-up { color: var(--color-error); }
.card-trend.trend-down { color: var(--color-success); }
.card-trend.trend-stable { color: var(--text-secondary); }

.card-meta {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

/* Tab badge (extends global .tab-btn) */
.tab-badge {
  background: var(--bg-tertiary);
  padding: var(--spacing-0) var(--spacing-2);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
}

.tab-btn.active .tab-badge {
  background: rgba(255, 255, 255, 0.2);
}

.tab-badge.critical {
  background: var(--color-error);
  color: white;
}

/* Tab panel */
.tab-panel {
  flex: 1;
}

/* Section Headers */
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-4);
}

.section-header h3 {
  margin: 0;
  color: var(--text-primary);
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
}

.section-header h3 i {
  margin-right: var(--spacing-2);
  color: var(--color-primary);
}

/* Priority Summary */
.priority-summary {
  display: flex;
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-5);
}

.priority-card {
  padding: var(--spacing-4) var(--spacing-5);
  border-radius: var(--radius-md);
  text-align: center;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
}

.priority-card .count {
  font-size: var(--text-xl);
  font-weight: var(--font-semibold);
}

.priority-card .label {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.priority-card.critical {
  background: var(--color-error-bg);
  border-color: var(--color-error);
}

.priority-card.critical .count { color: var(--color-error); }

.priority-card.high {
  background: var(--color-warning-bg);
  border-color: var(--color-warning);
}

.priority-card.high .count { color: var(--color-warning); }

/* Recommendation/Optimization/Insight Cards */
.recommendations-list,
.optimizations-list,
.insights-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

.recommendation-card,
.optimization-card,
.insight-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: var(--spacing-4);
}

.recommendation-card.priority-critical { border-left: 4px solid var(--color-error); }
.recommendation-card.priority-high { border-left: 4px solid var(--color-warning); }
.recommendation-card.priority-medium { border-left: 4px solid var(--color-info); }

.rec-header,
.opt-header,
.insight-header {
  display: flex;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-2);
}

.priority-badge,
.resource-type,
.effort-badge,
.insight-type {
  padding: var(--spacing-0) var(--spacing-2);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  text-transform: uppercase;
  font-weight: var(--font-semibold);
}

.priority-badge.critical { background: var(--color-error); color: white; }
.priority-badge.high { background: var(--color-warning); color: white; }
.priority-badge.medium { background: var(--color-info); color: white; }
.priority-badge.low { background: var(--bg-tertiary); color: var(--text-secondary); }

.category {
  color: var(--text-secondary);
  font-size: var(--text-xs);
}

.recommendation-card h4,
.optimization-card h4,
.insight-card h4 {
  margin: 0 0 var(--spacing-2);
  color: var(--text-primary);
}

.description,
.details {
  color: var(--text-secondary);
  font-size: var(--text-sm);
  margin-bottom: var(--spacing-3);
}

.rec-details {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-3);
}

.detail {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.detail i { color: var(--color-primary); }
.detail.confidence { color: var(--color-success); }

.rec-action,
.opt-action,
.insight-action {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2);
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
}

.rec-action i,
.opt-action i,
.insight-action i {
  color: var(--color-success);
}

/* Optimization specific */
.savings-summary {
  display: flex;
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-5);
}

.savings-card {
  flex: 1;
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  padding: var(--spacing-4);
  background: var(--color-success);
  border-radius: var(--radius-md);
  color: white;
}

.savings-card > i {
  font-size: var(--text-3xl);
  opacity: 0.8;
}

.savings-value {
  font-size: var(--text-xl);
  font-weight: var(--font-semibold);
}

.savings-label {
  font-size: var(--text-xs);
  opacity: 0.9;
}

.opt-metrics {
  display: flex;
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-3);
}

.metric {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  color: var(--color-success);
  font-size: var(--text-sm);
}

.resource-type.llm_tokens { background: var(--color-primary); color: white; }
.resource-type.agent_tasks { background: var(--color-info); color: white; }
.resource-type.cache { background: var(--color-success); color: white; }

.effort-badge.low { background: var(--color-success); color: white; }
.effort-badge.medium { background: var(--color-warning); color: white; }
.effort-badge.high { background: var(--color-error); color: white; }

/* Insights specific */
.insight-type.maintenance { background: var(--color-warning); color: white; }
.insight-type.optimization { background: var(--color-success); color: white; }

.insight-impact {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  margin-top: var(--spacing-2);
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.insight-impact i { color: var(--color-info); }

/* Reports */
.report-options {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-5);
}

.report-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: var(--spacing-5);
  cursor: pointer;
  transition: border-color var(--duration-200) var(--ease-in-out),
              transform var(--duration-200) var(--ease-in-out);
}

.report-card:hover {
  border-color: var(--color-primary);
  transform: translateY(-2px);
}

.report-card > i {
  font-size: var(--text-3xl);
  color: var(--color-primary);
  margin-bottom: var(--spacing-3);
  display: block;
}

.report-card h4 {
  margin: 0 0 var(--spacing-2);
  color: var(--text-primary);
}

.report-card p {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.generated-report {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: var(--spacing-4);
}

.report-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-4);
}

.report-header h4 {
  margin: 0;
  text-transform: capitalize;
  color: var(--text-primary);
}

.report-date {
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.report-content {
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
  padding: var(--spacing-4);
  font-size: var(--text-xs);
  font-family: var(--font-mono);
  max-height: 400px;
  overflow: auto;
  margin-bottom: var(--spacing-4);
  color: var(--text-primary);
}

/* Loading Overlay */
.loading-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-4);
  color: white;
  z-index: var(--z-modal);
}

/* Responsive */
@media (max-width: 1024px) {
  .health-overview { flex-direction: column; }
  .overview-cards { flex-wrap: wrap; }
  .overview-card { min-width: calc(50% - var(--spacing-2)); }
}

@media (max-width: 768px) {
  .overview-card { min-width: 100%; }
}
</style>
