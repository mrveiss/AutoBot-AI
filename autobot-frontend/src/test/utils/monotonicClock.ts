// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * A `Date.now()` that never runs backwards, for the test environment (#18254).
 *
 * Vue's DOM event invoker discards a handler when the event's `Date.now()`
 * stamp is not later than the listener's attach stamp (runtime-dom
 * `createInvoker`: `e._vts <= invoker.attached`). This host's wall clock STEPS
 * BACKWARDS under load -- WSL2 time correction, measured at 2 steps of up to
 * 1.76 s in 45 s -- so a click that straddles a step is silently dropped. That
 * is the "clicked and nothing happened" flake family: OrgChart view switches,
 * WorkflowCanvas undo, the schedule picker's Advanced toggle. A 2 s step
 * between two clicks reproduces it on every run with no load at all.
 *
 * The fix keeps an offset rather than clamping: when the wall clock steps back,
 * the offset absorbs the step and time continues forward from where it was.
 * A clamp would instead freeze time for the length of the step, and equal
 * stamps trip the same `<=` guard.
 *
 * Fake timers are unaffected: `vi.useFakeTimers()` replaces `Date` itself.
 */

/** A source of wall-clock milliseconds; injectable so a test can step it back. */
export type WallClock = () => number

/** Wrap `wall` so successive readings never decrease. */
export function monotonic(wall: WallClock): WallClock {
  let offset = 0
  let last = -Infinity
  return () => {
    let now = wall() + offset
    if (now < last) {
      offset += last - now
      now = last
    }
    last = now
    return now
  }
}

/** Replace `Date.now` with a monotonic reading of the current one. Returns the restore. */
export function installMonotonicDateNow(): () => void {
  const original = Date.now
  Date.now = monotonic(original.bind(Date))
  return () => {
    Date.now = original
  }
}
