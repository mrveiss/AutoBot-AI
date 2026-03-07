<script setup lang="ts">
/**
 * ConnectorManager - Main connector management view (Issue #1255)
 *
 * Lists all source connectors with status cards, provides
 * create/edit/delete/sync/history actions.
 */

import { ref, computed, onMounted } from 'vue'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import { knowledgeRepository } from '@/models/repositories/KnowledgeRepository'
import type {
  ConnectorConfig,
  ConnectorStatus,
  SyncResult
} from '@/types/knowledgeBase'
import ConnectorStatusCard from './ConnectorStatusCard.vue'
import ConnectorConfigModal from './ConnectorConfigModal.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import { formatTimeAgo } from '@/utils/formatHelpers'
import { createLogger } from '@/utils/debugUtils'
import { useI18n } from 'vue-i18n'

const logger = createLogger('ConnectorManager')
const { t } = useI18n()

const store = useKnowledgeStore()

// Modal state
const showConfigModal = ref(false)
const editingConnector = ref<ConnectorConfig | null>(null)

// History modal state
const showHistoryModal = ref(false)
const historyConnectorId = ref<string | null>(null)
const historyItems = ref<SyncResult[]>([])
const historyLoading = ref(false)

// Card refs for resetting sync spinners
const cardRefs = ref<Record<string, InstanceType<typeof ConnectorStatusCard>>>({})

const historyConnectorName = computed(() => {
  if (!historyConnectorId.value) return ''
  const cfg = store.connectors.find(
    c => c.connector_id === historyConnectorId.value
  )
  return cfg ? cfg.name : historyConnectorId.value
})

// =========================================================================
// Data Loading
// =========================================================================

async function loadConnectors() {
  store.setConnectorsLoading(true)
  try {
    const data = await knowledgeRepository.listConnectors()
    store.setConnectors(
      data.connectors || [],
      data.statuses || {}
    )
    logger.info('Loaded %d connectors', (data.connectors || []).length)
  } catch (error) {
    logger.error('Failed to load connectors: %s', error)
  } finally {
    store.setConnectorsLoading(false)
  }
}

// =========================================================================
// Actions
// =========================================================================

function openCreate() {
  editingConnector.value = null
  showConfigModal.value = true
}

function openEdit(id: string) {
  const cfg = store.connectors.find(c => c.connector_id === id)
  if (cfg) {
    editingConnector.value = cfg
    showConfigModal.value = true
  }
}

async function handleSync(id: string) {
  try {
    const result = await knowledgeRepository.syncConnector(id)
    logger.info(
      'Sync completed for %s: added=%d updated=%d deleted=%d',
      id,
      result.added,
      result.updated,
      result.deleted
    )
    // Refresh the connector to get updated status
    await refreshConnectorStatus(id)
  } catch (error) {
    logger.error('Sync failed for %s: %s', id, error)
  } finally {
    // Reset the card's syncing spinner
    const card = cardRefs.value[id]
    if (card) {
      card.resetSyncing()
    }
  }
}

async function handleDelete(id: string) {
  try {
    await knowledgeRepository.deleteConnector(id)
    store.removeConnector(id)
    logger.info('Connector deleted: %s', id)
  } catch (error) {
    logger.error('Failed to delete connector %s: %s', id, error)
  }
}

async function handleViewHistory(id: string) {
  historyConnectorId.value = id
  historyItems.value = []
  historyLoading.value = true
  showHistoryModal.value = true

  try {
    historyItems.value = await knowledgeRepository.getConnectorHistory(id)
  } catch (error) {
    logger.error('Failed to load history for %s: %s', id, error)
  } finally {
    historyLoading.value = false
  }
}

function onConnectorSaved(config: ConnectorConfig) {
  // Reload all connectors to get fresh statuses
  loadConnectors()
}

async function refreshConnectorStatus(id: string) {
  try {
    const data = await knowledgeRepository.getConnector(id)
    store.updateConnectorStatus(id, data.status)
  } catch (error) {
    logger.error('Failed to refresh status for %s: %s', id, error)
  }
}

function getStatus(id: string): ConnectorStatus {
  return (
    store.connectorStatuses[id] || {
      connector_id: id,
      is_healthy: false,
      last_sync_at: null,
      last_sync_status: 'never',
      documents_indexed: 0,
      last_error: null
    }
  )
}

function setCardRef(id: string, el: any) {
  if (el) {
    cardRefs.value[id] = el
  }
}

// =========================================================================
// Lifecycle
// =========================================================================

onMounted(() => {
  loadConnectors()
})
</script>

