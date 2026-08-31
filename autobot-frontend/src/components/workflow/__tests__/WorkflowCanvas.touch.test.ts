// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * GH#14610: the canvas was mouse-only — `touchstart`/`@touch`/pointer events:
 * zero occurrences. Pan needed a modifier key that does not exist on touch
 * (shift or middle-click); zoom was wheel-only; node drag and connection
 * drawing were equally unreachable.
 *
 * Covers:
 *   - a one-finger touch press on empty canvas pans (no modifier key needed)
 *   - a one-finger touch press on a node drags it, exactly like a plain
 *     mouse press already did — readonly (Company OS) disables this, same
 *     rule the keyboard move shortcut already follows (#14609)
 *   - a plain (unmodified) mouse press on empty canvas still does NOT pan —
 *     the touch branch must not swallow the existing mouse gating
 *   - two-finger pinch zooms, clamped to the existing 0.3–2 range
 *   - a touch gesture that moved something does not also select — the touch
 *     analogue of #14079, sharing the one `movedThisGesture` flag
 *   - horizontal pan reads identically in an RTL document (canvas pans with
 *     a CSS transform, never mirrored)
 */

import { describe, it, expect, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { memoizeByLocale } from '@/test/utils/i18n-cache'
import en from '@/i18n/locales/en.json'
import ar from '@/i18n/locales/ar.json'

vi.mock('@/composables/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: vi.fn().mockResolvedValue(true) }),
}))

import WorkflowCanvas from '../WorkflowCanvas.vue'
import type { CanvasNode } from '../canvasNode'
import { firePointer } from './pointerTestUtils'

const ORG_NODE: CanvasNode[] = [
  {
    id: 'ceo',
    type: 'org-person',
    position: { x: 40, y: 40 },
    data: { title: 'Ada', status: 'idle' },
    connections: [],
  },
]

const STEP_NODE: CanvasNode[] = [
  {
    id: 'n1',
    type: 'step',
    position: { x: 100, y: 40 },
    data: { command: '', description: '', risk_level: 'low', requires_confirmation: true },
    connections: [],
  },
]

// #14860: memoized per locale. This helper ran on EVERY mount and each call
// re-ingested the ~400KB `en` and `ar` message bundles. The locale is a real
// parameter here, so a blind hoist would be wrong — one instance per locale
// is not. Nothing in this file mutates the returned instance.
const makeI18n = memoizeByLocale((locale: string) =>
  createI18n({ legacy: false, locale, fallbackLocale: 'en', messages: { en, ar } }),
)

function mountCanvas(props: Record<string, unknown>, locale: 'en' | 'ar' = 'en') {
  return mount(WorkflowCanvas, {
    props: { selectedNodeId: null, ...props },
    global: { plugins: [makeI18n(locale)] },
  })
}

type Wrapper = ReturnType<typeof mountCanvas>

const area = (w: Wrapper) => w.get('.canvas-area')
const node = (w: Wrapper) => w.get('.workflow-node')
const transform = (w: Wrapper) => w.get('.canvas-content').attributes('style')

afterEach(() => {
  document.documentElement.removeAttribute('dir')
})

