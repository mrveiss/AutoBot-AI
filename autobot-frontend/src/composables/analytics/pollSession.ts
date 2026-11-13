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
 */
export interface PollSession {
  /** End the current session: every guard taken before this call reports stale. */
  renew: () => void
  /** Take a guard for the session as it is now; it returns true once the session has ended. */
  guard: () => () => boolean
}

export function createPollSession(): PollSession {
  let generation = 0
  return {
    renew: () => {
      generation += 1
    },
    guard: () => {
      const mine = generation
      return () => mine !== generation
    },
  }
}
