<template>
  <div class="verification-queue">
    <!-- Header -->
    <div class="verification-header">
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
              d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
            />
          </svg>
          {{ $t('knowledge.verification.title') }}
        </h2>
      </div>

      <div class="header-right">
        <div class="mode-toggle">
          <span class="mode-label">{{ $t('knowledge.verification.modeLabel') }}</span>
          <button
            class="mode-btn"
            :class="{ active: store.verificationConfig.mode === 'autonomous' }"
            @click="setMode('autonomous')"
            :disabled="configLoading"
          >
            {{ $t('knowledge.verification.autonomous') }}
          </button>
          <button
            class="mode-btn"
            :class="{ active: store.verificationConfig.mode === 'collaborative' }"
            @click="setMode('collaborative')"
            :disabled="configLoading"
          >
            {{ $t('knowledge.verification.collaborative') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Stats Bar -->
    <div class="stats-bar">
      <div class="stat-item">
        <span class="stat-value stat-pending">
          {{ store.pendingVerificationsTotal }}
        </span>
        <span class="stat-label">{{ $t('knowledge.verification.pending') }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-value stat-approved">{{ todayApproved }}</span>
        <span class="stat-label">{{ $t('knowledge.verification.approvedToday') }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-value stat-rejected">{{ todayRejected }}</span>
        <span class="stat-label">{{ $t('knowledge.verification.rejectedToday') }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">
          {{ (store.verificationConfig?.quality_threshold ?? 0).toFixed(1) }}
        </span>
        <span class="stat-label">{{ $t('knowledge.verification.qualityThreshold') }}</span>
      </div>
    </div>

    <!-- Bulk Actions -->
    <div v-if="selection.selectedCount.value > 0" class="bulk-toolbar">
      <span class="bulk-count">
        {{ $t('knowledge.verification.selectedCount', { count: selection.selectedCount.value }) }}
      </span>
      <BaseButton
        variant="ghost"
        size="sm"
        @click="selection.selectAll"
      >
        {{ $t('knowledge.verification.selectAll') }}
      </BaseButton>
      <BaseButton
        variant="success"
        size="sm"
        @click="bulkApprove"
        :loading="bulkProcessing"
      >
        <Icon name="check" />
        {{ $t('knowledge.verification.approveSelected') }}
      </BaseButton>
      <BaseButton
        variant="error"
        size="sm"
        @click="bulkReject"
        :loading="bulkProcessing"
      >
        <Icon name="times" />
        {{ $t('knowledge.verification.rejectSelected') }}
      </BaseButton>
      <BaseButton
        variant="ghost"
        size="sm"
        @click="selection.clear"
      >
        {{ $t('knowledge.verification.clearSelection') }}
      </BaseButton>
    </div>

    <!-- Loading State -->
    <div v-if="store.verificationLoading" class="loading-state">
      <Icon name="spinner" :spin="true" />
      <p>{{ $t('knowledge.verification.loading') }}</p>
    </div>

    <!-- Empty State -->
    <EmptyState
      v-else-if="store.pendingVerifications.length === 0"
      icon="shield-alt"
      :title="$t('knowledge.verification.emptyTitle')"
      :message="$t('knowledge.verification.emptyMessage')"
    />

    <!-- Source Cards -->
    <div v-else class="source-list">
      <div
        v-for="source in store.pendingVerifications"
        :key="source.fact_id"
        class="source-card"
        :class="{ selected: selection.isSelected(source) }"
      >
        <div class="card-header">
          <input
            type="checkbox"
            :checked="selection.isSelected(source)"
            @change="selection.toggle(source)"
            class="card-checkbox"
          />
          <div class="card-title-row">
            <span class="card-title">
              {{ source.title || source.domain || $t('knowledge.verification.untitled') }}
            </span>
            <QualityScoreBadge :score="source.quality_score" />
          </div>
        </div>

        <div class="card-meta">
          <span class="source-type-badge">
            {{ formatSourceType(source.source_type) }}
          </span>
          <span v-if="source.domain" class="card-domain">
            {{ source.domain }}
          </span>
          <span class="card-timestamp">
            {{ formatTimestamp(source.timestamp) }}
          </span>
        </div>

        <p class="card-content">
          {{ truncateContent(source.content) }}
        </p>

        <div v-if="source.url" class="card-url">
          <svg
            class="url-icon"
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
          <a
            :href="source.url"
            target="_blank"
            rel="noopener noreferrer"
            class="url-link"
          >
            {{ source.url }}
          </a>
        </div>

        <div class="card-actions">
          <BaseButton
            variant="success"
            size="sm"
            @click="approveSource(source.fact_id)"
            :loading="actionLoadingId === source.fact_id"
          >
            <Icon name="check" />
            {{ $t('knowledge.verification.approve') }}
          </BaseButton>
          <BaseButton
            variant="error"
            size="sm"
            @click="rejectSource(source.fact_id)"
            :loading="actionLoadingId === source.fact_id"
          >
            <Icon name="times" />
            {{ $t('knowledge.verification.reject') }}
          </BaseButton>
        </div>
      </div>
    </div>

    <!-- Pagination -->
    <div
      v-if="totalPages > 1"
      class="pagination"
    >
      <BaseButton
        variant="outline-solid"
        size="sm"
        :disabled="currentPage === 1"
        @click="goToPage(currentPage - 1)"
      >
        <Icon name="chevron-left" />
      </BaseButton>
      <span class="page-info">
        {{ $t('knowledge.verification.pageInfo', { current: currentPage, total: totalPages }) }}
      </span>
      <BaseButton
        variant="outline-solid"
        size="sm"
        :disabled="currentPage === totalPages"
        @click="goToPage(currentPage + 1)"
      >
        <Icon name="chevron-right" />
      </BaseButton>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import { useUserStore } from '@/stores/useUserStore'
import { knowledgeRepository } from '@/models/repositories/KnowledgeRepository'
import type { VerificationConfig } from '@/types/knowledgeBase'
import { formatDate } from '@/utils/formatHelpers'
import { useBatchSelection } from '@/composables/useBatchSelection'
import BaseButton from '@/components/base/BaseButton.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import QualityScoreBadge from './QualityScoreBadge.vue'
import { createLogger } from '@/utils/debugUtils'
import Icon from '@/components/ui/Icon.vue'

const logger = createLogger('KnowledgeVerificationQueue')

const { t } = useI18n()
const store = useKnowledgeStore()
const userStore = useUserStore()

// Local state
const currentPage = ref(1)
const pageSize = 20
const todayApproved = ref(0)
const todayRejected = ref(0)
const selection = useBatchSelection<{ fact_id: string }, string>(
  () => store.pendingVerifications,
  (item) => item.fact_id
)
const actionLoadingId = ref<string | null>(null)
const bulkProcessing = ref(false)
const configLoading = ref(false)

// Computed
const totalPages = computed(() =>
  Math.max(1, Math.ceil(store.pendingVerificationsTotal / pageSize))
)

const currentUser = computed(() =>
  userStore.currentUser?.username || 'user'
)

// Data loading
async function loadPendingVerifications() {
  try {
    store.setVerificationLoading(true)
    const data = await knowledgeRepository.getPendingVerifications(
      currentPage.value,
      pageSize
    )
    store.setPendingVerifications(data.sources || [], data.total || 0)
  } catch (error) {
    logger.error('Failed to load pending verifications: %s', error)
  } finally {
    store.setVerificationLoading(false)
  }
}

async function loadVerificationConfig() {
  try {
    configLoading.value = true
    const config = await knowledgeRepository.getVerificationConfig()
    store.setVerificationConfig(config)
  } catch (error) {
    logger.error('Failed to load verification config: %s', error)
  } finally {
    configLoading.value = false
  }
}

// Actions
async function approveSource(factId: string) {
  try {
    actionLoadingId.value = factId
    await knowledgeRepository.approveSource(factId, currentUser.value)
    store.removePendingSource(factId)
    todayApproved.value++
    selection.deselectByKey(factId)
    logger.info('Source approved: %s', factId)
  } catch (error) {
    logger.error('Failed to approve source %s: %s', factId, error)
  } finally {
    actionLoadingId.value = null
  }
}

async function rejectSource(factId: string) {
  try {
    actionLoadingId.value = factId
    await knowledgeRepository.rejectSource(
      factId,
      currentUser.value,
      false
    )
    store.removePendingSource(factId)
    todayRejected.value++
    selection.deselectByKey(factId)
    logger.info('Source rejected: %s', factId)
  } catch (error) {
    logger.error('Failed to reject source %s: %s', factId, error)
  } finally {
    actionLoadingId.value = null
  }
}

async function setMode(mode: VerificationConfig['mode']) {
  try {
    configLoading.value = true
    const newConfig: VerificationConfig = {
      ...store.verificationConfig,
      mode
    }
    const result = await knowledgeRepository.updateVerificationConfig(
      newConfig
    )
    store.setVerificationConfig(result.config || newConfig)
    logger.info('Verification mode set to: %s', mode)
  } catch (error) {
    logger.error('Failed to update verification config: %s', error)
  } finally {
    configLoading.value = false
  }
}

// Bulk operations
async function bulkApprove() {
  if (selection.selectedCount.value === 0) return
  bulkProcessing.value = true
  try {
    const ids = [...selection.selected.value]
    const results = await Promise.allSettled(
      ids.map(id =>
        knowledgeRepository.approveSource(id, currentUser.value)
      )
    )
    let approved = 0
    results.forEach((result, index) => {
      if (result.status === 'fulfilled') {
        store.removePendingSource(ids[index])
        approved++
      }
    })
    todayApproved.value += approved
    selection.clear()
    logger.info('Bulk approved %d sources', approved)
  } catch (error) {
    logger.error('Bulk approve failed: %s', error)
  } finally {
    bulkProcessing.value = false
  }
}

async function bulkReject() {
  if (selection.selectedCount.value === 0) return
  bulkProcessing.value = true
  try {
    const ids = [...selection.selected.value]
    const results = await Promise.allSettled(
      ids.map(id =>
        knowledgeRepository.rejectSource(id, currentUser.value, false)
      )
    )
    let rejected = 0
    results.forEach((result, index) => {
      if (result.status === 'fulfilled') {
        store.removePendingSource(ids[index])
        rejected++
      }
    })
    todayRejected.value += rejected
    selection.clear()
    logger.info('Bulk rejected %d sources', rejected)
  } catch (error) {
    logger.error('Bulk reject failed: %s', error)
  } finally {
    bulkProcessing.value = false
  }
}

// Pagination
function goToPage(page: number) {
  currentPage.value = page
  selection.clear()
  loadPendingVerifications()
}

// Formatting helpers
function formatSourceType(type: string): string {
  const typeMap: Record<string, string> = {
    manual_upload: t('knowledge.verification.typeUpload'),
    url_fetch: t('knowledge.verification.typeUrl'),
    web_research: t('knowledge.verification.typeResearch'),
    connector: t('knowledge.verification.typeConnector')
  }
  return typeMap[type] || type
}

function formatTimestamp(timestamp: string): string {
  return formatDate(new Date(timestamp))
}

function truncateContent(content: string): string {
  if (content.length <= 200) return content
  return content.substring(0, 200) + '...'
}

// Lifecycle
onMounted(() => {
  loadPendingVerifications()
  loadVerificationConfig()
})
</script>

<style scoped>
.verification-queue {
  padding: var(--spacing-6);
  max-width: 960px;
}

/* Header */
.verification-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-5);
  flex-wrap: wrap;
  gap: var(--spacing-4);
}

.header-title {
  margin: var(--spacing-0);
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
  font-family: var(--font-sans);
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
}

.header-icon {
  width: 22px;
  height: 22px;
  color: var(--color-info);
  flex-shrink: 0;
}

/* Mode Toggle */
.mode-toggle {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.mode-label {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-secondary);
  font-family: var(--font-sans);
}

.mode-btn {
  padding: var(--spacing-1-5) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xs);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-size: var(--text-xs);
  font-weight: 500;
  font-family: var(--font-sans);
  cursor: pointer;
  transition: all var(--duration-150) var(--ease-in-out);
}

.mode-btn:hover:not(:disabled) {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.mode-btn.active {
  background: var(--color-info-bg);
  color: var(--color-info);
  border-color: var(--color-info);
}

.mode-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Stats Bar */
.stats-bar {
  display: flex;
  gap: var(--spacing-4);
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-default);
  margin-bottom: var(--spacing-5);
  flex-wrap: wrap;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-0-5);
  min-width: 80px;
}

.stat-value {
  font-size: var(--text-xl);
  font-weight: 600;
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.stat-pending {
  color: var(--color-warning);
}

.stat-approved {
  color: var(--color-success);
}

.stat-rejected {
  color: var(--color-error);
}

.stat-label {
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-family: var(--font-sans);
}

/* Bulk Toolbar */
.bulk-toolbar {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3) var(--spacing-4);
  background: var(--color-info-bg);
  border: 1px solid var(--color-info);
  border-radius: var(--radius-default);
  margin-bottom: var(--spacing-4);
}

.bulk-count {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-info);
  font-family: var(--font-sans);
}

