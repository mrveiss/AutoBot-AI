// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The wait helpers actually wait, and actually give up (#17365).
 *
 * These guard test infrastructure, which is worth testing for a specific reason:
 * a `waitFor` that returned immediately would make every call site pass exactly
 * as it does today, and the flake it was written to remove would come back with
 * no failing test anywhere to say the guard had stopped guarding. The helper
 * would read as protection while providing none.
 *
 * So: one test that it survives a state arriving several ticks late, and one that
 * it throws rather than hanging or silently passing when the state never arrives.
 */

import { describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import { waitForEmitCount, waitForLastEmit, waitForTicks } from './emitTestUtils'

/** A wrapper stand-in whose emission appears only after `afterTicks` flushes. */
/**
 * A component that emits after `afterTicks` REAL ticks, independently of reads.
 *
 * #17664 review: the previous version advanced its own clock inside
 * `emitted()`, so reading was what made time pass and `advance` -- which would
 * have driven it independently -- was never called. That fixture could not
 * distinguish a helper that yields to `nextTick` from one that spins in a tight
 * loop calling `emitted()`: both reach the emission, because the read IS the
 * clock. The test passed either way, which is the same vacuity that made the
 * sibling diagnostic test in this file meaningless.
 *
 * Reads are pure now. `advance()` runs concurrently on real ticks, so if the
 * helper under test never awaits, `advance` never progresses and the helper
 * times out -- which is the property these tests claim to check.
 */
function lateEmitter(event: string, payload: unknown, afterTicks: number) {
  const emissions: unknown[] = []
  const advance = async () => {
    for (let i = 0; i < afterTicks; i += 1) await nextTick()
    emissions.push(payload)
  }
  return {
    wrapper: {
      emitted: (name: string) =>
        name === event && emissions.length ? [...emissions] : undefined,
    },
    advance,
  }
}

describe('waitForTicks', () => {
  it('returns as soon as the predicate is true', async () => {
    const predicate = vi.fn(() => true)

    await waitForTicks(predicate, 'an already-true condition')

    expect(predicate).toHaveBeenCalledTimes(1)
  })

  it('keeps flushing until a late condition becomes true', async () => {
    let calls = 0
    const becomesTrueOnTheFifthLook = () => {
      calls += 1
      return calls >= 5
    }

    await waitForTicks(becomesTrueOnTheFifthLook, 'a condition true on the fifth look')

    expect(calls).toBe(5)
  })

  it('throws naming what it waited for, rather than hanging or passing', async () => {
    // The control that matters: without a throw, a never-true condition would
    // return silently and every call site would be decoration.
    await expect(waitForTicks(() => false, 'something that never happens')).rejects.toThrow(
      /waited \d+ ticks for something that never happens/,
    )
  })
})

describe('the failure diagnostic describes the END of the wait, not the start', () => {
  it('reports the last emission observed, not the one present before polling began', async () => {
    // #17664 review: both messages were plain template literals, so they were
    // built BEFORE waitForTicks ran and reported the pre-wait state. These
    // helpers exist to make a timing failure legible; a diagnostic naming the
    // one moment that is never interesting is the defect they were written for.
    //
    // The wrapper must hold its FIRST answer stable and change only afterwards.
    // An earlier version of this test mutated on every read, so the eager build
    // also saw a changed value and the test passed against the bug it targets --
    // a green that meant nothing.
    let reads = 0
    const wrapper = {
      emitted: (name: string) => {
        if (name !== 'node-selected') return undefined
        reads += 1
        return reads <= 1 ? [['before-the-wait']] : [[`during-tick-${reads}`]]
      },
    }

    const error = await waitForLastEmit(wrapper, 'node-selected', ['never-matches']).catch(
      (e: Error) => e,
    )

    expect(error).toBeInstanceOf(Error)
    // Eager interpolation reports the first read; lazy reports the last.
    expect((error as Error).message).not.toContain('before-the-wait')
    expect((error as Error).message).toContain('during-tick-')
  })

  it('still accepts a plain string, so existing callers are unchanged', async () => {
    await expect(waitForTicks(() => false, 'a plain description')).rejects.toThrow(
      'a plain description',
    )
  })
})

describe('waitForLastEmit', () => {
  it('waits for an emission that arrives several ticks late', async () => {
    const { wrapper, advance } = lateEmitter('node-selected', ['n2'], 4)

    // Started, not awaited: it and the helper race on the same real ticks. A
    // helper that does not yield leaves this stalled and times out.
    const emitting = advance()
    await waitForLastEmit(wrapper, 'node-selected', ['n2'])
    await emitting

    expect(wrapper.emitted('node-selected')?.at(-1)).toEqual(['n2'])
  })

  it('reports the payload it saw when the expected one never arrives', async () => {
    // The real failure this replaces read `expected [ 'n1' ] to deeply equal
    // [ 'n2' ]` with no hint that the cause was timing. This says so.
    const wrapper = { emitted: () => [['n1']] }

    await expect(waitForLastEmit(wrapper, 'node-selected', ['n2'])).rejects.toThrow(/last seen: \["n1"\]/)
  })

  it('distinguishes nothing-emitted from a wrong payload', async () => {
    const wrapper = { emitted: () => undefined }

    await expect(waitForLastEmit(wrapper, 'node-selected', ['n2'])).rejects.toThrow(/nothing emitted/)
  })
})

describe('waitForEmitCount', () => {
  it('waits for the nth emission', async () => {
    let reads = 0
    const wrapper = {
      emitted: () => {
        reads += 1
        return Array.from({ length: Math.min(reads, 2) }, () => ['moved'])
      },
    }

    await waitForEmitCount(wrapper, 'node-moved', 2)

    expect(wrapper.emitted().length).toBe(2)
  })

  it('throws with the count it saw when the nth never arrives', async () => {
    const wrapper = { emitted: () => [['moved']] }

    await expect(waitForEmitCount(wrapper, 'node-moved', 3)).rejects.toThrow(/emitted 3 time\(s\) \(seen: 1\)/)
  })
})
