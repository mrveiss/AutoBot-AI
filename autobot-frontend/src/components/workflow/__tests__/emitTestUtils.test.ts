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
function lateEmitter(event: string, payload: unknown, afterTicks: number) {
  let ticks = 0
  const emissions: unknown[] = []
  const advance = async () => {
    for (let i = 0; i < afterTicks + 2; i += 1) {
      ticks += 1
      if (ticks === afterTicks) emissions.push(payload)
      await nextTick()
    }
  }
  return {
    wrapper: {
      emitted: (name: string) => {
        // Reading is what drives the clock here, mirroring the real case: the
        // helper flushes ticks and the component emits during one of them.
        if (name !== event) return undefined
        ticks += 1
        if (ticks === afterTicks) emissions.push(payload)
        return emissions.length ? [...emissions] : undefined
      },
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

describe('waitForLastEmit', () => {
  it('waits for an emission that arrives several ticks late', async () => {
    const { wrapper } = lateEmitter('node-selected', ['n2'], 4)

    await waitForLastEmit(wrapper, 'node-selected', ['n2'])

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
