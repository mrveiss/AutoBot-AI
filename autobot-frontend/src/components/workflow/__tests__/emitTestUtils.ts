// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Wait for an emission to arrive, rather than assuming one tick was enough (#17365).
 *
 * `await wrapper.trigger(...)` and `firePointer` each flush exactly ONE Vue tick.
 * That is enough whenever the component reacts synchronously, and not enough when
 * anything in the reaction defers — so an assertion reading `emitted()` straight
 * afterwards is racing the component. Under the full suite with `--coverage` the
 * race is lost often enough to red a required check:
 *
 *     FAIL WorkflowCanvas.contextMenu.test.ts > re-anchors and re-targets ...
 *     AssertionError: expected [ 'n1' ] to deeply equal [ 'n2' ]
 *
 * `n1` is the PREVIOUS emission — the new one had not happened yet, so `.at(-1)`
 * read the old one. Nothing about the assertion is wrong; it was made too early.
 *
 * WHY TICKS AND NOT TIME. A `setTimeout` or a fixed number of ticks trades one
 * race for another: it passes on a fast machine and fails on a loaded one, which
 * is the behaviour being removed. These wait on the STATE — the emission the test
 * is about — and give up only after a bound that exists to fail a genuinely
 * broken component rather than to hang the suite.
 *
 * WHAT THIS CANNOT FIX, stated because it is half the class. A NEGATIVE assertion
 * ("does not refetch", "leaves the contact unchanged") has no state to wait for,
 * and waiting longer makes it MORE likely to fail rather than less. Those need a
 * deterministic flush and then an assertion, not a wait — see #17365 for the
 * split.
 */

import { waitForTicks } from '@/test/utils/waitForState'

export { waitForTicks }

/** The slice of `VueWrapper` these helpers need, so they are not tied to one wrapper type. */
export interface EmitsEvents {
  emitted(event: string): unknown[] | undefined
}

/**
 * Wait until *event*'s most recent payload matches *expected*.
 *
 * The caller still asserts afterwards, deliberately: the assertion stays visible
 * in the test, and this only removes the race in front of it. If the emission
 * never matches, the throw here names the event and what was seen, which is more
 * useful than `expected [ 'n1' ] to deeply equal [ 'n2' ]` with no indication
 * that the cause was timing.
 */
export async function waitForLastEmit(
  wrapper: EmitsEvents,
  event: string,
  expected: unknown,
): Promise<void> {
  const wanted = JSON.stringify(expected)
  const seen = () => JSON.stringify(wrapper.emitted(event)?.at(-1))

  await waitForTicks(
    () => seen() === wanted,
    () => `'${event}' to last emit ${wanted} (last seen: ${seen() ?? 'nothing emitted'})`,
  )
}

/** Wait until *event* has been emitted exactly *count* times. */
export async function waitForEmitCount(wrapper: EmitsEvents, event: string, count: number): Promise<void> {
  await waitForTicks(
    () => (wrapper.emitted(event)?.length ?? 0) === count,
    () => `'${event}' to have been emitted ${count} time(s) (seen: ${wrapper.emitted(event)?.length ?? 0})`,
  )
}
