// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #18254: the test clock never runs backwards, so a host wall-clock step
 * cannot make Vue drop a click. The canvas case runs the same two clicks
 * across a 2 s backward step with and without the monotonic wrapper: without
 * it the undo is dropped (the defect), with it the undo lands.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import { monotonic, type WallClock } from '../monotonicClock'

vi.mock('@/composables/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: vi.fn().mockResolvedValue(true) }),
}))

import WorkflowCanvas from '@/components/workflow/WorkflowCanvas.vue'

const installed = Date.now
afterEach(() => {
  Date.now = installed
})

describe('monotonic()', () => {
  it('never decreases across a backward step, then advances with the wall clock again', () => {
    const readings = [1000, 1010, 8, 18, 30]
    const now = monotonic(() => readings.shift()!)
    expect([now(), now(), now(), now(), now()]).toEqual([1000, 1010, 1010, 1020, 1032])
  })
})

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

/** Add a node, step the wall clock back 2 s, press Undo; report whether the undo landed. */
async function undoAcrossABackwardStep(wrap: (wall: WallClock) => WallClock): Promise<boolean> {
  const real = installed.bind(Date)
  let shift = 0
  Date.now = wrap(() => real() - shift)
  const w = mount(WorkflowCanvas, { props: { nodes: [], selectedNodeId: null }, global: { plugins: [i18n] } })
  await w.get('.tool-btn[title="Add Step"]').trigger('click')
  shift = 2000
  await w.get('[data-testid="canvas-undo"]').trigger('click')
  return Boolean(w.emitted('node-removed'))
}

describe('a click across a backward wall-clock step (#18254)', () => {
  it('lands when the clock is monotonic', async () => {
    expect(await undoAcrossABackwardStep(monotonic)).toBe(true)
  })

  it('is dropped by Vue when the clock is not -- the defect this guards against', async () => {
    expect(await undoAcrossABackwardStep((wall) => wall)).toBe(false)
  })
})
