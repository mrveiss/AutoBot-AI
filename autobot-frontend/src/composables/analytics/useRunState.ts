// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Composable: useRunState (#21003)
 *
 * How the newest indexing run of the selected source ended. A run that was
 * killed keeps the findings it had stored, and those are shown on the page as
 * partial results: the backend labels every results route with `partial` and
 * `run`, and `GET /index/run-state` answers the same question on its own.
 *
 * ONE state serves the page. It is fed from two places that carry the same
 * truth: the `run` field already arriving on the stats and problems bodies
 * (`applyRunFields`, no extra request) and the run-state route (`loadRunState`),
 * which covers a source whose stats body carries no data and the moment a job
 * ends. The notice component reads it by injection.
 */

import { getCurrentInstance, inject, provide, ref, watch, type InjectionKey, type Ref } from 'vue'
import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useRunState')

/** `running` | `completed` | `failed` | `killed` | `abandoned` | `cancelled`; empty string = none. */
export interface CodebaseRunState {
  run_id: string
  status: string
  partial: boolean
  reason: string
  started_at: string
  finished_at: string
  last_completed_at: string
}

/** The fields every results route and the run-state route add to their body (#21003). */
interface RunBodyFields {
  partial?: boolean
  run?: CodebaseRunState | null
}

export interface RunStateHandle {
  /** `null` = no run record (data indexed before records existed): nothing says the results are partial. */
  run: Ref<CodebaseRunState | null>
  /**
   * The last run-state read of the selected source failed, and nothing has answered since: `run`
   * is then what was known before (or `null`), NOT "no run record". Cleared by the next answer.
   */
  readFailed: Ref<boolean>
  /**
   * Take the `run` field off a results body; a body without the field changes nothing.
   * `forSource` is the source key the request was made for (default: the current one): a
   * response for a source that is no longer selected is dropped. A `running` snapshot of a run
   * already known to have ended is dropped too: the first terminal status of a run is final.
   */
  applyRunFields: (body: unknown, forSource?: string) => void
  /** Read the run state; also the retry after a failed read. */
  loadRunState: () => Promise<void>
}

export const RUN_STATE_KEY: InjectionKey<RunStateHandle> = Symbol('codebase-run-state')

/**
 * How a job that has left the task slot ended, read off the run record (a run's id is its task
 * id). `null` when the record does not say: no record, a run still `running`, or the record of
 * another run than `taskId` (`null` = the job's id was never seen, so the newest run is taken).
 * `killed` and `abandoned` are failures to the job poller; their reason is the error.
 */
export function endedRunOutcome(
  run: CodebaseRunState | null,
  taskId: string | null,
): { status: string; error?: string } | null {
  if (!run || !run.status || run.status === 'running') return null
  if (taskId && run.run_id !== taskId) return null
  if (run.status === 'completed' || run.status === 'cancelled') return { status: run.status }
  return { status: 'failed', error: run.reason || run.status }
}

/**
 * Create the page's run state and offer it to the components below the caller.
 *
 * `currentSource` names the selected source (any stable key; '' = none). When it changes the
 * previous source's run is dropped and the new source's is read.
 */
export function useRunState(withSourceId: (url: string) => string, currentSource: () => string): RunStateHandle {
  const run = ref<CodebaseRunState | null>(null)
  const readFailed = ref(false)

  const applyRunFields = (body: unknown, forSource: string = currentSource()) => {
    if (forSource !== currentSource()) return
    if (body && typeof body === 'object' && 'run' in body) {
      const incoming = (body as RunBodyFields).run ?? null
      const known = run.value
      // The requests are not ordered: a snapshot taken while the run was going can arrive last.
      const staleRunning = !!known && !!incoming && known.run_id === incoming.run_id &&
        known.status !== 'running' && incoming.status === 'running'
      if (!staleRunning) run.value = incoming
      if (incoming) readFailed.value = false // `run: null` on a results body may itself be a failed label read
    }
  }

  const endpoint = useFetchEndpoint<RunBodyFields, CodebaseRunState, string>(
    {
      path: '/api/analytics/codebase/index/run-state',
      scopeToSource: true,
      requireSource: true,
      label: 'Index run state',
      pickData: (raw) => raw.run ?? null,
      onSuccess: (_run, raw, forSource) => applyRunFields(raw, forSource),
      onNoData: (forSource) => {
        if (forSource !== currentSource()) return
        run.value = null
        readFailed.value = false
      },
      onError: (message, _err, forSource) => {
        logger.warn(`Run state not read: ${message}`)
        if (forSource === currentSource()) readFailed.value = true
      },
    },
    { withSourceId },
  )

  const loadRunState = () => endpoint.load(undefined, currentSource())
  watch(currentSource, () => {
    run.value = null
    readFailed.value = false
    void loadRunState()
  })

  const handle: RunStateHandle = { run, readFailed, applyRunFields, loadRunState }
  if (getCurrentInstance()) provide(RUN_STATE_KEY, handle)
  return handle
}

/** The run state a parent provided, or `null` when the component is mounted without one. */
export function injectRunState(): RunStateHandle | null {
  return inject(RUN_STATE_KEY, null)
}
