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
.service-health {
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  overflow: hidden;
  margin-bottom: 20px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  background: #f8f9fa;
  border-bottom: 1px solid #dee2e6;
}

.section-header h4 {
  margin: 0;
  color: #333;
  font-size: 1.2em;
}

.services-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 20px;
  padding: 20px;
}

.service-card {
  border: 1px solid #dee2e6;
  border-radius: 6px;
  padding: 15px;
  background: #fafafa;
}

.service-card.healthy { border-left: 4px solid #4caf50; }
.service-card.degraded { border-left: 4px solid #ff9800; }
.service-card.critical { border-left: 4px solid #f44336; }
.service-card.offline { border-left: 4px solid #999; }

.service-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.service-name {
  font-weight: 600;
  color: #333;
}

.service-status {
  font-size: 0.8em;
  padding: 2px 8px;
  border-radius: 12px;
  font-weight: 500;
}

.service-status.healthy { background: #e8f5e8; color: #4caf50; }
.service-status.degraded { background: #fff3e0; color: #ff9800; }
.service-status.critical { background: #ffebee; color: #f44336; }
.service-status.offline { background: #f5f5f5; color: #999; }

.service-details {
  font-size: 0.85em;
}

.detail-row {
  display: flex;
  justify-content: space-between;
  margin-bottom: 5px;
}

@media (max-width: 768px) {
  .services-grid {
    grid-template-columns: 1fr;
  }
}
</style>