describe('WorkflowCanvas one-finger touch pan (#14610)', () => {
  it('pans from a press on empty canvas — no modifier key needed', async () => {
    const w = mountCanvas({ nodes: ORG_NODE, readonly: true })

    await firePointer(area(w).element, 'pointerdown', {
      pointerType: 'touch', pointerId: 1, clientX: 10, clientY: 10,
    })
    await firePointer(area(w).element, 'pointermove', {
      pointerType: 'touch', pointerId: 1, clientX: 90, clientY: 60,
    })
    await firePointer(area(w).element, 'pointerup', {
      pointerType: 'touch', pointerId: 1, clientX: 90, clientY: 60,
    })

    // Default pan starts at (50, 50); an 80/50 finger delta lands at (130, 100).
    expect(transform(w)).toContain('translate(130px, 100px)')
  })

  it('a plain unmodified mouse press on empty canvas still does not pan', async () => {
    // The touch branch (`pointerType === 'touch'`) must not swallow the
    // mouse's own shift/middle-click gating — a mouse press with neither
    // stays a no-op on empty canvas, exactly as before #14610.
    const w = mountCanvas({ nodes: ORG_NODE, readonly: true })

    await firePointer(area(w).element, 'pointerdown', {
      pointerType: 'mouse', pointerId: 1, clientX: 10, clientY: 10,
    })
    await firePointer(area(w).element, 'pointermove', {
      pointerType: 'mouse', pointerId: 1, clientX: 90, clientY: 60,
    })

    expect(transform(w)).toContain('translate(50px, 50px)')
  })

  it('pans by the same transform in an RTL locale as in an LTR one', async () => {
    const ltr = mountCanvas({ nodes: ORG_NODE, readonly: true }, 'en')
    await firePointer(area(ltr).element, 'pointerdown', { pointerType: 'touch', pointerId: 1, clientX: 10, clientY: 10 })
    await firePointer(area(ltr).element, 'pointermove', { pointerType: 'touch', pointerId: 1, clientX: 130, clientY: 40 })
    const ltrStyle = transform(ltr)

    document.documentElement.setAttribute('dir', 'rtl')
    const rtl = mountCanvas({ nodes: ORG_NODE, readonly: true }, 'ar')
    await firePointer(area(rtl).element, 'pointerdown', { pointerType: 'touch', pointerId: 1, clientX: 10, clientY: 10 })
    await firePointer(area(rtl).element, 'pointermove', { pointerType: 'touch', pointerId: 1, clientX: 130, clientY: 40 })
    const rtlStyle = transform(rtl)

    expect(ltrStyle).toContain('translate(170px, 80px)')
    expect(rtlStyle).toBe(ltrStyle)
  })
})

describe('WorkflowCanvas one-finger touch drag (#14610)', () => {
  it('drags a node exactly like a plain mouse press already did', async () => {
    const w = mountCanvas({ nodes: STEP_NODE, readonly: false })

    await firePointer(node(w).element, 'pointerdown', {
      pointerType: 'touch', pointerId: 1, clientX: 100, clientY: 100,
    })
    await firePointer(area(w).element, 'pointermove', {
      pointerType: 'touch', pointerId: 1, clientX: 130, clientY: 140,
    })

    // #14768: the drag lands on the grid — the raw drop is (130, 80) and 130
    // snaps to the nearest 20. The y is already a grid multiple.
    expect(w.emitted('node-moved')).toEqual([['n1', { x: 140, y: 80 }]])
    // The pan transform must not have moved — this was a drag, not a pan.
    expect(transform(w)).toContain('translate(50px, 50px)')
  })

  it('drags the node on a readonly canvas, exactly as the mouse always has', async () => {
    // The premise these tests were first written under was wrong, and #14610
    // corrected it. `readonly` means "cannot author the workflow" — no add,
    // delete, connect or save. Moving a node rearranges the *view* and
    // persists nothing: `OrgChart.onCanvasNodeMoved` writes an in-memory
    // position.
    //
    // It is also a feature the org chart deliberately supports. `OrgChart.vue`
    // holds `canvasNodes` as a ref rather than a computed specifically so
    // "node drags stay put", and avoids re-layout so "a drag survives
    // pause/resume". Refusing the drag here would have made that engineering
    // dead code on the only canvas that mounts read-only.
    const w = mountCanvas({ nodes: ORG_NODE, readonly: true })

    await firePointer(node(w).element, 'pointerdown', {
      pointerType: 'touch', pointerId: 1, clientX: 100, clientY: 100,
    })
    await firePointer(area(w).element, 'pointermove', {
      pointerType: 'touch', pointerId: 1, clientX: 130, clientY: 140,
    })

    expect(w.emitted('node-moved')).toBeTruthy()
    // A drag, not a pan: the canvas transform is untouched.
    expect(transform(w)).toContain('translate(50px, 50px)')
  })

  it('drags rather than pans when a touch press starts on a node, matching the mouse', async () => {
    // Parity is the point. A press on a node drags it and a pan starts on
    // empty canvas or a container, for touch and mouse alike — one rule, not
    // one rule per input device.
    const w = mountCanvas({ nodes: ORG_NODE, readonly: true })

    await firePointer(node(w).element, 'pointerdown', {
      pointerType: 'touch', pointerId: 1, clientX: 100, clientY: 100,
    })
    await firePointer(area(w).element, 'pointermove', {
      pointerType: 'touch', pointerId: 1, clientX: 130, clientY: 140,
    })

    expect(transform(w)).toContain('translate(50px, 50px)')
  })

  it('drags on a readonly canvas by mouse too, so neither device is special-cased', async () => {
    const w = mountCanvas({ nodes: ORG_NODE, readonly: true })

    await firePointer(node(w).element, 'pointerdown', {
      pointerType: 'mouse', pointerId: 1, clientX: 100, clientY: 100,
    })
    await firePointer(area(w).element, 'pointermove', {
      pointerType: 'mouse', pointerId: 1, clientX: 130, clientY: 140,
    })

    expect(w.emitted('node-moved')).toBeTruthy()
  })

  it('readonly still selects the node on a genuine tap', async () => {
    const w = mountCanvas({ nodes: ORG_NODE, readonly: true })

    await firePointer(node(w).element, 'pointerdown', {
      pointerType: 'touch', pointerId: 1, clientX: 100, clientY: 100,
    })
    await firePointer(node(w).element, 'pointerup', {
      pointerType: 'touch', pointerId: 1, clientX: 100, clientY: 100,
    })
    await node(w).trigger('click')

    expect(w.emitted('node-selected')).toEqual([['ceo']])
  })
})

