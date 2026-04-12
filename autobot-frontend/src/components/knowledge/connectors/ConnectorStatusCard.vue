<script setup lang="ts">
/**
 * ConnectorStatusCard - Individual connector card (Issue #1255)
 *
 * Displays connector name, type, health status, sync info,
 * document count, and action buttons.
 */

import { ref, computed } from 'vue'
import type { ConnectorConfig, ConnectorStatus } from '@/types/knowledgeBase'
import { formatTimeAgo } from '@/utils/formatHelpers'
import BaseBadge from '@/components/base/BaseBadge.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{
  config: ConnectorConfig
  status: ConnectorStatus
}>()

const emit = defineEmits<{
  sync: [id: string]
  edit: [id: string]
  delete: [id: string]
  viewHistory: [id: string]
}>()

const { t } = useI18n()
const showDeleteConfirm = ref(false)
const syncing = ref(false)

const typeLabel = computed(() => {
  const map: Record<string, string> = {
    file_server: t('knowledge.connectors.status.typeFileServer'),
    web_crawler: t('knowledge.connectors.status.typeWebCrawler'),
    database: t('knowledge.connectors.status.typeDatabase')
  }
  return map[props.config.connector_type] || props.config.connector_type
})

const typeBadgeVariant = computed(() => {
  const map: Record<string, 'primary' | 'info' | 'warning'> = {
    file_server: 'primary',
    web_crawler: 'info',
    database: 'warning'
  }
  return map[props.config.connector_type] || 'primary'
})

const lastSyncDisplay = computed(() => {
  if (!props.status.last_sync_at) return t('knowledge.connectors.status.never')
  return formatTimeAgo(props.status.last_sync_at)
})

const syncStatusVariant = computed(() => {
  const map: Record<string, 'success' | 'error' | 'warning' | 'default'> = {
    success: 'success',
    failed: 'error',
    running: 'warning',
    never: 'default'
  }
  return map[props.status.last_sync_status] || 'default'
})

function handleSync() {
  syncing.value = true
  emit('sync', props.config.connector_id)
}

function handleDelete() {
  showDeleteConfirm.value = false
  emit('delete', props.config.connector_id)
}

/** Called by parent when sync completes */
function resetSyncing() {
  syncing.value = false
}

defineExpose({ resetSyncing })
</script>

