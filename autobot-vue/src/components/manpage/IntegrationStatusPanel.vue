<template>
  <BasePanel variant="bordered" size="medium">
    <template #header>
      <h3><i class="fas fa-chart-bar"></i> Integration Status</h3>
      <BaseButton
        size="sm"
        variant="outline"
        @click="$emit('refresh')"
        :disabled="loading"
      >
        <i class="fas fa-sync" :class="{ 'fa-spin': loading }"></i>
        Refresh
      </BaseButton>
    </template>

    <div v-if="status" class="status-info">
      <div v-if="status.status === 'not_integrated'" class="not-integrated">
        <i class="fas fa-info-circle"></i>
        <div>
          <strong>Man pages not yet integrated</strong>
          <p>Click "Integrate Man Pages" below to extract documentation from your system.</p>
        </div>
      </div>

      <div v-else-if="status.status === 'error'" class="error-state">
        <i class="fas fa-exclamation-circle"></i>
        <div>
          <strong>Integration Error</strong>
          <p>{{ status.message }}</p>
        </div>
      </div>

      <div v-else class="integration-stats">
        <div class="stats-grid">
          <div class="stat-item">
            <div class="stat-number">{{ status.successful || 0 }}</div>
            <div class="stat-label">Successful</div>
          </div>
          <div class="stat-item">
            <div class="stat-number">{{ status.processed || 0 }}</div>
            <div class="stat-label">Processed</div>
          </div>
          <div class="stat-item">
            <div class="stat-number">{{ status.current_man_page_files || 0 }}</div>
            <div class="stat-label">Knowledge Files</div>
          </div>
          <div class="stat-item">
            <div class="stat-number">{{ status.total_available_tools || 0 }}</div>
            <div class="stat-label">Available Tools</div>
          </div>
        </div>

        <div v-if="status.integration_date" class="integration-date">
          <i class="fas fa-clock"></i>
          Last integrated: {{ formatDate(status.integration_date) }}
        </div>

        <div v-if="status.available_commands" class="available-commands">
          <h4>Integrated Commands ({{ status.available_commands.length }}):</h4>
          <div class="command-tags">
            <span
              v-for="command in status.available_commands"
              :key="command"
              class="command-tag"
            >
              {{ command }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <div v-if="loading" class="loading">
      <i class="fas fa-spinner fa-spin"></i>
      Loading integration status...
    </div>
  </BasePanel>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Integration Status Panel Component
 *
 * Displays man page integration status and statistics.
 * Extracted from ManPageManager.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

import BasePanel from '@/components/base/BasePanel.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import { useKnowledgeBase } from '@/composables/useKnowledgeBase'

interface IntegrationStatus {
  status: 'not_integrated' | 'error' | 'integrated' | string
  message?: string
  successful?: number
  processed?: number
  current_man_page_files?: number
  total_available_tools?: number
  integration_date?: string
  available_commands?: string[]
}

interface Props {
  status: IntegrationStatus | null
  loading?: boolean
}

interface Emits {
  (e: 'refresh'): void
}

withDefaults(defineProps<Props>(), {
  loading: false
})

defineEmits<Emits>()

const { formatDate } = useKnowledgeBase()
</script>

<style scoped>
.status-info {
  padding: 20px;
}

.not-integrated,
.error-state {
  display: flex;
  align-items: center;
  gap: 15px;
  padding: 20px;
  border-radius: 8px;
  background: white;
}

.not-integrated {
  border-left: 4px solid #3498db;
}

.not-integrated i {
  color: #3498db;
  font-size: 1.5rem;
}

.error-state {
  border-left: 4px solid #e74c3c;
}

.error-state i {
  color: #e74c3c;
  font-size: 1.5rem;
}

.integration-stats {
  background: white;
  border-radius: 8px;
  padding: 20px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 20px;
  margin-bottom: 20px;
}

.stat-item {
  text-align: center;
  padding: 15px;
  background: #ecf0f1;
  border-radius: 8px;
}

.stat-number {
  font-size: 2rem;
  font-weight: bold;
  color: #2c3e50;
}

.stat-label {
  color: #7f8c8d;
  font-size: 0.9rem;
  margin-top: 5px;
}

.integration-date {
  color: #7f8c8d;
  margin-bottom: 20px;
}

.integration-date i {
  margin-right: 8px;
}

.available-commands h4 {
  margin-bottom: 15px;
  color: #2c3e50;
}

.command-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.command-tag {
  background: #3498db;
  color: white;
  padding: 4px 10px;
  border-radius: 15px;
  font-size: 0.8rem;
  font-family: 'Courier New', monospace;
}

.loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 15px;
  padding: 40px;
  color: #7f8c8d;
  font-style: italic;
}

.loading i {
  font-size: 1.2rem;
}
</style>