describe('WorkflowCanvas a touch gesture that moved does not also select (#14610)', () => {
  it('does not select the node a one-finger drag just moved', async () => {
    const w = mountCanvas({ nodes: STEP_NODE, readonly: false })

    await firePointer(node(w).element, 'pointerdown', { pointerType: 'touch', pointerId: 1, clientX: 100, clientY: 100 })
    await firePointer(area(w).element, 'pointermove', { pointerType: 'touch', pointerId: 1, clientX: 170, clientY: 100 })
    await firePointer(area(w).element, 'pointerup', { pointerType: 'touch', pointerId: 1, clientX: 170, clientY: 100 })
    // The `click` a real touchscreen fires when the finger lifts over the node.
    await node(w).trigger('click')

    expect(w.emitted('node-selected')).toBeUndefined()
  })

  it('does not select the node a one-finger pan started on', async () => {
    const w = mountCanvas({ nodes: ORG_NODE, readonly: true })

    await firePointer(node(w).element, 'pointerdown', { pointerType: 'touch', pointerId: 1, clientX: 100, clientY: 100 })
    await firePointer(area(w).element, 'pointermove', { pointerType: 'touch', pointerId: 1, clientX: 170, clientY: 100 })
    await firePointer(area(w).element, 'pointerup', { pointerType: 'touch', pointerId: 1, clientX: 170, clientY: 100 })
    await node(w).trigger('click')

    expect(w.emitted('node-selected')).toBeUndefined()
  })

  it('still selects on a tap that never moved', async () => {
    // The negative-only trap: pair every "does not select" assertion above
    // with a case that must stay selectable.
    const w = mountCanvas({ nodes: STEP_NODE, readonly: false })

    await firePointer(node(w).element, 'pointerdown', { pointerType: 'touch', pointerId: 1, clientX: 100, clientY: 100 })
    await firePointer(node(w).element, 'pointerup', { pointerType: 'touch', pointerId: 1, clientX: 100, clientY: 100 })
    await node(w).trigger('click')

    expect(w.emitted('node-selected')).toEqual([['n1']])
  })
})

