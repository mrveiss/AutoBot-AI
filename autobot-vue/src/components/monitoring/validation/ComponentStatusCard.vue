<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  ComponentStatusCard.vue - Individual Component Status Display
  Shows validation status for individual system components (Issue #581)
-->
<template>
  <div :class="['component-card', `status-${normalizedStatus}`]" @click="$emit('validate')">
    <!-- Card Header -->
    <div class="card-header">
      <div class="component-icon">
        <i :class="getComponentIcon()"></i>
      </div>
      <div class="component-info">
        <span class="component-name">{{ formatName(name) }}</span>
        <span :class="['status-badge', normalizedStatus]">
          <i :class="getStatusIcon()"></i>
          {{ normalizedStatus }}
        </span>
      </div>
    </div>

    <!-- Score Display -->
    <div class="score-section">
      <div class="score-circle" :class="scoreClass">
        <svg viewBox="0 0 36 36" class="circular-chart">
          <path
            class="circle-bg"
            d="M18 2.0845
              a 15.9155 15.9155 0 0 1 0 31.831
              a 15.9155 15.9155 0 0 1 0 -31.831"
          />
          <path
            :class="['circle-progress', scoreClass]"
            :stroke-dasharray="`${status.score || 0}, 100`"
            d="M18 2.0845
              a 15.9155 15.9155 0 0 1 0 31.831
              a 15.9155 15.9155 0 0 1 0 -31.831"
          />
        </svg>
        <span class="score-value">{{ Math.round(status.score || 0) }}</span>
      </div>
      <span class="score-label">Health Score</span>
    </div>

    <!-- Message -->
    <div class="message-section" v-if="status.message">
      <p class="message-text">{{ status.message }}</p>
    </div>

    <!-- Last Validated -->
    <div class="footer-section" v-if="status.lastValidated">
      <i class="fas fa-clock"></i>
      <span>{{ formatTimestamp(status.lastValidated) }}</span>
    </div>

    <!-- Validate Button -->
    <button class="validate-btn" @click.stop="$emit('validate')">
      <i class="fas fa-play"></i>
      Validate
    </button>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { computed } from 'vue'

interface ComponentStatus {
  status: string
  score: number
  message: string
  lastValidated?: string
  details?: Record<string, unknown>
}

interface Props {
  name: string
  status: ComponentStatus
}

const props = defineProps<Props>()

defineEmits<{
  (e: 'validate'): void
}>()

// Computed
const normalizedStatus = computed(() => {
  const s = props.status.status?.toLowerCase() || 'unknown'
  if (s === 'healthy' || s === 'excellent') return 'healthy'
  if (s === 'warning' || s === 'degraded') return 'warning'
  if (s === 'unhealthy' || s === 'critical') return 'critical'
  return 'unknown'
})

const scoreClass = computed(() => {
  const score = props.status.score || 0
  if (score >= 90) return 'excellent'
  if (score >= 70) return 'good'
  if (score >= 50) return 'warning'
  if (score >= 30) return 'degraded'
  return 'critical'
})

// Methods
const getComponentIcon = (): string => {
  const iconMap: Record<string, string> = {
    cache: 'fas fa-database',
    caching: 'fas fa-database',
    search: 'fas fa-search',
    hybrid_search: 'fas fa-search-plus',
    monitoring: 'fas fa-chart-line',
    model: 'fas fa-brain',
    model_optimization: 'fas fa-bolt',
    integration: 'fas fa-puzzle-piece'
  }
  return iconMap[props.name.toLowerCase()] || 'fas fa-cube'
}

const getStatusIcon = (): string => {
  const iconMap: Record<string, string> = {
    healthy: 'fas fa-check-circle',
    warning: 'fas fa-exclamation-triangle',
    critical: 'fas fa-times-circle',
    unknown: 'fas fa-question-circle'
  }
  return iconMap[normalizedStatus.value] || 'fas fa-circle'
}

const formatName = (name: string): string => {
  return name
    .replace(/_/g, ' ')
    .replace(/\b\w/g, l => l.toUpperCase())
}

const formatTimestamp = (timestamp: string): string => {
  if (!timestamp) return 'Never'
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
</script>

<style scoped>
.component-card {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
  cursor: pointer;
  transition: all var(--duration-200) var(--ease-in-out);
  position: relative;
  overflow: hidden;
}

.component-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

/* Status-based styling */
.component-card.status-healthy {
  border-left: 4px solid var(--color-success);
}

.component-card.status-warning {
  border-left: 4px solid var(--color-warning);
}

.component-card.status-critical {
  border-left: 4px solid var(--color-error);
}

.component-card.status-unknown {
  border-left: 4px solid var(--text-tertiary);
}

/* Card Header */
.card-header {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-3);
}

.component-icon {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  flex-shrink: 0;
}

.component-icon i {
  font-size: var(--text-lg);
  color: var(--color-primary);
}

.component-info {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
  flex: 1;
  min-width: 0;
}

.component-name {
  font-weight: var(--font-semibold);
  font-size: var(--text-base);
  color: var(--text-primary);
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-full);
  text-transform: capitalize;
  width: fit-content;
}

.status-badge.healthy {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.status-badge.warning {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.status-badge.critical {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.status-badge.unknown {
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
}

/* Score Section */
.score-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-1);
}

.score-circle {
  width: 80px;
  height: 80px;
  position: relative;
}

.circular-chart {
  width: 100%;
  height: 100%;
  transform: rotate(-90deg);
}

.circle-bg {
  fill: none;
  stroke: var(--bg-secondary);
  stroke-width: 3.5;
}

.circle-progress {
  fill: none;
  stroke-width: 3.5;
  stroke-linecap: round;
  transition: stroke-dasharray var(--duration-500) var(--ease-out);
}

.circle-progress.excellent {
  stroke: var(--color-success);
}

.circle-progress.good {
  stroke: var(--color-success-light);
}

.circle-progress.warning {
  stroke: var(--color-warning);
}

.circle-progress.degraded {
  stroke: var(--chart-orange);
}

.circle-progress.critical {
  stroke: var(--color-error);
}

.score-value {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
}

.score-label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

/* Message Section */
.message-section {
  padding: var(--spacing-2);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
}

.message-text {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--text-secondary);
  line-height: 1.4;
}

/* Footer Section */
.footer-section {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.footer-section i {
  font-size: 10px;
}

/* Validate Button */
.validate-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2);
  background: var(--color-primary);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  cursor: pointer;
  transition: all var(--duration-150) var(--ease-in-out);
  opacity: 0;
  transform: translateY(10px);
}

.component-card:hover .validate-btn {
  opacity: 1;
  transform: translateY(0);
}

.validate-btn:hover {
  background: var(--color-primary-dark);
}
</style>
