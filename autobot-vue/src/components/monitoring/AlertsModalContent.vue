<template>
  <div>
    <div v-if="alerts.length > 0" class="alerts-list">
      <div
        v-for="alert in alerts"
        :key="getAlertKey(alert)"
        :class="['alert-item', alert.severity]"
      >
        <div class="alert-header">
          <StatusBadge :variant="(getSeverityVariant(alert.severity) as any)" size="small">
            {{ alert.severity }}
          </StatusBadge>
          <span class="category">{{ alert.category }}</span>
          <!-- Issue #474: Show alert source -->
          <span v-if="alert.source" class="source-badge" :class="alert.source">
            {{ alert.source === 'alertmanager' ? 'Prometheus' : 'Legacy' }}
          </span>
          <span class="timestamp">{{ formatTimestamp(alert.timestamp) }}</span>
        </div>
        <div class="alert-message">{{ alert.message }}</div>
        <!-- Issue #474: Show description if available from AlertManager -->
        <div v-if="alert.description" class="alert-description">
          {{ alert.description }}
        </div>
        <div class="alert-recommendation">
          <strong>Recommendation:</strong> {{ alert.recommendation }}
        </div>
        <!-- Issue #474: Show alert name for AlertManager alerts -->
        <div v-if="alert.alertname" class="alert-name">
          Alert: {{ alert.alertname }}
        </div>
      </div>
    </div>

    <div v-else class="no-alerts">
      <i class="fas fa-check-circle"></i>
      No performance alerts
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Alerts Modal Content Component
 *
 * Displays performance alerts in a modal.
 * Extracted from MonitoringDashboard.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 * Issue #474: Extended to support AlertManager alerts with richer metadata
 */

import StatusBadge from '@/components/ui/StatusBadge.vue'

/**
 * Alert interface.
 * Issue #474: Extended to support AlertManager fields.
 */
interface Alert {
  timestamp: number
  severity: 'critical' | 'warning' | 'high' | 'info'
  category: string
  message: string
  recommendation: string
  // Issue #474: AlertManager-specific fields
  source?: 'alertmanager' | 'autobot_monitor'
  alertname?: string
  fingerprint?: string
  description?: string
}

interface Props {
  alerts: Alert[]
}

defineProps<Props>()

/**
 * Get unique key for alert.
 * Issue #474: Uses fingerprint for AlertManager alerts.
 */
const getAlertKey = (alert: Alert): string => {
  return alert.fingerprint || `${alert.timestamp}-${alert.category}`
}

const getSeverityVariant = (severity: string) => {
  const variantMap: Record<string, string> = {
    'critical': 'danger',
    'high': 'danger',
    'warning': 'warning',
    'info': 'info'
  }
  return variantMap[severity] || 'secondary'
}

const formatTimestamp = (timestamp: number) => {
  return new Date(timestamp * 1000).toLocaleString()
}
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.alerts-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

.alert-item {
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: var(--spacing-4);
  background: var(--bg-secondary);
}

.alert-item.critical { border-left: 4px solid var(--color-error-hover); }
.alert-item.high { border-left: 4px solid var(--color-error); }
.alert-item.warning { border-left: 4px solid var(--color-warning); }
.alert-item.info { border-left: 4px solid var(--color-info); }

.alert-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
  margin-bottom: var(--spacing-2-5);
}

.category {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  font-weight: var(--font-medium);
}

.timestamp {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  margin-left: auto;
}

.alert-message {
  font-size: var(--text-sm);
  margin-bottom: var(--spacing-2);
  color: var(--text-primary);
}

.alert-recommendation {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: var(--leading-relaxed);
}

/* Issue #474: AlertManager-specific styles */
.source-badge {
  font-size: var(--text-xs);
  padding: var(--spacing-px) var(--spacing-1-5);
  border-radius: var(--radius-sm);
  font-weight: var(--font-medium);
}

.source-badge.alertmanager {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.source-badge.autobot_monitor {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.alert-description {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-2);
  padding: var(--spacing-2);
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
}

.alert-name {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  margin-top: var(--spacing-2);
  font-family: var(--font-mono);
}

.no-alerts {
  text-align: center;
  padding: var(--spacing-10) var(--spacing-5);
  color: var(--color-success);
}

.no-alerts i {
  font-size: var(--text-2xl);
  margin-bottom: var(--spacing-2-5);
  display: block;
}
</style>