describe('WorkflowCanvas pinch-to-zoom (#14610)', () => {
  it('zooms in as two fingers spread apart', async () => {
    const w = mountCanvas({ nodes: ORG_NODE, readonly: true })

    await firePointer(area(w).element, 'pointerdown', { pointerType: 'touch', pointerId: 1, clientX: 100, clientY: 100 })
    await firePointer(area(w).element, 'pointerdown', { pointerType: 'touch', pointerId: 2, clientX: 200, clientY: 100 })
    // Distance 100 -> 150: 1.5x.
    await firePointer(area(w).element, 'pointermove', { pointerType: 'touch', pointerId: 1, clientX: 50, clientY: 100 })

    expect(transform(w)).toContain('scale(1.5)')
  })

  it('zooms out as two fingers pinch together', async () => {
    const w = mountCanvas({ nodes: ORG_NODE, readonly: true })

    await firePointer(area(w).element, 'pointerdown', { pointerType: 'touch', pointerId: 1, clientX: 0, clientY: 100 })
    await firePointer(area(w).element, 'pointerdown', { pointerType: 'touch', pointerId: 2, clientX: 200, clientY: 100 })
    // Distance 200 -> 100: 0.5x.
    await firePointer(area(w).element, 'pointermove', { pointerType: 'touch', pointerId: 1, clientX: 100, clientY: 100 })

    expect(transform(w)).toContain('scale(0.5)')
  })

  it('clamps pinch-out at the existing zoom-in ceiling (2)', async () => {
    const w = mountCanvas({ nodes: ORG_NODE, readonly: true })

    await firePointer(area(w).element, 'pointerdown', { pointerType: 'touch', pointerId: 1, clientX: 100, clientY: 100 })
    await firePointer(area(w).element, 'pointerdown', { pointerType: 'touch', pointerId: 2, clientX: 110, clientY: 100 })
    // Distance 10 -> 1000: wildly past the ceiling.
    await firePointer(area(w).element, 'pointermove', { pointerType: 'touch', pointerId: 1, clientX: -890, clientY: 100 })

    expect(transform(w)).toContain('scale(2)')
  })

  it('clamps pinch-in at the existing zoom-out floor (0.3)', async () => {
    const w = mountCanvas({ nodes: ORG_NODE, readonly: true })

    await firePointer(area(w).element, 'pointerdown', { pointerType: 'touch', pointerId: 1, clientX: 0, clientY: 100 })
    await firePointer(area(w).element, 'pointerdown', { pointerType: 'touch', pointerId: 2, clientX: 200, clientY: 100 })
    // Distance 200 -> 2: wildly past the floor.
    await firePointer(area(w).element, 'pointermove', { pointerType: 'touch', pointerId: 1, clientX: 198, clientY: 100 })

    expect(transform(w)).toContain('scale(0.3)')
  })

  it('a second finger landing on a node still starts a pinch, not a drag', async () => {
    // #14610: pinch is tracked at both `startPan` (empty canvas) and
    // `onNodePointerDown` (a node) — a real two-finger pinch rarely lands
    // both fingers on empty canvas.
    const w = mountCanvas({ nodes: STEP_NODE, readonly: false })

    await firePointer(area(w).element, 'pointerdown', { pointerType: 'touch', pointerId: 1, clientX: 200, clientY: 100 })
    await firePointer(node(w).element, 'pointerdown', { pointerType: 'touch', pointerId: 2, clientX: 100, clientY: 100 })
    // Distance 100 -> 150: 1.5x.
    await firePointer(area(w).element, 'pointermove', { pointerType: 'touch', pointerId: 1, clientX: 250, clientY: 100 })

    expect(w.emitted('node-moved')).toBeUndefined()
    expect(transform(w)).toContain('scale(1.5)')
  })
})
