// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #14612: the node context menu — `contextMenu`/`contextMenuActions`/
 * `openContextMenuAt`/`onNodeContextMenu`/`runContextMenuAction` were
 * implemented and never exercised by a test. This covers:
 *   - it opens where the user pointed, acting on the RIGHT node.
 *   - it offers only actions that genuinely exist — no "edit" item, since
 *     card editing (#14603) is blocked and unbuilt.
 *   - its per-node action set is never a second, hand-maintained list: every
 *     action re-invokes the exact handler the node's own inline control
 *     (the process/tool detach buttons) already calls, with the same
 *     payload.
 *   - it is keyboard-reachable: the ContextMenu key, Shift+F10, and the
 *     node's own "…" button (a real `<button>`, Tab/Enter-operable without
 *     memorising either shortcut) all open it.
 *   - it clamps to the physical viewport identically in an RTL document —
 *     never locale/direction-dependent offset math that could put it on the
 *     wrong side.
 */

import { describe, it, expect, vi, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import ar from '@/i18n/locales/ar.json'

vi.mock('@/composables/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: vi.fn().mockResolvedValue(true) }),
}))

import WorkflowCanvas from '../WorkflowCanvas.vue'
import type { CanvasNode } from '../canvasNode'
import { buildProcessCanvasNodes, buildToolCanvasNodes } from '@/composables/llc/orgCanvasGraph'

function step(id: string, x: number, y: number): CanvasNode {
  return {
    id,
    type: 'step',
    position: { x, y },
    data: { command: '', description: '', risk_level: 'low', requires_confirmation: true },
    connections: [],
  }
}

function makeI18n(locale: 'en' | 'ar') {
  return createI18n({ legacy: false, locale, fallbackLocale: 'en', messages: { en, ar } })
}

function mountCanvas(props: Record<string, unknown>, locale: 'en' | 'ar' = 'en') {
  return mount(WorkflowCanvas, {
    props: { selectedNodeId: null, ...props },
    global: { plugins: [makeI18n(locale)] },
  })
}

type Wrapper = ReturnType<typeof mountCanvas>
const node = (w: Wrapper, id: string) => w.get(`[data-node-id="${id}"]`)
const menu = (w: Wrapper) => w.find('[data-testid="canvas-context-menu"]')
const menuItem = (w: Wrapper, actionId: string) => w.find(`[data-testid="canvas-context-menu-item-${actionId}"]`)

afterEach(() => {
  document.documentElement.removeAttribute('dir')
})

describe('the context menu opens where the user pointed, on the right node (#14612)', () => {
  it('anchors at the click coordinates', async () => {
    const w = mountCanvas({ nodes: [step('n1', 10, 10), step('n2', 300, 10)] })

    await node(w, 'n2').trigger('contextmenu', { clientX: 123, clientY: 456 })

    expect(menu(w).exists()).toBe(true)
    expect(menu(w).attributes('style')).toContain('left: 123px')
    expect(menu(w).attributes('style')).toContain('top: 456px')
  })

  it('acts on the node it was opened on, not some other node on the canvas', async () => {
    const w = mountCanvas({ nodes: [step('n1', 10, 10), step('n2', 300, 10)] })

    await node(w, 'n2').trigger('contextmenu', { clientX: 50, clientY: 50 })
    await menuItem(w, 'select').trigger('click')

    expect(w.emitted('node-selected')?.at(-1)).toEqual(['n2'])
  })

  it('re-anchors and re-targets when opened again on a different node', async () => {
    const w = mountCanvas({ nodes: [step('n1', 10, 10), step('n2', 300, 10)] })

    await node(w, 'n1').trigger('contextmenu', { clientX: 10, clientY: 10 })
    await node(w, 'n2').trigger('contextmenu', { clientX: 200, clientY: 200 })
    await menuItem(w, 'select').trigger('click')

    expect(w.emitted('node-selected')?.at(-1)).toEqual(['n2'])
  })
})

describe('the menu offers only actions that genuinely exist today (#14603/#14612)', () => {
  it('never offers an edit action — card editing is unbuilt', async () => {
    const w = mountCanvas({ nodes: [step('n1', 10, 10)] })
    await node(w, 'n1').trigger('contextmenu', { clientX: 10, clientY: 10 })

    expect(w.find('[data-testid="canvas-context-menu-item-edit"]').exists()).toBe(false)
    expect(menu(w).text().toLowerCase()).not.toContain('edit')
  })

  it('offers exactly select/zoom/delete for an ordinary step node', async () => {
    const w = mountCanvas({ nodes: [step('n1', 10, 10)] })
    await node(w, 'n1').trigger('contextmenu', { clientX: 10, clientY: 10 })

    expect(menuItem(w, 'select').exists()).toBe(true)
    expect(menuItem(w, 'zoom').exists()).toBe(true)
    expect(menuItem(w, 'delete').exists()).toBe(true)
    expect(menu(w).findAll('[role="menuitem"]')).toHaveLength(3)
  })

  it('never offers delete on a readonly canvas', async () => {
    const w = mountCanvas({ nodes: [step('n1', 10, 10)], readonly: true })
    await node(w, 'n1').trigger('contextmenu', { clientX: 10, clientY: 10 })

    expect(menuItem(w, 'delete').exists()).toBe(false)
    expect(menuItem(w, 'select').exists()).toBe(true)
  })
})

