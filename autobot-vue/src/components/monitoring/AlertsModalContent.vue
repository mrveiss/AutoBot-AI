<template>
  <div>
    <div v-if="alerts.length > 0" class="alerts-list">
      <div
        v-for="alert in alerts"
        :key="alert.timestamp"
        :class="['alert-item', alert.severity]"
      >
        <div class="alert-header">
          <StatusBadge :variant="getSeverityVariant(alert.severity)" size="small">
            {{ alert.severity }}
          </StatusBadge>
          <span class="category">{{ alert.category }}</span>
          <span class="timestamp">{{ formatTimestamp(alert.timestamp) }}</span>
        </div>
        <div class="alert-message">{{ alert.message }}</div>
        <div class="alert-recommendation">
          <strong>Recommendation:</strong> {{ alert.recommendation }}
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
 */

import StatusBadge from '@/components/ui/StatusBadge.vue'

interface Alert {
  timestamp: number
  severity: 'critical' | 'warning'
  category: string
  message: string
  recommendation: string
}

interface Props {
  alerts: Alert[]
}

defineProps<Props>()

const getSeverityVariant = (severity: string) => {
  const variantMap: Record<string, string> = {
    'critical': 'danger',
    'warning': 'warning'
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
.alert-item.warning { border-left: 4px solid #ff9800; }

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
