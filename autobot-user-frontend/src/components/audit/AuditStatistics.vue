<template>
  <div class="audit-statistics">
    <div class="stats-grid">
      <!-- Total Events Card -->
      <div class="stat-card">
        <div class="stat-icon total">
          <i class="fas fa-list-alt"></i>
        </div>
        <div class="stat-content">
          <span class="stat-value">{{ formatNumber(statistics?.total_entries || 0) }}</span>
          <span class="stat-label">Total Events</span>
        </div>
      </div>

      <!-- Success Card -->
      <div class="stat-card">
        <div class="stat-icon success">
          <i class="fas fa-check-circle"></i>
        </div>
        <div class="stat-content">
          <span class="stat-value">{{ formatNumber(statistics?.success_count || 0) }}</span>
          <span class="stat-label">Successful</span>
        </div>
      </div>

      <!-- Denied Card -->
      <div class="stat-card">
        <div class="stat-icon denied">
          <i class="fas fa-ban"></i>
        </div>
        <div class="stat-content">
          <span class="stat-value">{{ formatNumber(statistics?.denied_count || 0) }}</span>
          <span class="stat-label">Denied</span>
        </div>
      </div>

      <!-- Failed Card -->
      <div class="stat-card">
        <div class="stat-icon failed">
          <i class="fas fa-times-circle"></i>
        </div>
        <div class="stat-content">
          <span class="stat-value">{{ formatNumber(statistics?.failed_count || 0) }}</span>
          <span class="stat-label">Failed</span>
        </div>
      </div>

      <!-- Success Rate Card -->
      <div class="stat-card stat-card-wide">
        <div class="stat-icon rate">
          <i class="fas fa-chart-pie"></i>
        </div>
        <div class="stat-content">
          <div class="success-rate-display">
            <span class="stat-value" :class="successRateClass">
              {{ successRate }}%
            </span>
            <div class="progress-bar">
              <div
                class="progress-fill"
                :class="successRateClass"
                :style="{ width: `${successRate}%` }"
              ></div>
            </div>
          </div>
          <span class="stat-label">Success Rate</span>
        </div>
      </div>

      <!-- VM Info Card -->
      <div v-if="vmInfo" class="stat-card stat-card-wide">
        <div class="stat-icon vm">
          <i class="fas fa-server"></i>
        </div>
        <div class="stat-content">
          <span class="stat-value stat-value-small">{{ vmInfo.vm_name }}</span>
          <span class="stat-label">{{ vmInfo.vm_source }}</span>
        </div>
      </div>
    </div>

    <!-- Top Operations Section -->
    <div v-if="statistics?.top_operations?.length" class="stat-section">
      <h4 class="section-title">
        <i class="fas fa-fire"></i>
        Top Operations
      </h4>
      <div class="top-list">
        <div
          v-for="(item, index) in statistics.top_operations.slice(0, 5)"
          :key="item.operation"
          class="top-item"
        >
          <span class="top-rank">{{ index + 1 }}</span>
          <span class="top-name">{{ formatOperationName(item.operation) }}</span>
          <span class="top-count">{{ formatNumber(item.count) }}</span>
        </div>
      </div>
    </div>

    <!-- Top Users Section -->
    <div v-if="statistics?.top_users?.length" class="stat-section">
      <h4 class="section-title">
        <i class="fas fa-users"></i>
        Most Active Users
      </h4>
      <div class="top-list">
        <div
          v-for="(item, index) in statistics.top_users.slice(0, 5)"
          :key="item.user_id"
          class="top-item clickable"
          @click="emit('user-click', item.user_id)"
        >
          <span class="top-rank">{{ index + 1 }}</span>
          <span class="top-name">{{ item.user_id }}</span>
          <span class="top-count">{{ formatNumber(item.count) }} events</span>
        </div>
      </div>
    </div>

    <!-- Loading Overlay -->
    <div v-if="loading" class="loading-overlay">
      <i class="fas fa-spinner fa-spin"></i>
      <span>Loading statistics...</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AuditStatistics } from '@/types/audit'

interface Props {
  statistics: AuditStatistics | null
  vmInfo: { vm_source: string; vm_name: string } | null
  loading?: boolean
}

interface Emits {
  (e: 'user-click', userId: string): void
}

const props = withDefaults(defineProps<Props>(), {
  loading: false
})

