// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// Expert (Advanced) mode of the schedule picker (#18432): edits standard
// 5-field cron ONLY. Text is accepted — i.e. emitted as the new spec — only
// when it validates: the server preview when one exists, the client's
// 5-field parse otherwise. Extensions (5L, 1#2, W, ?) are refused with the
// token named and a pointer to the picker.

import { ref } from 'vue'
import { parseCron5 } from '../schedule/cronFields'
import type { PreviewError } from './useSchedulePreview'
import type { SchedulePreviewFn, ScheduleSpec } from '../schedule/types'

const NAMES = /MON|TUE|WED|THU|FRI|SAT|SUN|JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC/gi

/** Client-side refusal with a stable code, or null when the text may pass. */
export function cronProblem(text: string): PreviewError | null {
  const fields = text.trim().split(/\s+/)
  if (fields.length !== 5) return { code: 'schedule.invalid_cron', params: {} }
  const token = fields.find((f) => /[LW#?]/i.test(f.replace(NAMES, '')))
  if (token) return { code: 'schedule.cron_extension_unsupported', params: { token } }
  return parseCron5(text) ? null : { code: 'schedule.invalid_cron', params: {} }
}

async function serverVerdict(fn: SchedulePreviewFn | undefined, spec: ScheduleSpec): Promise<PreviewError | null> {
  if (!fn) return null
  try {
    const res = await fn(spec, 1)
    if (res && !res.valid) return { code: res.error_code ?? '', params: res.error_params ?? {} }
  } catch {
    // preview unavailable: the client 5-field parse already passed
  }
  return null
}

export function useScheduleExpert(
  zone: () => string,
  preview: () => SchedulePreviewFn | undefined,
  accept: (spec: ScheduleSpec) => void,
) {
  const open = ref(false)
  const editing = ref(false)
  const text = ref('')
  const error = ref<PreviewError | null>(null)
  let seq = 0

  async function onInput(value: string): Promise<void> {
    text.value = value
    const mine = ++seq
    error.value = cronProblem(value)
    if (error.value) return
    const spec: ScheduleSpec = { kind: 'cron', timezone: zone(), cron: value.trim() }
    const verdict = await serverVerdict(preview(), spec)
    if (mine !== seq) return
    error.value = verdict
    if (!verdict) accept(spec)
  }

  function startEditing(current: string): void {
    open.value = true
    editing.value = true
    text.value = current
    error.value = null
  }

  function stopEditing(): void {
    editing.value = false
    error.value = null
    seq++
  }

  return { open, editing, text, error, onInput, startEditing, stopEditing }
}
