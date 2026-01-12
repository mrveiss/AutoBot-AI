<template>
  <div class="service-health">
    <div class="section-header">
      <h4>
        <i class="fas fa-network-wired"></i>
        Distributed Services Health
      </h4>
    </div>

    <div class="services-grid">
      <div
        v-for="service in services"
        :key="service.name"
        :class="['service-card', service.status]"
      >
        <div class="service-header">
          <span class="service-name">{{ service.name }}</span>
          <span :class="['service-status', service.status]">
            <i :class="getStatusIcon(service.status)"></i>
            {{ service.status }}
          </span>
        </div>
        <div class="service-details">
          <div class="detail-row">
            <span>Response Time</span>
            <span>{{ service.response_time_ms }}ms</span>
          </div>
          <div class="detail-row">
            <span>Health Score</span>
            <span>{{ service.health_score }}/100</span>
          </div>
          <div class="detail-row">
            <span>Endpoint</span>
            <span>{{ service.host }}:{{ service.port }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Service Health Grid Component
 *
 * Displays distributed services health status.
 * Extracted from MonitoringDashboard.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

import { getStatusIcon as getStatusIconUtil } from '@/utils/iconMappings'

interface Service {
  name: string
  status: 'healthy' | 'degraded' | 'critical' | 'offline'
  host: string
  port: number
  response_time_ms: number
  health_score: number
}

interface Props {
  services: Service[]
}

defineProps<Props>()

const getStatusIcon = (status: string) => {
  const statusMap: Record<string, string> = {
    'healthy': 'healthy',
    'degraded': 'warning',
    'critical': 'error',
    'offline': 'offline'
  }
  const mappedStatus = statusMap[status] || status
  return getStatusIconUtil(mappedStatus)
}
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.service-health {
  background: var(--bg-surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
  overflow: hidden;
  margin-bottom: var(--spacing-5);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-5);
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-default);
}

.section-header h4 {
  margin: 0;
  color: var(--text-primary);
  font-size: var(--text-lg);
}

.services-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: var(--spacing-5);
  padding: var(--spacing-5);
}

.service-card {
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: var(--spacing-4);
  background: var(--bg-tertiary);
}

.service-card.healthy { border-left: 4px solid var(--color-success); }
.service-card.degraded { border-left: 4px solid var(--color-warning); }
.service-card.critical { border-left: 4px solid var(--color-error); }
.service-card.offline { border-left: 4px solid var(--text-tertiary); }

.service-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-2-5);
}

.service-name {
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.service-status {
  font-size: var(--text-xs);
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-full);
  font-weight: var(--font-medium);
}

.service-status.healthy { background: var(--color-success-bg); color: var(--color-success); }
.service-status.degraded { background: var(--color-warning-bg); color: var(--color-warning); }
.service-status.critical { background: var(--color-error-bg); color: var(--color-error); }
.service-status.offline { background: var(--bg-tertiary); color: var(--text-tertiary); }

.service-details {
  font-size: var(--text-sm);
}

.detail-row {
  display: flex;
  justify-content: space-between;
  margin-bottom: var(--spacing-1);
}

@media (max-width: 768px) {
  .services-grid {
    grid-template-columns: 1fr;
  }
}
</style>
