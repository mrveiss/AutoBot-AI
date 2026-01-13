<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  HealthTimeline.vue - Historical Health Data Timeline
  Displays health history with visual timeline (Issue #581)
-->
<template>
  <BasePanel variant="bordered" size="medium">
    <template #header>
      <div class="panel-header-content">
        <h2><i class="fas fa-history"></i> Health Timeline</h2>
        <span class="entry-count" v-if="history.length">{{ history.length }} entries</span>
      </div>
    </template>

    <div v-if="loading" class="loading-state">
      <i class="fas fa-spinner fa-spin"></i>
      <span>Loading health history...</span>
    </div>

    <div v-else-if="history.length === 0" class="empty-state">
      <i class="fas fa-clock"></i>
      <span>No health history available</span>
      <p>Run a validation test to start tracking health</p>
    </div>

    <div v-else class="timeline-container">
      <!-- Mini Chart -->
      <div class="mini-chart">
        <div class="chart-header">
          <span class="chart-title">Health Score Trend</span>
          <span class="chart-range">Last {{ history.length }} checks</span>
        </div>
        <div class="chart-body">
          <svg
            :viewBox="`0 0 ${chartWidth} ${chartHeight}`"
            class="trend-svg"
            preserveAspectRatio="none"
          >
            <!-- Grid Lines -->
            <line
              v-for="i in 4"
              :key="`grid-${i}`"
              :x1="0"
              :y1="(chartHeight / 4) * i"
              :x2="chartWidth"
              :y2="(chartHeight / 4) * i"
              class="grid-line"
            />
            <!-- Area Fill -->
            <path
              :d="areaPath"
              class="trend-area"
            />
            <!-- Line -->
            <path
              :d="linePath"
              class="trend-line"
            />
            <!-- Points -->
            <circle
              v-for="(point, index) in chartPoints"
              :key="`point-${index}`"
              :cx="point.x"
              :cy="point.y"
              r="3"
              :class="['trend-point', getScoreClass(history[index]?.score || 0)]"
            />
          </svg>
          <!-- Y-axis labels -->
          <div class="y-axis-labels">
            <span>100%</span>
            <span>75%</span>
            <span>50%</span>
            <span>25%</span>
            <span>0%</span>
          </div>
        </div>
      </div>

      <!-- Timeline List -->
      <div class="timeline-list">
        <div
          v-for="(entry, index) in history"
          :key="entry.timestamp"
          :class="['timeline-entry', getScoreClass(entry.score)]"
        >
          <div class="entry-marker">
            <div class="marker-dot"></div>
            <div class="marker-line" v-if="index < history.length - 1"></div>
          </div>
          <div class="entry-content">
            <div class="entry-header">
              <span class="entry-time">{{ formatTimestamp(entry.timestamp) }}</span>
              <span :class="['entry-score', getScoreClass(entry.score)]">
                {{ entry.score.toFixed(1) }}%
              </span>
            </div>
            <div class="entry-status">
              <i :class="getStatusIcon(entry.status)"></i>
              {{ formatStatus(entry.status) }}
            </div>
            <div class="entry-components" v-if="Object.keys(entry.componentScores || {}).length > 0">
              <span
                v-for="(score, name) in entry.componentScores"
                :key="String(name)"
                :class="['component-chip', getScoreClass(score)]"
                :title="`${formatComponentName(String(name))}: ${score}%`"
              >
                {{ formatComponentName(String(name)).substring(0, 3) }}: {{ Math.round(score) }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </BasePanel>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { computed } from 'vue'
import BasePanel from '@/components/base/BasePanel.vue'

interface HealthHistoryEntry {
  timestamp: string
  score: number
  status: string
  componentScores: Record<string, number>
}

interface Props {
  history: HealthHistoryEntry[]
  loading?: boolean
}

const props = defineProps<Props>()

// Chart dimensions
const chartWidth = 300
const chartHeight = 100
const padding = 10

// Computed chart points
const chartPoints = computed(() => {
  if (props.history.length === 0) return []

  const entries = [...props.history].reverse() // Oldest first for chart
  const xStep = (chartWidth - padding * 2) / Math.max(entries.length - 1, 1)

  return entries.map((entry, index) => ({
    x: padding + index * xStep,
    y: chartHeight - padding - ((entry.score / 100) * (chartHeight - padding * 2))
  }))
})

// Computed line path
const linePath = computed(() => {
  if (chartPoints.value.length === 0) return ''
  return chartPoints.value
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`)
    .join(' ')
})

// Computed area path (for fill under line)
const areaPath = computed(() => {
  if (chartPoints.value.length === 0) return ''
  const points = chartPoints.value
  const firstPoint = points[0]
  const lastPoint = points[points.length - 1]

  return [
    `M ${firstPoint.x} ${chartHeight - padding}`,
    `L ${firstPoint.x} ${firstPoint.y}`,
    ...points.slice(1).map(p => `L ${p.x} ${p.y}`),
    `L ${lastPoint.x} ${chartHeight - padding}`,
    'Z'
  ].join(' ')
})

// Helper functions
const getScoreClass = (score: number): string => {
  if (score >= 90) return 'excellent'
  if (score >= 70) return 'good'
  if (score >= 50) return 'warning'
  if (score >= 30) return 'degraded'
  return 'critical'
}

const getStatusIcon = (status: string): string => {
  const iconMap: Record<string, string> = {
    healthy: 'fas fa-check-circle',
    excellent: 'fas fa-star',
    warning: 'fas fa-exclamation-triangle',
    degraded: 'fas fa-exclamation-circle',
    critical: 'fas fa-times-circle',
    unhealthy: 'fas fa-times-circle'
  }
  return iconMap[status?.toLowerCase()] || 'fas fa-circle'
}

const formatStatus = (status: string): string => {
  if (!status) return 'Unknown'
  return status.charAt(0).toUpperCase() + status.slice(1)
}

const formatTimestamp = (timestamp: string): string => {
  if (!timestamp) return 'N/A'
  try {
    const date = new Date(timestamp)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)

    if (diffMins < 1) return 'Just now'
    if (diffMins < 60) return `${diffMins}m ago`
    if (diffMins < 1440) return `${Math.floor(diffMins / 60)}h ago`
    return date.toLocaleDateString()
  } catch {
    return timestamp
  }
}

const formatComponentName = (name: string): string => {
  return name
    .replace(/_/g, ' ')
    .replace(/\b\w/g, l => l.toUpperCase())
}
</script>

<style scoped>
.panel-header-content {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  width: 100%;
}

.panel-header-content h2 {
  margin: 0;
  font-size: var(--text-lg);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.panel-header-content h2 i {
  color: var(--color-primary);
}

.entry-count {
  margin-left: auto;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  font-weight: var(--font-normal);
}

/* Loading & Empty States */
.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
  padding: var(--spacing-8);
  color: var(--text-tertiary);
  text-align: center;
}

.loading-state i,
.empty-state i {
  font-size: var(--text-2xl);
}

.empty-state p {
  margin: 0;
  font-size: var(--text-sm);
}

/* Timeline Container */
.timeline-container {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

/* Mini Chart */
.mini-chart {
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  padding: var(--spacing-3);
}

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-2);
}

.chart-title {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.chart-range {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.chart-body {
  position: relative;
  height: 100px;
}

.trend-svg {
  width: 100%;
  height: 100%;
}

.grid-line {
  stroke: var(--border-default);
  stroke-width: 1;
  stroke-dasharray: 4 4;
}

.trend-area {
  fill: rgba(59, 130, 246, 0.1);
}

.trend-line {
  fill: none;
  stroke: var(--color-primary);
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.trend-point {
  fill: var(--color-primary);
  stroke: var(--bg-surface);
  stroke-width: 2;
}

.trend-point.excellent {
  fill: var(--color-success);
}

.trend-point.good {
  fill: var(--color-success-light);
}

.trend-point.warning {
  fill: var(--color-warning);
}

.trend-point.degraded {
  fill: var(--chart-orange);
}

.trend-point.critical {
  fill: var(--color-error);
}

.y-axis-labels {
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  padding: var(--spacing-1) 0;
}

/* Timeline List */
.timeline-list {
  display: flex;
  flex-direction: column;
  max-height: 300px;
  overflow-y: auto;
}

/* Timeline Entry */
.timeline-entry {
  display: flex;
  gap: var(--spacing-3);
  padding: var(--spacing-2) 0;
}

/* Entry Marker */
.entry-marker {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 20px;
  flex-shrink: 0;
}

.marker-dot {
  width: 12px;
  height: 12px;
  border-radius: var(--radius-full);
  background: var(--color-primary);
  border: 2px solid var(--bg-surface);
  box-shadow: 0 0 0 2px var(--color-primary);
  flex-shrink: 0;
}

.timeline-entry.excellent .marker-dot {
  background: var(--color-success);
  box-shadow: 0 0 0 2px var(--color-success);
}

.timeline-entry.good .marker-dot {
  background: var(--color-success-light);
  box-shadow: 0 0 0 2px var(--color-success-light);
}

.timeline-entry.warning .marker-dot {
  background: var(--color-warning);
  box-shadow: 0 0 0 2px var(--color-warning);
}

.timeline-entry.degraded .marker-dot {
  background: var(--chart-orange);
  box-shadow: 0 0 0 2px var(--chart-orange);
}

.timeline-entry.critical .marker-dot {
  background: var(--color-error);
  box-shadow: 0 0 0 2px var(--color-error);
}

.marker-line {
  width: 2px;
  flex: 1;
  background: var(--border-default);
  margin-top: var(--spacing-1);
}

/* Entry Content */
.entry-content {
  flex: 1;
  padding-bottom: var(--spacing-3);
  border-bottom: 1px solid var(--border-default);
}

.timeline-entry:last-child .entry-content {
  border-bottom: none;
}

.entry-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-1);
}

.entry-time {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.entry-score {
  font-size: var(--text-sm);
  font-weight: var(--font-bold);
}

.entry-score.excellent {
  color: var(--color-success);
}

.entry-score.good {
  color: var(--color-success-light);
}

.entry-score.warning {
  color: var(--color-warning);
}

.entry-score.degraded {
  color: var(--chart-orange);
}

.entry-score.critical {
  color: var(--color-error);
}

.entry-status {
  font-size: var(--text-sm);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
  margin-bottom: var(--spacing-2);
}

.entry-status i {
  font-size: var(--text-xs);
}

/* Component Chips */
.entry-components {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-1);
}

.component-chip {
  font-size: var(--text-xs);
  padding: var(--spacing-0-5) var(--spacing-1);
  border-radius: var(--radius-sm);
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.component-chip.excellent {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.component-chip.good {
  background: var(--color-success-bg);
  color: var(--color-success-light);
}

.component-chip.warning {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.component-chip.degraded {
  background: rgba(249, 115, 22, 0.1);
  color: var(--chart-orange);
}

.component-chip.critical {
  background: var(--color-error-bg);
  color: var(--color-error);
}
</style>