<template>
  <div class="connector-card" :class="{ disabled: !config.enabled }">
    <!-- Card Header -->
    <div class="card-header">
      <div class="header-left">
        <!-- Type icon -->
        <svg
          v-if="config.connector_type === 'file_server'"
          class="type-icon"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
          />
        </svg>
        <svg
          v-else-if="config.connector_type === 'web_crawler'"
          class="type-icon"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9"
          />
        </svg>
        <svg
          v-else
          class="type-icon"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4"
          />
        </svg>

        <div class="header-info">
          <div class="name-row">
            <span class="connector-name">{{ config.name }}</span>
            <span
              class="health-dot"
              :class="status.is_healthy ? 'healthy' : 'unhealthy'"
              :title="status.is_healthy ? $t('knowledge.connectors.status.healthy') : $t('knowledge.connectors.status.unhealthy')"
            ></span>
          </div>
          <BaseBadge :variant="typeBadgeVariant" size="xs">
            {{ typeLabel }}
          </BaseBadge>
        </div>
      </div>

      <div v-if="!config.enabled" class="disabled-badge">
        {{ $t('knowledge.connectors.status.disabled') }}
      </div>
    </div>

    <!-- Stats Row -->
    <div class="card-stats">
      <div class="stat">
        <span class="stat-label">{{ $t('knowledge.connectors.status.lastSync') }}</span>
        <span class="stat-value">{{ lastSyncDisplay }}</span>
      </div>
      <div class="stat">
        <span class="stat-label">{{ $t('knowledge.connectors.status.documents') }}</span>
        <span class="stat-value stat-count">
          {{ status.documents_indexed }}
        </span>
      </div>
      <div class="stat">
        <span class="stat-label">{{ $t('knowledge.connectors.status.status') }}</span>
        <BaseBadge :variant="syncStatusVariant" size="xs">
          {{ status.last_sync_status }}
        </BaseBadge>
      </div>
    </div>

    <!-- Error Display -->
    <div v-if="status.last_error" class="card-error">
      <svg
        class="error-icon"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="2"
          d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"
        />
      </svg>
      <span class="error-text">{{ status.last_error }}</span>
    </div>

    <!-- Actions -->
    <div class="card-actions">
      <BaseButton
        variant="primary"
        size="sm"
        :loading="syncing || status.last_sync_status === 'running'"
        :disabled="!config.enabled"
        @click="handleSync"
      >
        <template #icon-left>
          <svg
            class="btn-icon"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
        </template>
        {{ $t('knowledge.connectors.status.sync') }}
      </BaseButton>

      <BaseButton variant="ghost" size="sm" @click="emit('viewHistory', config.connector_id)">
        {{ $t('knowledge.connectors.status.history') }}
      </BaseButton>

      <BaseButton variant="ghost" size="sm" @click="emit('edit', config.connector_id)">
        {{ $t('knowledge.connectors.status.edit') }}
      </BaseButton>

      <!-- Delete with confirmation -->
      <template v-if="!showDeleteConfirm">
        <BaseButton
          variant="ghost"
          size="sm"
          @click="showDeleteConfirm = true"
        >
          {{ $t('knowledge.connectors.status.delete') }}
        </BaseButton>
      </template>
      <template v-else>
        <BaseButton
          variant="danger"
          size="sm"
          @click="handleDelete"
        >
          {{ $t('knowledge.connectors.status.confirm') }}
        </BaseButton>
        <BaseButton
          variant="ghost"
          size="sm"
          @click="showDeleteConfirm = false"
        >
          {{ $t('knowledge.connectors.status.cancel') }}
        </BaseButton>
      </template>
    </div>
  </div>
</template>

<style scoped>
.connector-card {
  padding: var(--spacing-4);
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 4px;
  transition: all 150ms cubic-bezier(0.4, 0, 0.2, 1);
}

.connector-card:hover {
  border-color: var(--border-hover, var(--border-default));
  box-shadow: var(--shadow-sm);
}

.connector-card.disabled {
  opacity: 0.6;
}

/* Card Header */
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--spacing-3);
}

.header-left {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-3);
}

.type-icon {
  width: 20px;
  height: 20px;
  color: var(--color-info);
  flex-shrink: 0;
  margin-top: 2px;
}

.header-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.name-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.connector-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  font-family: var(--font-sans);
}

.health-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.health-dot.healthy {
  background: var(--color-success);
  box-shadow: 0 0 4px var(--color-success);
}

.health-dot.unhealthy {
  background: var(--color-error);
  box-shadow: 0 0 4px var(--color-error);
}

.disabled-badge {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 2px var(--spacing-2);
  background: var(--bg-tertiary);
  border-radius: 2px;
  font-family: var(--font-sans);
}

/* Stats */
.card-stats {
  display: flex;
  gap: var(--spacing-5);
  margin-bottom: var(--spacing-3);
  padding: var(--spacing-3) 0;
  border-top: 1px solid var(--border-default);
  border-bottom: 1px solid var(--border-default);
}

.stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stat-label {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-family: var(--font-sans);
}

.stat-value {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  font-family: var(--font-sans);
}

.stat-count {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

/* Error */
.card-error {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-3);
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--color-error-bg);
  border-radius: 2px;
}

.error-icon {
  width: 14px;
  height: 14px;
  color: var(--color-error);
  flex-shrink: 0;
  margin-top: 1px;
}

.error-text {
  font-size: 12px;
  color: var(--color-error-dark);
  font-family: var(--font-mono);
  line-height: 1.4;
  word-break: break-word;
}

/* Actions */
.card-actions {
  display: flex;
  gap: var(--spacing-2);
  flex-wrap: wrap;
}

.btn-icon {
  width: 14px;
  height: 14px;
}

/* Responsive */
@media (max-width: 768px) {
  .card-stats {
    flex-wrap: wrap;
    gap: var(--spacing-3);
  }
}
</style>
