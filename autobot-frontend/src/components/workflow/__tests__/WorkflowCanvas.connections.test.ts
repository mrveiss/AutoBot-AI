// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #14766: edge geometry.
 *
 * The `connections` computed used to resolve each edge's target with
 * `props.nodes.find(...)`, making it O(N x E) — on the drag hot path, where
 * `onPointerMove` emits `node-moved` per pointer event and the consumer's
 * write re-triggers the computed. It now resolves through an index built once
 * per recompute.
 *
 * That is a pure refactor, so the tests that matter are the ones that pin the
 * OUTPUT: the rendered `d` attributes must be byte-identical to what the scan
 * produced, including the cases where the two implementations could plausibly
 * disagree — a dangling target, a self-edge, several edges from one node, and
 * a duplicate id (`find` returns the FIRST match; a naive `Map.set` loop keeps
 * the LAST).
 *
 * The expected path strings below are written out in full rather than
 * recomputed from the same formula the component uses. A test that rebuilds
 * the formula would keep passing if the formula itself changed.
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

vi.mock('@/composables/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: vi.fn().mockResolvedValue(true) }),
}))

import WorkflowCanvas from '../WorkflowCanvas.vue'
import type { CanvasNode } from '../canvasNode'

function step(id: string, x: number, y: number, connections: string[] = []): CanvasNode {
  return {
    id,
    type: 'step',
    position: { x, y },
    data: { command: '', description: '', risk_level: 'low', requires_confirmation: true },
    connections,
  }
}

// #14854: built once, not per mount. This file mounts many times and the `en`
// bundle is ~400KB, so constructing a fresh i18n instance inside mountCanvas
// re-ingested the whole message tree on every single mount. The instance is
// read-only here — no test mutates locale or messages — so sharing it is safe
// and removes work that was never the thing under test.
const i18nForTests = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

function mountCanvas(nodes: CanvasNode[]) {
  return mount(WorkflowCanvas, {
    props: { nodes, selectedNodeId: null },
    global: { plugins: [i18nForTests] },
  })
}

/** Every rendered edge path, in render order. */
function paths(w: ReturnType<typeof mountCanvas>): string[] {
  return w.findAll('.connection-line').map((p) => p.attributes('d') ?? '')
}

describe('edge geometry is unchanged by the index (#14766)', () => {
  it('draws the same path the linear scan produced', () => {
    // n1 at (0, 0) -> n2 at (400, 200). Ports attach at the node mid-line
    // (CANVAS_NODE_PORT_Y = 50) and leave the source's right edge
    // (CANVAS_NODE_WIDTH = 240), so the curve runs (240,50) -> (400,250) with
    // both control points on the midpoint x = 320.
    const w = mountCanvas([step('n1', 0, 0, ['n2']), step('n2', 400, 200)])

    expect(paths(w)).toEqual(['M240,50 C320,50 320,250 400,250'])
  })

  it('skips an edge whose target is not on the canvas rather than drawing to nowhere', () => {
    const w = mountCanvas([step('n1', 0, 0, ['ghost']), step('n2', 400, 200)])

    expect(paths(w)).toEqual([])
  })

  it('draws every edge of a node that has several', () => {
    const w = mountCanvas([
      step('n1', 0, 0, ['n2', 'n3']),
      step('n2', 400, 200),
      step('n3', 400, 600),
    ])

    expect(paths(w)).toEqual([
      'M240,50 C320,50 320,250 400,250',
      'M240,50 C320,50 320,650 400,650',
    ])
  })

  it('draws a self-edge as the scan did rather than dropping it', () => {
    const w = mountCanvas([step('n1', 0, 0, ['n1'])])

    expect(paths(w)).toEqual(['M240,50 C120,50 120,50 0,50'])
  })

  it('resolves a duplicated id to the FIRST match, as find() did', () => {
    // Two nodes share the id 'dup'. `find` returns the first; a `Map.set` loop
    // that did not guard would keep the last and re-anchor the edge to
    // (800, 400) instead of (400, 200).
    const w = mountCanvas([
      step('n1', 0, 0, ['dup']),
      step('dup', 400, 200),
      step('dup', 800, 400),
    ])

    expect(paths(w)).toEqual(['M240,50 C320,50 320,250 400,250'])
  })
})

