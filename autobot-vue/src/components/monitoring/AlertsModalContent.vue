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
.alerts-list {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.alert-item {
  border: 1px solid #dee2e6;
  border-radius: 6px;
  padding: 15px;
  background: #fafafa;
}

.alert-item.critical { border-left: 4px solid #f44336; }
.alert-item.high { border-left: 4px solid #e53935; }
.alert-item.warning { border-left: 4px solid #ff9800; }
.alert-item.info { border-left: 4px solid #2196f3; }

.alert-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.category {
  font-size: 0.8em;
  color: #666;
  font-weight: 500;
}

.timestamp {
  font-size: 0.8em;
  color: #666;
  margin-left: auto;
}

.alert-message {
  font-size: 0.9em;
  margin-bottom: 8px;
  color: #333;
}

.alert-recommendation {
  font-size: 0.85em;
  color: #666;
  line-height: 1.4;
}

/* Issue #474: AlertManager-specific styles */
.source-badge {
  font-size: 0.7em;
  padding: 2px 6px;
  border-radius: 3px;
  font-weight: 500;
}

.source-badge.alertmanager {
  background: #e3f2fd;
  color: #1565c0;
}

.source-badge.autobot_monitor {
  background: #fce4ec;
  color: #c62828;
}

.alert-description {
  font-size: 0.85em;
  color: #555;
  margin-bottom: 8px;
  padding: 8px;
  background: #f5f5f5;
  border-radius: 4px;
}

.alert-name {
  font-size: 0.75em;
  color: #888;
  margin-top: 8px;
  font-family: monospace;
}

.no-alerts {
  text-align: center;
  padding: 40px 20px;
  color: #4caf50;
}

.no-alerts i {
  font-size: 2em;
  margin-bottom: 10px;
  display: block;
}
</style>
