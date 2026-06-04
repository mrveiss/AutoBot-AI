<template>
  <BasePanel variant="bordered" size="md">
    <template #header>
      <h3><Icon name="chart-bar" /> {{ $t('manpage.integrationStatus.title') }}</h3>
      <BaseButton
        size="sm"
        variant="outline-solid"
        @click="$emit('refresh')"
        :disabled="loading"
      >
        <Icon name="sync" />
        {{ $t('manpage.integrationStatus.refresh') }}
      </BaseButton>
    </template>

    <div v-if="status" class="status-info">
      <div v-if="status.status === 'not_integrated'" class="not-integrated">
        <Icon name="info-circle" />
        <div>
          <strong>{{ $t('manpage.integrationStatus.notIntegratedTitle') }}</strong>
          <p>{{ $t('manpage.integrationStatus.notIntegratedDesc') }}</p>
        </div>
      </div>

      <div v-else-if="status.status === 'error'" class="error-state">
        <Icon name="exclamation-circle" />
        <div>
          <strong>{{ $t('manpage.integrationStatus.errorTitle') }}</strong>
          <p>{{ status.message }}</p>
        </div>
      </div>

      <div v-else class="integration-stats">
        <div class="stats-grid">
          <div class="stat-item">
            <div class="stat-number">{{ status.successful || 0 }}</div>
            <div class="stat-label">{{ $t('manpage.integrationStatus.successful') }}</div>
          </div>
          <div class="stat-item">
            <div class="stat-number">{{ status.processed || 0 }}</div>
            <div class="stat-label">{{ $t('manpage.integrationStatus.processed') }}</div>
          </div>
          <div class="stat-item">
            <div class="stat-number">{{ status.current_man_page_files || 0 }}</div>
            <div class="stat-label">{{ $t('manpage.integrationStatus.knowledgeFiles') }}</div>
          </div>
          <div class="stat-item">
            <div class="stat-number">{{ status.total_available_tools || 0 }}</div>
            <div class="stat-label">{{ $t('manpage.integrationStatus.availableTools') }}</div>
          </div>
        </div>

        <div v-if="status.integration_date" class="integration-date">
          <Icon name="clock" />
          {{ $t('manpage.integrationStatus.lastIntegrated') }} {{ formatDate(status.integration_date) }}
        </div>

        <div v-if="status.available_commands" class="available-commands">
          <h4>{{ $t('manpage.integrationStatus.integratedCommands', { count: status.available_commands.length }) }}</h4>
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
      <Icon name="spinner" class="animate-spin" />
      {{ $t('manpage.integrationStatus.loadingStatus') }}
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

import Icon from '@/components/ui/Icon.vue'
import BasePanel from '@/components/base/BasePanel.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import { formatDate } from '@/utils/formatHelpers'

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
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.status-info {
  padding: var(--spacing-5);
}

.not-integrated,
.error-state {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  padding: var(--spacing-5);
  border-radius: var(--radius-lg);
  background: var(--bg-surface);
}

.not-integrated {
  border-left: 4px solid var(--color-info);
}

.not-integrated i {
  color: var(--color-info);
  font-size: var(--text-2xl);
}

.error-state {
  border-left: 4px solid var(--color-error);
}

.error-state i {
  color: var(--color-error);
  font-size: var(--text-2xl);
}

.integration-stats {
  background: var(--bg-surface);
  border-radius: var(--radius-lg);
  padding: var(--spacing-5);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: var(--spacing-5);
  margin-bottom: var(--spacing-5);
}

.stat-item {
  text-align: center;
  padding: var(--spacing-4);
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
}

.stat-number {
  font-size: var(--text-3xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
}

.stat-label {
  color: var(--text-tertiary);
  font-size: var(--text-sm);
  margin-top: var(--spacing-1);
}

.integration-date {
  color: var(--text-tertiary);
  margin-bottom: var(--spacing-5);
}

.integration-date i {
  margin-right: var(--spacing-2);
}

.available-commands h4 {
  margin-bottom: var(--spacing-4);
  color: var(--text-primary);
}

.command-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
}

.command-tag {
  background: var(--color-primary);
  color: var(--text-inverse);
  padding: var(--spacing-1) var(--spacing-2-5);
  border-radius: var(--radius-2xl);
  font-size: 0.8rem;
  font-family: 'Courier New', monospace;
}

.loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-4);
  padding: var(--spacing-10);
  color: var(--text-muted);
  font-style: italic;
}

.loading i {
  font-size: 1.2rem;
}
</style>
