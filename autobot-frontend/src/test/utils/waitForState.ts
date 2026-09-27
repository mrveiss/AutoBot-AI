// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Wait for a component to reach a state, rather than assuming a tick got it there (#17365).
 *
 * Shared because the failure is not specific to one view. The required Unit gate
 * runs `vitest run --coverage`, v8 instrumentation slows execution, and any
 * assertion made immediately after a trigger is racing the component. When the
 * race is lost the gate reds on a PR whose author never touched the failing
 * file — #10323 first, then #17365 in two more places. Fixing each instance
 * where it appears is what made it recur; this lives somewhere every suite can
 * reach.
 *
 * TICKS, NOT TIME. `vi.waitFor`, `setTimeout` and a fixed delay are all
 * interval-based, so they pass on an idle machine and fail on a loaded one —
 * the exact property being removed. Flushing microtasks is load-independent:
 * fifty flushes cost microseconds when idle and are still fifty when busy.
 *
 * NEGATIVE ASSERTIONS DO NOT WAIT. "does not refetch", "leaves the name
 * unchanged" — there is no state to wait for, and waiting longer makes a false
 * pass MORE likely, not less. Anchor them instead: wait for the positive signal
 * that the path completed (the error text rendered, the request settled), then
 * assert the absence. Once the completion signal is observed the absence is a
 * settled fact rather than a race, which is what `waitForSettled` is for.
 */

import { nextTick } from 'vue'

/** Ticks to flush before giving up. The bound exists to fail a broken component,
 *  not to bound a slow one, so it is deliberately generous. */
export const MAX_TICKS = 50

/**
 * Flush Vue ticks until `predicate()` is true.
 *
 * @throws if still false after {@link MAX_TICKS}, naming what was awaited — a
 *   timeout that says what it wanted beats a bare assertion failure.
 */
export async function waitForTicks(
  predicate: () => boolean,
  awaited: string | (() => string),
): Promise<void> {
  for (let tick = 0; tick < MAX_TICKS; tick += 1) {
    if (predicate()) return
    await nextTick()
  }
  // Resolved HERE, not at the call. A caller interpolating observed state into
  // a plain string builds that string before the first tick, so the timeout
  // reports what was true BEFORE the wait -- the one moment that is never the
  // interesting one. These helpers exist to make timing failures legible, and a
  // diagnostic describing the pre-wait state is the same defect they are for.
  const described = typeof awaited === 'function' ? awaited() : awaited
  throw new Error(`waited ${MAX_TICKS} ticks for ${described} and it never became true`)
}

/**
 * Wait for the positive signal that a path finished, so a NEGATIVE assertion
 * after it is about a settled system rather than an unfinished one.
 *
 * Identical mechanics to {@link waitForTicks}; it exists under its own name
 * because the call site reads differently. `waitForTicks(...)` in front of
 * `expect(x).toBe(1)` says "wait for this"; `waitForSettled(...)` in front of
 * `expect(callCount).toBe(1)` says "the thing that had to happen has happened,
 * so nothing else is still coming". A reader who does not know that distinction
 * is the one who will later delete the wait as redundant.
 */
export async function waitForSettled(completed: () => boolean, signal: string): Promise<void> {
  await waitForTicks(completed, `${signal} (the completion signal a negative assertion is anchored to)`)
}
