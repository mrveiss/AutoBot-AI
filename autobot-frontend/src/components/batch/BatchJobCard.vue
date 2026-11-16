<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!--
  BatchJobCard — one batch job: status, progress, timing and the actions its status allows (#20644).
  A failed job offers Retry (it is run again, POST /batch-jobs/{id}/run). A pending or running job
  offers "Cancel and remove": the backend's only cancel is DELETE, which also removes the job.
  A finished job offers Remove. The card only emits; the screen performs the call and reports a failure.
-->
<template>
  <BaseCard :title="job.name" :subtitle="t('batchJobs.typeAndId', { type: typeLabel, id: job.job_id.slice(0, 8) })">
    <template #actions>
      <BaseBadge :variant="statusVariant" :label="t(`batchJobs.status.${job.status}`)" />
    </template>

    <div class="batch-job__progress">
      <span>{{ t('batchJobs.progress', { value: job.progress }) }}</span>
      <progress :value="job.progress" max="100" :aria-label="t('batchJobs.progressLabel', { name: job.name })" />
    </div>

    <dl class="batch-job__facts">
      <div>
        <dt>{{ t('batchJobs.created') }}</dt>
        <dd>{{ formatDateTime(job.created_at) || t('batchJobs.notReported') }}</dd>
      </div>
      <div>
        <dt>{{ t('batchJobs.started') }}</dt>
        <dd>{{ formatDateTime(job.started_at) || t('batchJobs.notStarted') }}</dd>
      </div>
      <div>
        <dt>{{ t('batchJobs.duration') }}</dt>
        <dd>{{ job.started_at ? formatDuration(job.started_at, job.completed_at ?? null) : t('batchJobs.notStarted') }}</dd>
      </div>
    </dl>

    <BaseAlert v-if="job.error_message" variant="error" :message="job.error_message" />

    <div class="batch-job__actions">
      <BaseButton v-if="job.status === 'failed'" size="sm" :disabled="busy" @click="emit('run', job.job_id)">
        {{ t('batchJobs.retry') }}
      </BaseButton>
      <BaseButton v-if="isActive" size="sm" variant="error" :disabled="busy" @click="emit('remove', job)">
        {{ t('batchJobs.cancelAndRemove') }}
      </BaseButton>
      <BaseButton v-else size="sm" variant="ghost" :disabled="busy" @click="emit('remove', job)">
        {{ t('batchJobs.remove') }}
      </BaseButton>
    </div>
  </BaseCard>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseAlert, BaseBadge, BaseButton, BaseCard, formatDateTime, formatDuration } from '@autobot/ui'
import type { BatchJob, BatchJobStatus } from '@/types/batch-processing'

const props = defineProps<{ job: BatchJob; busy?: boolean }>()
const emit = defineEmits<{ run: [jobId: string]; remove: [job: BatchJob] }>()
const { t } = useI18n()

const STATUS_VARIANT: Record<BatchJobStatus, 'neutral' | 'info' | 'success' | 'error' | 'warning'> = {
  pending: 'neutral',
  running: 'info',
  completed: 'success',
  failed: 'error',
  cancelled: 'warning',
}

const statusVariant = computed(() => STATUS_VARIANT[props.job.status])
const typeLabel = computed(() => t(`batchJobs.type.${props.job.job_type}`))
const isActive = computed(() => props.job.status === 'pending' || props.job.status === 'running')
</script>

<style scoped>
.batch-job__progress {
  display: flex;
  flex-direction: column;
  gap: var(--aui-space-1);
  margin-bottom: var(--aui-space-3);
  color: var(--aui-color-text-muted);
}

.batch-job__progress progress {
  width: 100%;
}

.batch-job__facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
  gap: var(--aui-space-3);
  margin: 0 0 var(--aui-space-3);
}

.batch-job__facts dt {
  color: var(--aui-color-text-muted);
}

.batch-job__facts dd {
  margin: 0;
  color: var(--aui-color-text);
}

.batch-job__actions {
  display: flex;
  gap: var(--aui-space-2);
  justify-content: flex-end;
}
</style>
