<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  ErrorStatistics.vue - Statistics cards with error counts and health score
  Part of Error Monitoring Dashboard (Issue #579)
-->
<template>
  <div class="error-statistics">
    <div class="stats-grid">
      <!-- Health Score Card -->
      <BasePanel variant="elevated" size="small">
        <div class="stat-card health-card" :class="healthStatusClass">
          <div class="stat-icon">
            <i :class="healthIcon"></i>
          </div>
          <div class="stat-content">
            <div class="stat-value">{{ healthScore }}%</div>
            <div class="stat-label">System Health</div>
            <div class="stat-status" :class="healthStatusClass">
              {{ healthStatus }}
            </div>
          </div>
        </div>
      </BasePanel>

      <!-- Total Errors Card -->
      <BasePanel variant="elevated" size="small">
        <div class="stat-card">
          <div class="stat-icon error-icon">
            <i class="fas fa-exclamation-triangle"></i>
          </div>
          <div class="stat-content">
            <div class="stat-value">{{ statistics.totalErrors }}</div>
            <div class="stat-label">Total Errors</div>
          </div>
        </div>
      </BasePanel>

      <!-- Critical Errors Card -->
      <BasePanel variant="elevated" size="small">
        <div class="stat-card" :class="{ 'has-critical': statistics.criticalErrors > 0 }">
          <div class="stat-icon critical-icon">
            <i class="fas fa-skull-crossbones"></i>
          </div>
          <div class="stat-content">
            <div class="stat-value critical-value">{{ statistics.criticalErrors }}</div>
            <div class="stat-label">Critical</div>
          </div>
        </div>
      </BasePanel>

      <!-- High Severity Card -->
      <BasePanel variant="elevated" size="small">
        <div class="stat-card" :class="{ 'has-high': statistics.highErrors > 0 }">
          <div class="stat-icon high-icon">
            <i class="fas fa-exclamation-circle"></i>
          </div>
          <div class="stat-content">
            <div class="stat-value high-value">{{ statistics.highErrors }}</div>
            <div class="stat-label">High Severity</div>
          </div>
        </div>
      </BasePanel>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import BasePanel from '@/components/base/BasePanel.vue'

interface ErrorStatistics {
  totalErrors: number
  criticalErrors: number
  highErrors: number
  healthScore: number
  healthStatus: string
}

interface Props {
  statistics: ErrorStatistics
}

const props = withDefaults(defineProps<Props>(), {
  statistics: () => ({
    totalErrors: 0,
    criticalErrors: 0,
    highErrors: 0,
    healthScore: 100,
    healthStatus: 'excellent'
  })
})

const healthScore = computed(() => props.statistics.healthScore)
const healthStatus = computed(() => {
  const status = props.statistics.healthStatus
  return status.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
})

const healthStatusClass = computed(() => {
  const status = props.statistics.healthStatus.toLowerCase()
  return `health-${status.replace(/_/g, '-')}`
})

const healthIcon = computed(() => {
  const status = props.statistics.healthStatus.toLowerCase()
  switch (status) {
    case 'excellent':
      return 'fas fa-heart text-green-500'
    case 'healthy':
      return 'fas fa-heartbeat text-green-400'
    case 'warning':
      return 'fas fa-heart-crack text-yellow-500'
    case 'degraded':
      return 'fas fa-heart-pulse text-orange-500'
    case 'critical':
      return 'fas fa-skull text-red-500'
    default:
      return 'fas fa-heart text-gray-400'
  }
})
</script>

<style scoped>
.error-statistics {
  width: 100%;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--spacing-4);
}

.stat-card {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  padding: var(--spacing-2);
}

.stat-icon {
  font-size: var(--text-3xl);
  width: 50px;
  height: 50px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-lg);
  background: var(--bg-tertiary);
}

.error-icon {
  color: var(--color-warning);
}

.critical-icon {
  color: var(--color-error);
}

.high-icon {
  color: var(--chart-orange);
}

.stat-content {
  flex: 1;
}

.stat-value {
  font-size: var(--text-3xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
  line-height: 1.2;
}

.stat-label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-top: var(--spacing-1);
}

.stat-status {
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  text-transform: uppercase;
  margin-top: var(--spacing-1);
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-sm);
  display: inline-block;
}

/* Health status colors */
.health-excellent .stat-status,
.health-excellent .stat-value {
  color: var(--color-success);
}

.health-excellent .stat-status {
  background: var(--color-success-bg);
}

.health-healthy .stat-status,
.health-healthy .stat-value {
  color: var(--color-success-light);
}

.health-healthy .stat-status {
  background: var(--color-success-bg);
}

.health-warning .stat-status,
.health-warning .stat-value {
  color: var(--color-warning);
}

.health-warning .stat-status {
  background: var(--color-warning-bg);
}

.health-degraded .stat-status,
.health-degraded .stat-value {
  color: var(--chart-orange);
}

.health-degraded .stat-status {
  background: rgba(249, 115, 22, 0.15);
}

.health-critical .stat-status,
.health-critical .stat-value {
  color: var(--color-error);
}

.health-critical .stat-status {
  background: var(--color-error-bg);
}

/* Severity value colors */
.critical-value {
  color: var(--color-error);
}

.high-value {
  color: var(--chart-orange);
}

/* Alert states */
.has-critical {
  animation: pulse-critical 2s ease-in-out infinite;
}

.has-high {
  animation: pulse-high 3s ease-in-out infinite;
}

@keyframes pulse-critical {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(239, 68, 68, 0);
  }
  50% {
    box-shadow: 0 0 0 4px rgba(239, 68, 68, 0.2);
  }
}

@keyframes pulse-high {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(249, 115, 22, 0);
  }
  50% {
    box-shadow: 0 0 0 3px rgba(249, 115, 22, 0.15);
  }
}

/* Responsive */
@media (max-width: 768px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .stat-value {
    font-size: var(--text-2xl);
  }

  .stat-icon {
    font-size: var(--text-2xl);
    width: 40px;
    height: 40px;
  }
}

@media (max-width: 480px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }
}
</style>
