<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0
  AutoBot - AI-Powered Automation Platform
  Author: mrveiss

  #21003: findings stored by a run that did not finish are shown, never hidden, and this says
  so: how the newest run ended, that the findings are partial, and when the last run that did
  finish completed. A run still in progress is "updating", not a failure. Shown when the
  backend flags the run `partial`; nothing without a run record (data indexed before records
  existed) and nothing for a completed run.
-->
<template>
  <BaseAlert
    v-if="run && run.partial"
    :variant="isRunning ? 'info' : 'warning'"
    :title="isRunning ? t('analytics.codebase.runState.runningTitle') : t('analytics.codebase.runState.partialTitle')"
    bordered
    data-testid="run-state-notice"
  >
    <p v-for="line in lines" :key="line">{{ line }}</p>
  </BaseAlert>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseAlert } from '@autobot/ui'
import { createDateFormatter } from '@/utils/formatHelpers'
import { injectRunState } from '@/composables/analytics/useRunState'

const { t, locale } = useI18n()
const runState = injectRunState()
const run = computed(() => runState?.run.value ?? null)
const formatWhen = createDateFormatter({ locale: () => locale.value })

const isRunning = computed(() => run.value?.status === 'running')

const statusLabels = computed<Record<string, string>>(() => ({
  failed: t('analytics.codebase.runState.status.failed'),
  killed: t('analytics.codebase.runState.status.killed'),
  abandoned: t('analytics.codebase.runState.status.abandoned'),
  cancelled: t('analytics.codebase.runState.status.cancelled'),
}))

// An empty status never reads "ended as ." (#21003).
const endedLine = (status: string, reason: string): string => {
  if (!status) {
    return reason
      ? t('analytics.codebase.runState.unfinishedWithReason', { reason })
      : t('analytics.codebase.runState.unfinished')
  }
  return reason
    ? t('analytics.codebase.runState.endedWithReason', { status, reason })
    : t('analytics.codebase.runState.ended', { status })
}

const lines = computed(() => {
  const current = run.value
  if (!current) return []
  const out: string[] = []
  if (isRunning.value) {
    out.push(t('analytics.codebase.runState.running'))
  } else {
    const status = statusLabels.value[current.status] ?? current.status
    out.push(endedLine(status, current.reason))
    out.push(t('analytics.codebase.runState.partialFindings'))
  }
  out.push(
    current.last_completed_at
      ? t('analytics.codebase.runState.lastCompleted', { when: formatWhen(current.last_completed_at) })
      : t('analytics.codebase.runState.neverCompleted'),
  )
  return out
})
</script>