<template>
  <div class="connector-manager">
    <!-- Header -->
    <div class="manager-header">
      <div class="header-left">
        <h2 class="header-title">
          <svg
            class="header-icon"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"
            />
          </svg>
          {{ $t('knowledge.connectors.title') }}
        </h2>
      </div>

      <BaseButton variant="primary" size="sm" @click="openCreate">
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
              d="M12 4v16m8-8H4"
            />
          </svg>
        </template>
        {{ $t('knowledge.connectors.addConnector') }}
      </BaseButton>
    </div>

    <!-- Loading State -->
    <div v-if="store.connectorsLoading" class="loading-state">
      <i class="fas fa-spinner fa-spin"></i>
      <p>{{ $t('knowledge.connectors.loadingConnectors') }}</p>
    </div>

    <!-- Empty State -->
    <EmptyState
      v-else-if="store.connectors.length === 0"
      icon="fas fa-plug"
      :title="$t('knowledge.connectors.noConnectorsTitle')"
      :message="$t('knowledge.connectors.noConnectorsMessage')"
    >
      <template #actions>
        <BaseButton variant="primary" size="sm" @click="openCreate">
          {{ $t('knowledge.connectors.addConnector') }}
          </BaseButton>
          </template>
          </EmptyState>

    <!-- Connector Grid -->
    <div v-else class="connector-grid">
      <ConnectorStatusCard
        v-for="cfg in store.connectors"
        :key="cfg.connector_id"
        :ref="(el: any) => setCardRef(cfg.connector_id, el)"
        :config="cfg"
        :status="getStatus(cfg.connector_id)"
        @sync="handleSync"
        @edit="openEdit"
        @delete="handleDelete"
        @view-history="handleViewHistory"
      />
    </div>

    <!-- Config Modal -->
    <ConnectorConfigModal
      v-model="showConfigModal"
      :edit-connector="editingConnector"
      @saved="onConnectorSaved"
    />

    <!-- History Modal -->
    <BaseModal
      v-model="showHistoryModal"
      :title="t('knowledge.connectors.syncHistoryTitle', { name: historyConnectorName })"
      size="medium"
    >
      <div v-if="historyLoading" class="loading-state compact">
        <i class="fas fa-spinner fa-spin"></i>
        <p>{{ $t('knowledge.connectors.loadingHistory') }}</p>
      </div>

      <div
        v-else-if="historyItems.length === 0"
        class="history-empty"
      >
        {{ $t('knowledge.connectors.noSyncHistory') }}
      </div>

      <div v-else class="history-list">
        <div
          v-for="(item, idx) in historyItems"
          :key="idx"
          class="history-item"
        >
          <div class="history-header">
            <span
              class="history-status"
              :class="`status-${item.status}`"
            >
              {{ item.status }}
            </span>
            <span class="history-time">
              {{ formatTimeAgo(item.started_at) }}
            </span>
          </div>
          <div class="history-stats">
            <span class="history-stat">
              <span class="stat-num added">+{{ item.added }}</span>
              {{ $t('knowledge.connectors.historyAdded') }}
            </span>
            <span class="history-stat">
              <span class="stat-num updated">~{{ item.updated }}</span>
              {{ $t('knowledge.connectors.historyUpdated') }}
            </span>
            <span class="history-stat">
              <span class="stat-num deleted">-{{ item.deleted }}</span>
              {{ $t('knowledge.connectors.historyDeleted') }}
            </span>
          </div>
          <div v-if="item.errors.length > 0" class="history-errors">
            <span
              v-for="(err, eidx) in item.errors.slice(0, 3)"
              :key="eidx"
              class="history-error"
            >
              {{ err }}
            </span>
            <span
              v-if="item.errors.length > 3"
              class="history-more-errors"
            >
              {{ $t('knowledge.connectors.moreErrors', { count: item.errors.length - 3 }) }}
            </span>
          </div>
        </div>
      </div>
    </BaseModal>
  </div>
</template>

<style scoped>
.connector-manager {
  padding: var(--spacing-6);
  max-width: 960px;
}

/* Header */
.manager-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-5);
  flex-wrap: wrap;
  gap: var(--spacing-4);
}

.header-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  font-family: var(--font-sans);
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-icon {
  width: 22px;
  height: 22px;
  color: var(--color-info);
  flex-shrink: 0;
}

.btn-icon {
  width: 14px;
  height: 14px;
}

/* Loading State */
.loading-state {
  text-align: center;
  padding: var(--spacing-12);
  color: var(--text-secondary);
}

.loading-state.compact {
  padding: var(--spacing-8);
}

.loading-state i {
  font-size: 24px;
  margin-bottom: var(--spacing-3);
}

/* Connector Grid */
.connector-grid {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

/* History */
.history-empty {
  text-align: center;
  padding: var(--spacing-8);
  color: var(--text-tertiary);
  font-size: 14px;
  font-family: var(--font-sans);
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.history-item {
  padding: var(--spacing-3);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 4px;
}

.history-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-2);
}

.history-status {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 2px var(--spacing-2);
  border-radius: 2px;
  font-family: var(--font-sans);
}

.status-success {
  color: var(--color-success-dark);
  background: var(--color-success-bg);
}

.status-failed {
  color: var(--color-error-dark);
  background: var(--color-error-bg);
}

.status-partial {
  color: var(--color-warning-dark);
  background: var(--color-warning-bg);
}

.history-time {
  font-size: 12px;
  color: var(--text-tertiary);
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}

.history-stats {
  display: flex;
  gap: var(--spacing-4);
}

.history-stat {
  font-size: 12px;
  color: var(--text-secondary);
  font-family: var(--font-sans);
}

.stat-num {
  font-weight: 600;
  font-family: var(--font-mono);
}

.stat-num.added {
  color: var(--color-success);
}

.stat-num.updated {
  color: var(--color-info);
}

.stat-num.deleted {
  color: var(--color-error);
}

.history-errors {
  margin-top: var(--spacing-2);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.history-error {
  font-size: 12px;
  color: var(--color-error-dark);
  font-family: var(--font-mono);
  line-height: 1.4;
}

.history-more-errors {
  font-size: 11px;
  color: var(--text-tertiary);
  font-style: italic;
  font-family: var(--font-sans);
}

/* Responsive */
@media (max-width: 768px) {
  .manager-header {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