const emit = defineEmits<Emits>()

const successRate = computed(() => {
  if (!props.statistics || props.statistics.total_entries === 0) return 0
  return Math.round(props.statistics.success_rate || 0)
})

const successRateClass = computed(() => {
  const rate = successRate.value
  if (rate >= 95) return 'excellent'
  if (rate >= 80) return 'good'
  if (rate >= 60) return 'warning'
  return 'critical'
})

function formatNumber(value: number): string {
  if (value >= 1000000) {
    return `${(value / 1000000).toFixed(1)}M`
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(1)}K`
  }
  return value.toString()
}

function formatOperationName(operation: string): string {
  return operation
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}
</script>

<style scoped>
.audit-statistics {
  position: relative;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-6);
}

.stat-card {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  transition: all var(--duration-200) var(--ease-in-out);
}

.stat-card:hover {
  box-shadow: var(--shadow-md);
  border-color: var(--border-hover);
}

.stat-card-wide {
  grid-column: span 2;
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-xl);
  flex-shrink: 0;
}

.stat-icon.total {
  background: var(--color-primary-light);
  color: var(--color-primary);
}

.stat-icon.success {
  background: rgba(34, 197, 94, 0.1);
  color: rgb(34, 197, 94);
}

.stat-icon.denied {
  background: rgba(239, 68, 68, 0.1);
  color: rgb(239, 68, 68);
}

.stat-icon.failed {
  background: rgba(249, 115, 22, 0.1);
  color: rgb(249, 115, 22);
}

.stat-icon.rate {
  background: rgba(168, 85, 247, 0.1);
  color: rgb(168, 85, 247);
}

.stat-icon.vm {
  background: rgba(59, 130, 246, 0.1);
  color: rgb(59, 130, 246);
}

.stat-content {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
  flex: 1;
  min-width: 0;
}

.stat-value {
  font-size: var(--text-2xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
  line-height: 1.2;
}

.stat-value-small {
  font-size: var(--text-lg);
}

.stat-label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.success-rate-display {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.stat-value.excellent {
  color: rgb(34, 197, 94);
}

.stat-value.good {
  color: rgb(59, 130, 246);
}

.stat-value.warning {
  color: rgb(249, 115, 22);
}

.stat-value.critical {
  color: rgb(239, 68, 68);
}

.progress-bar {
  height: 6px;
  background: var(--bg-secondary);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: var(--radius-full);
  transition: width var(--duration-500) var(--ease-in-out);
}

.progress-fill.excellent {
  background: rgb(34, 197, 94);
}

.progress-fill.good {
  background: rgb(59, 130, 246);
}

.progress-fill.warning {
  background: rgb(249, 115, 22);
}

.progress-fill.critical {
  background: rgb(239, 68, 68);
}

.stat-section {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  margin-bottom: var(--spacing-4);
}

.section-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  margin: 0 0 var(--spacing-3) 0;
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.section-title i {
  color: var(--color-primary);
}

.top-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.top-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-secondary);
  border-radius: var(--radius-default);
}

.top-item.clickable {
  cursor: pointer;
  transition: background var(--duration-200) var(--ease-in-out);
}

.top-item.clickable:hover {
  background: var(--bg-hover);
}

.top-rank {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-primary);
  color: white;
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: var(--font-bold);
  flex-shrink: 0;
}

.top-name {
  flex: 1;
  font-size: var(--text-sm);
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.top-count {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  font-weight: var(--font-medium);
  flex-shrink: 0;
}

.loading-overlay {
  position: absolute;
  inset: 0;
  background: rgba(var(--bg-card-rgb), 0.8);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
  border-radius: var(--radius-lg);
  color: var(--text-secondary);
}

.loading-overlay i {
  font-size: var(--text-2xl);
  color: var(--color-primary);
}

@media (max-width: 768px) {
  .stats-grid {
    grid-template-columns: 1fr 1fr;
  }

  .stat-card-wide {
    grid-column: span 2;
  }

  .stat-card {
    padding: var(--spacing-3);
  }

  .stat-icon {
    width: 40px;
    height: 40px;
    font-size: var(--text-lg);
  }

  .stat-value {
    font-size: var(--text-xl);
  }
}

@media (max-width: 480px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }

  .stat-card-wide {
    grid-column: span 1;
  }
}
</style>
