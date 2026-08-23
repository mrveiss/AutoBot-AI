// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #14770: the WIRING, not the helper.
 *
 * `useReducedMotion.test.ts` proves the composable answers correctly. That is
 * not the same claim as "the graph stops animating" — a helper suite stays
 * green while the seam it feeds is inert or bypassed. So this drives the real
 * component and asserts at the far boundary: the options object cytoscape's
 * own `layout()` actually receives.
 *
 * Cytoscape is faked with a Proxy that answers any property with a chainable
 * no-op, so the test does not have to track which parts of the library's
 * surface the component happens to touch. Only `layout` and `nodes` behave
 * specifically — `nodes` because `runLayout` bails on an empty graph, which
 * would make every assertion below pass vacuously.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const layoutSpy = vi.hoisted(() => vi.fn(() => ({ run: () => {} })))

vi.mock('cytoscape', () => {
  const makeCore = (): unknown => {
    const core: Record<string, unknown> = {
      layout: layoutSpy,
      nodes: () => ({ length: 2, forEach: () => {}, unselect: () => {} }),
    }
    const proxy: unknown = new Proxy(core, {
      get(target, prop) {
        if (prop in target) return target[prop as string]
        return () => proxy
      },
    })
    return proxy
  }
  const factory = () => makeCore()
  ;(factory as unknown as { use: () => void }).use = () => {}
  return { default: factory }
})
vi.mock('cytoscape-fcose', () => ({ default: {} }))

import FunctionCallGraph from '../FunctionCallGraph.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

const DATA = {
  nodes: [
    { id: 'a', name: 'alpha', module: 'm', file: 'm.py', line: 1 },
    { id: 'b', name: 'beta', module: 'm', file: 'm.py', line: 9 },
  ],
  edges: [{ from: 'a', to: 'b', resolved: true }],
}

/**
 * The cluster/Stats view builds its graph from `summary.top_callers` and
 * `summary.most_called` — NOT from `data`. Without a summary it adds no
 * elements and never reaches `runClusterLayout`, so a cluster test that omits
 * this passes its guard and proves nothing.
 */
const SUMMARY = {
  total_functions: 2,
  connected_functions: 2,
  total_call_relationships: 1,
  resolved_calls: 1,
  unresolved_calls: 0,
  top_callers: [{ function: 'alpha', calls: 3 }],
  most_called: [{ function: 'beta', calls: 5 }],
}

function stubMatchMedia(matches: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => ({
      matches,
      media: '(prefers-reduced-motion: reduce)',
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  )
}

async function mountGraph() {
  const w = mount(FunctionCallGraph, {
    props: { data: DATA, summary: SUMMARY },
    global: { plugins: [i18n] },
    attachTo: document.body,
  })
  await flushPromises()
  await flushPromises()
  return w
}

/** The `animate` flag from whichever layout calls actually happened. */
function animateFlags(): unknown[] {
  return layoutSpy.mock.calls.map((c) => (c[0] as { animate?: unknown } | undefined)?.animate)
}

beforeEach(() => {
  layoutSpy.mockClear()
})
afterEach(() => {
  vi.unstubAllGlobals()
})

/** Switch to the Stats/cluster view, which runs its own layout. */
async function openClusterView(w: Awaited<ReturnType<typeof mountGraph>>) {
  await w.get(`.view-toggle button[title="${en.charts.callGraph.clusterView}"]`).trigger('click')
  await flushPromises()
  await flushPromises()
}

describe('graph layout honours prefers-reduced-motion (#14770)', () => {
  it('animates the layout by default', async () => {
    stubMatchMedia(false)

    const w = await mountGraph()

    // Guard first: with no layout call at all the reduced-motion assertion in
    // the next test would pass vacuously — "never animated" is not "obeyed".
    expect(layoutSpy).toHaveBeenCalled()
    expect(animateFlags()).toContain(true)
    w.unmount()
  })

  it('does not animate when the user has asked for reduced motion', async () => {
    stubMatchMedia(true)

    const w = await mountGraph()

    expect(layoutSpy).toHaveBeenCalled()
    expect(animateFlags()).toContain(false)
    expect(animateFlags()).not.toContain(true)
    w.unmount()
  })
})

describe('the cluster layout honours it too (#14806)', () => {
  // #14806: `runClusterLayout` is a sibling of `runLayout` in the same file and
  // was left animating when that one was fixed. The suite passed unchanged with
  // the gap present, because it only ever drove `runLayout` — a test that
  // exercises one of two paths proves nothing about the other.
  it('animates the cluster layout by default', async () => {
    stubMatchMedia(false)
    const w = await mountGraph()
    layoutSpy.mockClear()

    await openClusterView(w)

    // Guard: if opening the view ran no layout at all, the assertion in the
    // next test would pass for the wrong reason.
    expect(layoutSpy).toHaveBeenCalled()
    expect(animateFlags()).toContain(true)
    w.unmount()
  })

  it('does not animate the cluster layout under reduced motion', async () => {
    stubMatchMedia(true)
    const w = await mountGraph()
    layoutSpy.mockClear()

    await openClusterView(w)

    expect(layoutSpy).toHaveBeenCalled()
    expect(animateFlags()).toContain(false)
    expect(animateFlags()).not.toContain(true)
    w.unmount()
  })
})