describe('the node count this canvas is known to carry (#14766)', () => {
  // The canvas renders every node as live DOM with no virtualisation and no
  // documented ceiling — before this, no test in the suite mounted more than a
  // handful. This states the number rather than leaving it to be discovered by
  // a real org graph. It is a floor on what we support, not a performance
  // budget: raise it when a surface needs more.
  // 200 is an order of magnitude past anything else the suite mounts.
  const SUPPORTED_NODES = 200

  // #14854: this case previously ran at 11-15s against the suite's 10s
  // `testTimeout` and flaked on runner load. Mounting 200 live DOM nodes with no
  // virtualisation is genuinely slow, and the node count *is* the assertion — so
  // the honest fix is an explicit budget for this one test, not a smaller graph
  // (which would delete the coverage #14766 exists for) and not a global timeout
  // bump (which would hide every other slow test too).
  const MOUNT_BUDGET_MS = 30_000

  it(
    `renders ${SUPPORTED_NODES} nodes and their edges without dropping any`,
    () => {
      const nodes = Array.from({ length: SUPPORTED_NODES }, (_, i) =>
        step(`n${i}`, (i % 20) * 300, Math.floor(i / 20) * 200, i > 0 ? [`n${i - 1}`] : []),
      )

      const w = mountCanvas(nodes)

      expect(w.findAll('.workflow-node')).toHaveLength(SUPPORTED_NODES)
      // Collected once: each call re-queries all 199 edges.
      const rendered = paths(w)
      // Every node but the first carries exactly one outgoing edge.
      expect(rendered).toHaveLength(SUPPORTED_NODES - 1)
      expect(rendered.every((d) => d.startsWith('M'))).toBe(true)
    },
    MOUNT_BUDGET_MS,
  )
})

describe('the edge-target index cannot go stale (#14792)', () => {
  // Staleness is structurally impossible today: the index is a plain local Map
  // built inside the `connections` computed and rebuilt from `props.nodes` on
  // every evaluation, so whatever invalidates the computed rebuilds the index in
  // the same pass. Nothing in the existing suite asserts that, because every
  // case mounts once and asserts immediately.
  //
  // The regression these guard against is the obvious future optimisation:
  // hoisting the Map into a ref, or memoising it outside the computed, to avoid
  // rebuilding it each time. That would look like a clean win, pass the whole
  // suite, and silently render edges against stale positions during a drag —
  // the exact operation the index was introduced to make fast.

  it('redraws against the new positions when a node moves after mount', async () => {
    const w = mountCanvas([step('n1', 0, 0, ['n2']), step('n2', 400, 200)])
    const before = paths(w)
    expect(before).toHaveLength(1)

    await w.setProps({ nodes: [step('n1', 0, 0, ['n2']), step('n2', 900, 600)] })

    const after = paths(w)
    expect(after).toHaveLength(1)
    expect(after[0]).not.toBe(before[0])
  })

  it('resolves an edge to a node added after mount', async () => {
    // A node absent at mount, then present. A cached index would keep reporting
    // the target missing and drop the edge for good.
    const w = mountCanvas([step('n1', 0, 0, ['later'])])
    expect(paths(w)).toHaveLength(0)

    await w.setProps({ nodes: [step('n1', 0, 0, ['later']), step('later', 300, 300)] })

    expect(paths(w)).toHaveLength(1)
  })

  it('drops an edge whose target is removed after mount', async () => {
    // The other direction: a cached index would keep drawing to a node that is
    // no longer on the canvas.
    const w = mountCanvas([step('n1', 0, 0, ['n2']), step('n2', 400, 200)])
    expect(paths(w)).toHaveLength(1)

    await w.setProps({ nodes: [step('n1', 0, 0, ['n2'])] })

    expect(paths(w)).toHaveLength(0)
  })
})