describe("the menu's action set mirrors the card's own controls, never a second list (#14612)", () => {
  it('the org-process detach item emits the identical payload the card button does', async () => {
    const nodes = buildProcessCanvasNodes(
      [{ role_id: 'role-1', role_name: 'Head of Ops', workflow_id: 'wf-1' }],
      0,
    )

    const cardCanvas = mountCanvas({ nodes, readonly: true })
    await cardCanvas.find('[data-testid="process-detach-btn"]').trigger('click')
    const cardPayload = cardCanvas.emitted('process-detached')?.at(0)

    const menuCanvas = mountCanvas({ nodes, readonly: true })
    await node(menuCanvas, nodes[0].id).trigger('contextmenu', { clientX: 10, clientY: 10 })
    await menuItem(menuCanvas, 'detach-process').trigger('click')
    const menuPayload = menuCanvas.emitted('process-detached')?.at(0)

    expect(menuPayload).toEqual(cardPayload)
    expect(menuPayload).toEqual(['role-1', 'wf-1'])
  })

  it('offers one detach-tool item per role, each matching its own card chip', async () => {
    const nodes = buildToolCanvasNodes(
      [
        { role_id: 'role-1', role_name: 'Head of Ops', tool_name: 'web_search' },
        { role_id: 'role-2', role_name: 'SRE', tool_name: 'web_search' },
      ],
      [],
      0,
    )

    const cardCanvas = mountCanvas({ nodes, readonly: true })
    const cardButtons = cardCanvas.findAll('[data-testid="tool-detach-btn"]')
    expect(cardButtons).toHaveLength(2)
    await cardButtons[0].trigger('click')
    await cardButtons[1].trigger('click')
    const cardPayloads = (cardCanvas.emitted('tool-detached') as unknown as [string, string][]).map((p) =>
      p.join(':'),
    )

    const menuCanvas = mountCanvas({ nodes, readonly: true })
    await node(menuCanvas, nodes[0].id).trigger('contextmenu', { clientX: 10, clientY: 10 })
    expect(menuItem(menuCanvas, 'detach-tool-role-1').exists()).toBe(true)
    expect(menuItem(menuCanvas, 'detach-tool-role-2').exists()).toBe(true)
    await menuItem(menuCanvas, 'detach-tool-role-1').trigger('click')
    await node(menuCanvas, nodes[0].id).trigger('contextmenu', { clientX: 10, clientY: 10 })
    await menuItem(menuCanvas, 'detach-tool-role-2').trigger('click')
    const menuPayloads = (menuCanvas.emitted('tool-detached') as unknown as [string, string][]).map((p) =>
      p.join(':'),
    )

    expect(new Set(menuPayloads)).toEqual(new Set(cardPayloads))
  })
})

describe('the context menu is keyboard-reachable (#14609/#14610/#14612)', () => {
  it('opens on the ContextMenu key', async () => {
    const w = mountCanvas({ nodes: [step('n1', 10, 10)] })
    await node(w, 'n1').trigger('keydown', { key: 'ContextMenu' })

    expect(menu(w).exists()).toBe(true)
  })

  it('opens on Shift+F10, the pre-ContextMenu-key convention', async () => {
    const w = mountCanvas({ nodes: [step('n1', 10, 10)] })
    await node(w, 'n1').trigger('keydown', { key: 'F10', shiftKey: true })

    expect(menu(w).exists()).toBe(true)
  })

  it("the node's own … button is a real, Tab/Enter-operable button that opens the same menu", async () => {
    const w = mountCanvas({ nodes: [step('n1', 10, 10), step('n2', 300, 10)] })
    const menuBtn = node(w, 'n2').get('[data-testid="node-menu-btn"]')

    expect(menuBtn.element.tagName).toBe('BUTTON')
    expect(menuBtn.attributes('type')).toBe('button')

    await menuBtn.trigger('click')

    expect(menu(w).exists()).toBe(true)
    await menuItem(w, 'select').trigger('click')
    expect(w.emitted('node-selected')?.at(-1)).toEqual(['n2'])
  })
})

