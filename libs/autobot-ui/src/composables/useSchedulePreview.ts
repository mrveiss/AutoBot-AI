// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// Next-run preview for the schedule picker (#18432). Shows the advisory
// client computation immediately, then REPLACES it with the server's answer
// (the same code the scheduler runs). Server absent (null / rejected / no
// function) keeps the advisory runs and flips `available` to false; that flag
// gates the picker to cron-only kinds. A server verdict of "invalid" wins.

import { onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { nextRuns } from '../schedule/nextRuns'
import type { PreviewResult, SchedulePreviewFn, ScheduleSpec } from '../schedule/types'

export type PreviewSource = 'server' | 'advisory' | 'none'
export interface PreviewError {
  code: string
  params: Record<string, unknown>
}

function createState() {
  return {
    runs: ref<Date[]>([]),
    source: ref<PreviewSource>('none'),
    error: ref<PreviewError | null>(null),
    loading: ref(false),
    /** null = not yet known; true = server answered; false = unavailable. */
    available: ref<boolean | null>(null),
  }
}
type State = ReturnType<typeof createState>

function showAdvisory(st: State, s: ScheduleSpec, count: number): void {
  const local = nextRuns(s, count)
  st.runs.value = local ?? []
  st.source.value = local ? 'advisory' : 'none'
  st.error.value = null
}

function clear(st: State): void {
  st.runs.value = []
  st.source.value = 'none'
  st.error.value = null
}

function applyServer(st: State, result: PreviewResult | null): void {
  st.loading.value = false
  st.available.value = result !== null
  if (!result) return
  if (!result.valid) {
    st.runs.value = []
    st.source.value = 'none'
    st.error.value = { code: result.error_code ?? '', params: result.error_params ?? {} }
    return
  }
  st.runs.value = result.next_runs.map((iso) => new Date(iso))
  st.source.value = 'server'
}

async function ask(fn: SchedulePreviewFn, s: ScheduleSpec, count: number): Promise<PreviewResult | null> {
  try {
    return await fn(s, count)
  } catch {
    return null // endpoint down or rejected: the advisory preview stays
  }
}

export function useSchedulePreview(
  spec: Ref<ScheduleSpec | null>,
  preview: () => SchedulePreviewFn | undefined,
  debounceMs: () => number,
  count = 3,
) {
  const st = createState()
  let seq = 0
  let timer: ReturnType<typeof setTimeout> | undefined

  async function askServer(s: ScheduleSpec, fn: SchedulePreviewFn, mine: number): Promise<void> {
    st.loading.value = true
    const result = await ask(fn, s, count)
    if (mine === seq) applyServer(st, result)
  }

  function refresh(): void {
    const mine = ++seq
    clearTimeout(timer)
    const s = spec.value
    const fn = preview()
    if (!fn) st.available.value = false
    if (!s) return clear(st)
    showAdvisory(st, s, count)
    if (!fn) return
    const wait = debounceMs()
    if (wait <= 0) void askServer(s, fn, mine)
    else timer = setTimeout(() => void askServer(s, fn, mine), wait)
  }

  watch(spec, refresh, { immediate: true, deep: true })
  onBeforeUnmount(() => clearTimeout(timer))
  return { ...st, refresh }
}
