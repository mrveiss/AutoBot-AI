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

    <div class="mb-3 flex flex-col gap-1 text-autobot-text-secondary">
      <span>{{ t('batchJobs.progress', { value: job.progress }) }}</span>
      <!-- Native <progress>: the kit has no progress primitive yet (#21662). -->
      <progress class="w-full" :value="job.progress" max="100" :aria-label="t('batchJobs.progressLabel', { name: job.name })" />
    </div>

    <dl class="mb-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
      <div>
        <dt class="text-autobot-text-muted">{{ t('batchJobs.created') }}</dt>
        <dd class="m-0 text-autobot-text-primary">{{ formatDateTime(job.created_at) || t('batchJobs.notReported') }}</dd>
      </div>
      <div>
        <dt class="text-autobot-text-muted">{{ t('batchJobs.started') }}</dt>
        <dd class="m-0 text-autobot-text-primary">{{ formatDateTime(job.started_at) || t('batchJobs.notStarted') }}</dd>
      </div>
      <div>
        <dt class="text-autobot-text-muted">{{ t('batchJobs.duration') }}</dt>
        <dd class="m-0 text-autobot-text-primary">{{ job.started_at ? formatDuration(job.started_at, job.completed_at ?? null) : t('batchJobs.notStarted') }}</dd>
      </div>
    </dl>

    <BaseAlert v-if="job.error_message" variant="error" :message="job.error_message" />

    <div class="flex justify-end gap-2">
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
