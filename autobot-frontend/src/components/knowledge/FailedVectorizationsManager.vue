<template>
  <div class="failed-vectorizations-manager">
    <div class="manager-header">
      <h3>
        <Icon name="exclamation-triangle" />
        {{ $t('knowledge.failedVectorizations.title') }}
      </h3>
      <div class="header-actions">
        <BaseButton
          variant="primary"
          size="sm"
          @click="refreshFailedJobs"
          :disabled="loading"
          :loading="loading"
          class="btn-refresh"
        >
          <Icon name="sync-alt" v-if="!loading" />
          {{ $t('knowledge.failedVectorizations.refresh') }}
        </BaseButton>
        <BaseButton
          v-if="failedJobs.length > 0"
          variant="error"
          size="sm"
          @click="clearAllFailed"
          :disabled="loading"
          class="btn-clear-all"
        >
          <Icon name="trash-alt" />
          {{ $t('knowledge.failedVectorizations.clearAll') }}
        </BaseButton>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading && failedJobs.length === 0" class="loading-state">
      <Icon name="spinner" class="animate-spin" />
      {{ $t('knowledge.failedVectorizations.loadingJobs') }}
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="error-state">
      <Icon name="exclamation-circle" />
      {{ error }}
    </div>

    <!-- Empty State -->
    <EmptyState
      v-else-if="failedJobs.length === 0"
      icon="check-circle"
      :message="$t('knowledge.failedVectorizations.noFailedJobs')"
      variant="success"
    />

    <!-- Failed Jobs List -->
    <div v-else class="failed-jobs-list">
      <div v-for="job in failedJobs" :key="job.job_id" class="failed-job-card">
        <div class="job-header">
          <div class="job-id">
            <Icon name="file-alt" />
            <span class="fact-id">{{ job.fact_id.substring(0, 8) }}...</span>
          </div>
          <div class="job-time">
            {{ formatTime(job.started_at) }}
          </div>
        </div>

        <div class="job-error">
          <Icon name="times-circle" />
          {{ job.error || $t('knowledge.failedVectorizations.unknownError') }}
        </div>

        <div class="job-actions">
          <BaseButton
            variant="success"
            size="sm"
            @click="retryJob(job.job_id)"
            :disabled="loading || retryingJobs.has(job.job_id)"
            :loading="retryingJobs.has(job.job_id)"
            class="btn-retry"
          >
            <Icon name="redo" v-if="!retryingJobs.has(job.job_id)" />
            {{ retryingJobs.has(job.job_id) ? $t('knowledge.failedVectorizations.retrying') : $t('knowledge.failedVectorizations.retryBtn') }}
          </BaseButton>
          <BaseButton
            variant="secondary"
            size="sm"
            @click="deleteJob(job.job_id)"
            :disabled="loading"
            class="btn-delete"
          >
            <Icon name="trash" />
            {{ $t('knowledge.failedVectorizations.deleteBtn') }}
          </BaseButton>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { formatDateTime } from '@/utils/formatHelpers'
import { useKnowledgeVectorization } from '@/composables/knowledge/useKnowledgeVectorization'
import EmptyState from '@/components/ui/EmptyState.vue'
import BaseButton from '@/components/base/BaseButton.vue'

const { t } = useI18n()

const {
  failedJobs,
  retryingJobs,
  isLoading: loading,
  error,
  refreshFailedJobs,
  retryJob: retryJobBase,
  deleteJob: deleteJobBase,
  clearAllFailed: clearAllFailedBase,
} = useKnowledgeVectorization()

// Delete a single job — confirm before delegating to composable
const deleteJob = async (jobId: string) => {
  if (!confirm(t('knowledge.failedVectorizations.confirmDelete'))) {
    return
  }
  await deleteJobBase(jobId)
}

// Clear all failed jobs — confirm before delegating to composable
const clearAllFailed = async () => {
  if (!confirm(t('knowledge.failedVectorizations.confirmClearAll', { count: failedJobs.value.length }))) {
    return
  }
  await clearAllFailedBase()
}

const retryJob = retryJobBase

// Use shared datetime formatting utility
const formatTime = formatDateTime

// Load on mount
onMounted(() => {
  refreshFailedJobs()
})
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.failed-vectorizations-manager {
  background: var(--bg-primary);
  border-radius: var(--radius-lg);
  padding: var(--spacing-6);
  box-shadow: var(--shadow-sm);
}

.manager-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-6);
  padding-bottom: var(--spacing-4);
  border-bottom: 2px solid var(--border-default);
}

.manager-header h3 {
  margin: var(--spacing-0);
  font-size: var(--text-xl);
  color: var(--color-error);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.header-actions {
  display: flex;
  gap: var(--spacing-3);
}

/* Button spacing handled by BaseButton */

.loading-state,
.error-state {
  text-align: center;
  padding: var(--spacing-8) var(--spacing-4);
  color: var(--text-secondary);
}

.loading-state i,
.error-state i {
  font-size: var(--text-4xl);
  margin-bottom: var(--spacing-4);
  display: block;
}

.error-state {
  color: var(--color-error);
}

.failed-jobs-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

.failed-job-card {
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  transition: all var(--duration-200);
}

.failed-job-card:hover {
  box-shadow: var(--shadow-md);
}

.job-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-3);
}

.job-id {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.fact-id {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  background: var(--bg-primary);
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-sm);
}

.job-time {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.job-error {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-2);
  padding: var(--spacing-3);
  background: var(--bg-primary);
  border-radius: var(--radius-md);
  margin-bottom: var(--spacing-4);
  font-size: var(--text-sm);
  color: var(--color-error);
}

.job-error i {
  flex-shrink: 0;
  margin-top: var(--spacing-px);
}

.job-actions {
  display: flex;
  gap: var(--spacing-2);
}

/* Button styling handled by BaseButton component */
</style>
