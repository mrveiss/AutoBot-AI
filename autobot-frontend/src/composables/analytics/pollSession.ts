// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * A poll session (#20513): the span in which what a poll learned still describes the page.
 *
 * `usePollingJob.stop()` and `useApiResource.refresh()` only drop their own result; the caller
 * that awaited them resumes anyway and writes into shared refs. A source switch (or a restart of
 * polling) ends the session with `renew()`; every async function takes a guard BEFORE its first
 * `await` and writes nothing after it once the guard reports stale.
 *
 * A session that waits for a queued request (one with no task id yet) also notes the newest run
 * id known when the wait began (#21003): if the wait ends with no job ever seen, a run record
 * still naming that run is the run BEFORE the request, not the request's own outcome.
 */
export interface PollSession {
  /** End the current session: every guard taken before this call reports stale, and the wait note is dropped. */
  renew: () => void
  /** Take a guard for the session as it is now; it returns true once the session has ended. */
  guard: () => () => boolean
  /** Note the newest run id known while waiting for a queued request; the first id noted in a session is kept. */
  noteWait: (runId: string | null) => void
  /** The run id noted for this session's wait, or `null` when none was known (or nothing waited). */
  waitBaseline: () => string | null
}

export function createPollSession(): PollSession {
  let generation = 0
  let baseline: string | null = null
  return {
    renew: () => {
      generation += 1
      baseline = null
    },
    noteWait: (runId) => {
      baseline ??= runId
    },
    waitBaseline: () => baseline,
    guard: () => {
      const mine = generation
      return () => mine !== generation
    },
  }
}