describe('the context menu clamps identically regardless of document direction (#14612)', () => {
  const ORIGINAL_WIDTH = window.innerWidth
  const ORIGINAL_HEIGHT = window.innerHeight

  afterEach(() => {
    Object.defineProperty(window, 'innerWidth', { value: ORIGINAL_WIDTH, configurable: true })
    Object.defineProperty(window, 'innerHeight', { value: ORIGINAL_HEIGHT, configurable: true })
  })

  function stubViewport(width: number, height: number): void {
    Object.defineProperty(window, 'innerWidth', { value: width, configurable: true })
    Object.defineProperty(window, 'innerHeight', { value: height, configurable: true })
  }

  it('clamps a right-click near the physical edge to the same coordinates in en/ltr and ar/rtl', async () => {
    stubViewport(1000, 700)
    // CONTEXT_MENU_WIDTH=220, CONTEXT_MENU_MAX_HEIGHT=280, an 8px margin —
    // matches the component's own constants (not re-exported, so pinned
    // here; the mutation test proves this pin is actually load-bearing).
    const expectedX = 1000 - 220 - 8
    const expectedY = 700 - 280 - 8

    const ltr = mountCanvas({ nodes: [step('n1', 10, 10)] }, 'en')
    await node(ltr, 'n1').trigger('contextmenu', { clientX: 995, clientY: 695 })
    expect(menu(ltr).attributes('style')).toContain(`left: ${expectedX}px`)
    expect(menu(ltr).attributes('style')).toContain(`top: ${expectedY}px`)

    document.documentElement.setAttribute('dir', 'rtl')
    const rtl = mountCanvas({ nodes: [step('n1', 10, 10)] }, 'ar')
    await node(rtl, 'n1').trigger('contextmenu', { clientX: 995, clientY: 695 })
    expect(menu(rtl).attributes('style')).toContain(`left: ${expectedX}px`)
    expect(menu(rtl).attributes('style')).toContain(`top: ${expectedY}px`)
  })

  it('does not clamp a right-click well inside the viewport, in either direction', async () => {
    stubViewport(1000, 700)

    const ltr = mountCanvas({ nodes: [step('n1', 10, 10)] }, 'en')
    await node(ltr, 'n1').trigger('contextmenu', { clientX: 300, clientY: 200 })
    expect(menu(ltr).attributes('style')).toContain('left: 300px')
    expect(menu(ltr).attributes('style')).toContain('top: 200px')

    document.documentElement.setAttribute('dir', 'rtl')
    const rtl = mountCanvas({ nodes: [step('n1', 10, 10)] }, 'ar')
    await node(rtl, 'n1').trigger('contextmenu', { clientX: 300, clientY: 200 })
    expect(menu(rtl).attributes('style')).toContain('left: 300px')
    expect(menu(rtl).attributes('style')).toContain('top: 200px')
  })
})

describe('a context-menu action actually performs its action (#14612)', () => {
  // Codecov flagged every `run: () => …` closure as uncovered, and it was
  // right to: the tests above prove the menu LISTS the correct actions and
  // that its detach payloads match the card's, but nothing proved that
  // clicking `select`, `zoom` or `fit-selection` does anything at all. A menu
  // that names an action it does not perform is the "full surface, no sink"
  // shape — everything visible, nothing wired.

  it('select emits node-selected for the node the menu was opened on', async () => {
    const w = mountCanvas({ nodes: [step('n1', 10, 10), step('n2', 300, 10)] })

    await node(w, 'n2').trigger('contextmenu', { clientX: 50, clientY: 50 })
    // Opening the menu already selects the node it was opened on, so the
    // emission count is captured HERE. Asserting only on the last emission
    // would pass with the action neutered — the open would satisfy it.
    const beforeClick = (w.emitted('node-selected') ?? []).length

    await menuItem(w, 'select').trigger('click')

    const after = w.emitted('node-selected') ?? []
    expect(after.length).toBeGreaterThan(beforeClick)
    expect(after.at(-1)).toEqual(['n2'])
    // And the menu closes behind it, rather than lingering over the canvas.
    expect(menu(w).exists()).toBe(false)
  })

  it('zoom moves the viewport onto that node, and does not merely close the menu', async () => {
    const w = mountCanvas({ nodes: [step('n1', 10, 10), step('n2', 900, 700)] })
    const before = (w.find('.canvas-content').attributes('style') ?? '')

    await node(w, 'n2').trigger('contextmenu', { clientX: 50, clientY: 50 })
    await menuItem(w, 'zoom').trigger('click')

    const after = (w.find('.canvas-content').attributes('style') ?? '')
    expect(after).not.toBe(before)
    expect(after).toContain('scale(')
  })

  it('fit-selection frames the whole selection, not just the clicked node', async () => {
    const nodes = [step('n1', 0, 0), step('n2', 900, 700), step('n3', 1800, 1400)]
    const w = mountCanvas({ nodes })

    // Build a multi-selection: plain click, then shift-click a distant node.
    await node(w, 'n1').trigger('click')
    await node(w, 'n3').trigger('click', { shiftKey: true })

    const before = (w.find('.canvas-content').attributes('style') ?? '')
    await node(w, 'n3').trigger('contextmenu', { clientX: 50, clientY: 50 })
    const fit = menuItem(w, 'fit-selection')
    expect(fit.exists()).toBe(true)
    await fit.trigger('click')

    expect((w.find('.canvas-content').attributes('style') ?? '')).not.toBe(before)
  })
})
