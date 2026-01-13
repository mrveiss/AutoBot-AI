<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  SystemHealthGrid.vue - VM Status Grid Component
  Displays health status for all 5 VMs (Issue #581)
-->
<template>
  <BasePanel variant="bordered" size="medium">
    <template #header>
      <div class="panel-header-content">
        <h2><i class="fas fa-server"></i> VM Infrastructure Health</h2>
        <span class="vm-count">{{ vms.length }} nodes</span>
      </div>
    </template>

    <div v-if="loading" class="loading-state">
      <i class="fas fa-spinner fa-spin"></i>
      <span>Loading VM health data...</span>
    </div>

    <div v-else-if="vms.length === 0" class="empty-state">
      <i class="fas fa-server"></i>
      <span>No VM data available</span>
    </div>

    <div v-else class="vm-grid">
      <div
        v-for="vm in vms"
        :key="vm.name"
        :class="['vm-card', `status-${vm.status}`]"
        @click="$emit('refresh-vm', vm.name)"
      >
        <!-- VM Header -->
        <div class="vm-header">
          <div class="vm-identity">
            <span class="vm-name">{{ vm.name }}</span>
            <span :class="['vm-status-badge', vm.status]">
              <i :class="getStatusIcon(vm.status)"></i>
              {{ vm.status }}
            </span>
          </div>
          <div class="vm-score">
            <span class="score-value">{{ vm.healthScore }}</span>
            <span class="score-label">/ 100</span>
          </div>
        </div>

        <!-- VM Details -->
        <div class="vm-details">
          <div class="detail-row">
            <span class="detail-label">
              <i class="fas fa-network-wired"></i>
              Endpoint
            </span>
            <span class="detail-value">{{ vm.ip }}:{{ vm.port }}</span>
          </div>
          <div class="detail-row" v-if="vm.responseTime > 0">
            <span class="detail-label">
              <i class="fas fa-clock"></i>
              Response
            </span>
            <span class="detail-value">{{ vm.responseTime }}ms</span>
          </div>
          <div class="detail-row" v-if="vm.lastCheck">
            <span class="detail-label">
              <i class="fas fa-history"></i>
              Last Check
            </span>
            <span class="detail-value">{{ formatTime(vm.lastCheck) }}</span>
          </div>
        </div>

        <!-- Services List -->
        <div class="vm-services" v-if="vm.services && vm.services.length">
          <span class="services-label">Services:</span>
          <div class="services-list">
            <span
              v-for="service in vm.services"
              :key="service"
              class="service-tag"
            >
              {{ service }}
            </span>
          </div>
        </div>

        <!-- Health Progress Bar -->
        <div class="health-progress">
          <div
            class="progress-fill"
            :style="{ width: `${vm.healthScore}%` }"
            :class="getHealthClass(vm.healthScore)"
          ></div>
        </div>
      </div>
    </div>
  </BasePanel>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import BasePanel from '@/components/base/BasePanel.vue'

interface VMHealth {
  name: string
  ip: string
  port: number
  status: 'healthy' | 'degraded' | 'critical' | 'offline'
  responseTime: number
  healthScore: number
  lastCheck: string
  services: string[]
}

interface Props {
  vms: VMHealth[]
  loading?: boolean
}

defineProps<Props>()

defineEmits<{
  (e: 'refresh-vm', vmName: string): void
}>()

const getStatusIcon = (status: string): string => {
  const iconMap: Record<string, string> = {
    healthy: 'fas fa-check-circle',
    degraded: 'fas fa-exclamation-triangle',
    critical: 'fas fa-times-circle',
    offline: 'fas fa-power-off'
  }
  return iconMap[status] || 'fas fa-question-circle'
}

const getHealthClass = (score: number): string => {
  if (score >= 90) return 'excellent'
  if (score >= 70) return 'good'
  if (score >= 50) return 'warning'
  if (score >= 30) return 'degraded'
  return 'critical'
}

const formatTime = (timestamp: string): string => {
  if (!timestamp) return 'N/A'
  try {
    return new Date(timestamp).toLocaleTimeString()
  } catch {
    return timestamp
  }
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

.vm-count {
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
  gap: var(--spacing-3);
  padding: var(--spacing-8);
  color: var(--text-tertiary);
}

.loading-state i,
.empty-state i {
  font-size: var(--text-2xl);
}

/* VM Grid */
.vm-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--spacing-4);
}

/* VM Card */
.vm-card {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  cursor: pointer;
  transition: all var(--duration-200) var(--ease-in-out);
}

.vm-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

/* Status-based left border */
.vm-card.status-healthy {
  border-left: 4px solid var(--color-success);
}

.vm-card.status-degraded {
  border-left: 4px solid var(--color-warning);
}

.vm-card.status-critical {
  border-left: 4px solid var(--color-error);
}

.vm-card.status-offline {
  border-left: 4px solid var(--text-tertiary);
  opacity: 0.7;
}

/* VM Header */
.vm-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--spacing-3);
}

.vm-identity {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.vm-name {
  font-weight: var(--font-semibold);
  font-size: var(--text-base);
  color: var(--text-primary);
}

.vm-status-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-full);
  text-transform: capitalize;
}

.vm-status-badge.healthy {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.vm-status-badge.degraded {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.vm-status-badge.critical {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.vm-status-badge.offline {
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
}

.vm-score {
  text-align: right;
}

.score-value {
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
}

.score-label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

/* VM Details */
.vm-details {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1-5);
  margin-bottom: var(--spacing-3);
}

.detail-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: var(--text-sm);
}

.detail-label {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  color: var(--text-secondary);
}

.detail-label i {
  font-size: var(--text-xs);
  width: 14px;
  text-align: center;
}

.detail-value {
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
}

/* Services */
.vm-services {
  margin-bottom: var(--spacing-3);
}

.services-label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  display: block;
  margin-bottom: var(--spacing-1);
}

.services-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-1);
}

.service-tag {
  font-size: var(--text-xs);
  padding: var(--spacing-0-5) var(--spacing-1-5);
  background: var(--bg-secondary);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
}

/* Health Progress Bar */
.health-progress {
  height: 4px;
  background: var(--bg-secondary);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: var(--radius-full);
  transition: width var(--duration-300) var(--ease-out);
}

.progress-fill.excellent {
  background: var(--color-success);
}

.progress-fill.good {
  background: var(--color-success-light);
}

.progress-fill.warning {
  background: var(--color-warning);
}

.progress-fill.degraded {
  background: var(--chart-orange);
}

.progress-fill.critical {
  background: var(--color-error);
}

/* Responsive */
@media (max-width: 768px) {
  .vm-grid {
    grid-template-columns: 1fr;
  }
}
</style>