/* Loading */
.loading-state {
  text-align: center;
  padding: var(--spacing-12);
  color: var(--text-secondary);
}

.loading-state i {
  font-size: var(--text-2xl);
  margin-bottom: var(--spacing-3);
}

/* Source Cards */
.source-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.source-card {
  padding: var(--spacing-4);
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-default);
  transition: all var(--duration-150) var(--ease-in-out);
}

.source-card:hover {
  border-color: var(--border-hover, var(--border-default));
  box-shadow: var(--shadow-sm);
}

.source-card.selected {
  background: var(--color-info-bg);
  border-color: var(--color-info);
}

/* Card Header */
.card-header {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-3);
  margin-bottom: var(--spacing-2);
}

.card-checkbox {
  margin-top: var(--spacing-1);
  flex-shrink: 0;
}

.card-title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex: 1;
  min-width: 0;
  gap: var(--spacing-3);
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  font-family: var(--font-sans);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Card Meta */
.card-meta {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  margin-bottom: var(--spacing-3);
  margin-left: var(--spacing-7);
  flex-wrap: wrap;
}

.source-type-badge {
  display: inline-block;
  padding: 2px var(--spacing-2);
  border-radius: var(--radius-xs);
  font-size: var(--text-xs);
  font-weight: 500;
  font-family: var(--font-sans);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.card-domain {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  font-family: var(--font-mono);
}

.card-timestamp {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}

/* Card Content */
.card-content {
  margin: 0 0 var(--spacing-3) 28px;
  font-size: var(--text-sm);
  line-height: 1.6;
  color: var(--text-secondary);
  font-family: var(--font-sans);
}

/* Card URL */
.card-url {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  margin: 0 0 var(--spacing-3) 28px;
}

.url-icon {
  width: 14px;
  height: 14px;
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.url-link {
  font-size: var(--text-xs);
  color: var(--color-info);
  text-decoration: none;
  font-family: var(--font-mono);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.url-link:hover {
  text-decoration: underline;
  color: var(--color-info-dark);
}

/* Card Actions */
.card-actions {
  display: flex;
  gap: var(--spacing-2);
  margin-left: var(--spacing-7);
}

/* Pagination */
.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: var(--spacing-4);
  padding: var(--spacing-5) 0 var(--spacing-2);
}

.page-info {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  font-family: var(--font-sans);
}

/* Responsive */
@media (max-width: 768px) {
  .verification-header {
    flex-direction: column;
    align-items: stretch;
  }

  .mode-toggle {
    justify-content: flex-end;
  }

  .stats-bar {
    justify-content: space-around;
  }

  .bulk-toolbar {
    flex-wrap: wrap;
  }

  .card-meta {
    margin-left: var(--spacing-0);
  }

  .card-content {
    margin-left: var(--spacing-0);
  }

  .card-url {
    margin-left: var(--spacing-0);
  }

  .card-actions {
    margin-left: var(--spacing-0);
  }
}
</style>
