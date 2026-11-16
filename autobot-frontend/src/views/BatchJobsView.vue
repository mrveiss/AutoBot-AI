<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!--
  BatchJobsView — Batch Processing, moved here from the SLM console (#20644).
  Lists the signed-in user's batch jobs (the backend scopes them to their owner, #21650), with counts by
  status, a status filter, create, retry (run again) and remove. Loading, a failed load, and an empty
  list each have their own state, so an outage never reads as "no jobs".
-->
<template>
  <div class="flex flex-col gap-4 p-6">
    <PageHeader :title="t('batchJobs.title')" :subtitle="t('batchJobs.subtitle')">
      <template #actions>
        <BaseButton variant="ghost" :loading="state.loading.value" @click="state.loadJobs()">
          {{ t('batchJobs.refresh') }}
        </BaseButton>
        <BaseButton @click="openCreate">{{ t('batchJobs.newJob') }}</BaseButton>
      </template>
    </PageHeader>

    <div class="grid grid-cols-2 gap-3 md:grid-cols-5" data-testid="batch-counts">
      <BaseCard v-for="count in counts" :key="count.key" size="sm">
        <p class="m-0 text-sm text-autobot-text-muted">{{ t(`batchJobs.counts.${count.key}`) }}</p>
        <p class="m-0 text-lg font-semibold text-autobot-text-primary">{{ count.value }}</p>
      </BaseCard>
    </div>

    <div class="max-w-xs">
      <BaseSelectMenu
        :model-value="state.filter.value.status ?? 'all'"
        :options="statusOptions"
        :label="t('batchJobs.filterLabel')"
        @update:model-value="filterBy"
      />
    </div>

    <BaseAlert v-if="actionError" variant="error" :message="actionError" data-testid="batch-action-error" />

    <div v-if="state.jobsView.value === 'loading'" class="flex justify-center p-6" data-testid="batch-loading">
      <BaseSpinner :label="t('batchJobs.loading')" />
    </div>
    <EmptyState
      v-else-if="state.jobsView.value === 'error'"
      :title="t('batchJobs.loadFailed')"
      :description="httpErrorText(state.error.value, t('batchJobs.loadFailedDetail'))"
      data-testid="batch-error"
    >
      <template #actions>
        <BaseButton @click="state.loadJobs()">{{ t('batchJobs.tryAgain') }}</BaseButton>
      </template>
    </EmptyState>
    <EmptyState
      v-else-if="state.jobsView.value === 'empty' && activeStatus"
      :title="t(`batchJobs.emptyFiltered.${activeStatus}`)"
      :description="t('batchJobs.emptyFilteredDetail')"
      data-testid="batch-empty-filtered"
    >
      <template #actions>
        <BaseButton @click="state.clearFilter()">{{ t('batchJobs.clearFilter') }}</BaseButton>
      </template>
    </EmptyState>
    <EmptyState
      v-else-if="state.jobsView.value === 'empty'"
      :title="t('batchJobs.empty')"
      :description="t('batchJobs.emptyDetail')"
      data-testid="batch-empty"
    />
    <div v-else class="flex flex-col gap-3" data-testid="batch-list">
      <BatchJobCard
        v-for="job in state.jobs.value"
        :key="job.job_id"
        :job="job"
        :busy="busy"
        @run="retryJob"
        @remove="removeJob"
      />
    </div>

    <BatchCreateJobModal v-model="createOpen" :busy="busy" :error="createError" @create="createJob" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseAlert, BaseButton, BaseCard, BaseSelectMenu, BaseSpinner, EmptyState, PageHeader, httpErrorText } from '@autobot/ui'
import BatchJobCard from '@/components/batch/BatchJobCard.vue'
import BatchCreateJobModal from '@/components/batch/BatchCreateJobModal.vue'
import { useBatchJobsScreen } from '@/composables/useBatchJobsScreen'

const { t } = useI18n()
const { state, busy, actionError, createOpen, createError, openCreate, createJob, retryJob, removeJob, filterBy } =
  useBatchJobsScreen()

const STATUSES = ['pending', 'running', 'completed', 'failed', 'cancelled'] as const

/** The status filter in force, if any: an empty answer under it is not "no jobs at all". */
const activeStatus = computed(() => state.filter.value.status)

const statusOptions = computed(() => [
  { value: 'all', label: t('batchJobs.filterAll') },
  ...STATUSES.map((value) => ({ value, label: t(`batchJobs.status.${value}`) })),
])

/** Counts are over every job the caller owns, by status, as the backend reports them. */
const counts = computed(() => [
  { key: 'total', value: Object.values(state.statusCounts.value).reduce((sum, n) => sum + n, 0) },
  { key: 'pending', value: state.pendingCount.value },
  { key: 'running', value: state.runningCount.value },
  { key: 'completed', value: state.completedCount.value },
  { key: 'failed', value: state.failedCount.value },
])
</script>
