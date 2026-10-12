// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// User-facing messages of the schedule picker (#18432): server/client error
// codes → i18n keys, and the preview status note. Keys only; the app owns text.

import { computed, type Ref } from 'vue'
import type { PreviewError, PreviewSource } from './useSchedulePreview'

export const KNOWN_ERROR_CODES = [
  'schedule.cron_extension_unsupported', 'schedule.invalid_timezone', 'schedule.once_in_past',
  'schedule.invalid_rrule', 'schedule.invalid_cron', 'schedule.conflicting_fields',
]

interface PreviewView {
  loading: Ref<boolean>
  source: Ref<PreviewSource>
  runs: Ref<Date[]>
}

type T = (key: string, params?: Record<string, unknown>) => string

export function useScheduleMessages(t: T, error: Ref<PreviewError | null>, pv: PreviewView) {
  const errorText = computed(() => {
    const e = error.value
    if (!e) return ''
    return t(KNOWN_ERROR_CODES.includes(e.code) ? e.code : 'schedule.invalid_generic', e.params)
  })
  const previewNote = computed(() => {
    if (pv.loading.value) return t('schedule.previewLoading')
    if (pv.source.value === 'advisory') return t('schedule.previewApprox')
    const none = pv.runs.value.length === 0 && pv.source.value === 'none'
    return none && !error.value ? t('schedule.previewUnavailable') : ''
  })
  return { errorText, previewNote }
}
