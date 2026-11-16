// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The Batch Processing screen's behaviour (#20644), on the one batch client, useBatchProcessing.
 *
 * Loads report through the client's own error refs (`jobsView` keeps loading, error and empty
 * apart). Mutations reject (#21649), so each action here catches its failure and shows it as
 * `actionError` instead of losing it. The backend scopes jobs to their owner (#21650): an
 * ordinary user sees and acts on their own jobs only.
 */
import { onMounted, onScopeDispose, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { httpErrorText } from '@autobot/ui'
import { useBatchProcessingState } from '@/composables/useBatchProcessing'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { createLogger } from '@/utils/debugUtils'
import type { BatchJob, BatchJobStatus, CreateBatchJobRequest } from '@/types/batch-processing'

const logger = createLogger('useBatchJobsScreen')

/** How often the list refreshes while a job is pending or running. */
export const BATCH_POLL_INTERVAL_MS = 5000

/** One in-flight action at a time; its failure is kept for the screen to show. */
function useActionRunner() {
  const { t } = useI18n()
  const busy = ref(false)
  const actionError = ref<string | null>(null)

  async function run(action: () => Promise<unknown>, failureKey: string): Promise<boolean> {
    busy.value = true
    actionError.value = null
    try {
      await action()
      return true
    } catch (err) {
      logger.error('Batch action failed:', err)
      actionError.value = httpErrorText(err, t(failureKey))
      return false
    } finally {
      busy.value = false
    }
  }

  return { busy, actionError, run }
}

/** Create-dialog state: open, and the create failure shown inside it. */
function useCreateDialog(state: ReturnType<typeof useBatchProcessingState>, runner: ReturnType<typeof useActionRunner>) {
  const createOpen = ref(false)
  const createError = ref<string | null>(null)

  function openCreate(): void {
    createError.value = null
    createOpen.value = true
  }

  async function createJob(request: CreateBatchJobRequest): Promise<void> {
    const ok = await runner.run(() => state.createJob(request), 'batchJobs.errors.create')
    if (ok) createOpen.value = false
    else createError.value = runner.actionError.value
  }

  return { createOpen, createError, openCreate, createJob }
}

export function useBatchJobsScreen() {
  const { t } = useI18n()
  const { confirm } = useConfirmDialog()
  const state = useBatchProcessingState()
  const runner = useActionRunner()
  const dialog = useCreateDialog(state, runner)

  const retryJob = (jobId: string) => runner.run(() => state.runJob(jobId), 'batchJobs.errors.retry')

  async function removeJob(job: BatchJob): Promise<void> {
    const active = job.status === 'pending' || job.status === 'running'
    const ok = await confirm({
      title: t(active ? 'batchJobs.confirm.cancelTitle' : 'batchJobs.confirm.removeTitle'),
      message: t('batchJobs.confirm.message', { name: job.name }),
    })
    if (ok) await runner.run(() => state.deleteJob(job.job_id), 'batchJobs.errors.remove')
  }

  const filterBy = (status: string) =>
    state.setFilter({ status: status === 'all' ? undefined : (status as BatchJobStatus) })

  onMounted(() => {
    void state.loadJobs()
    state.startPolling(BATCH_POLL_INTERVAL_MS)
  })
  onScopeDispose(() => state.stopPolling())

  return { state, ...runner, ...dialog, retryJob, removeJob, filterBy }
}
