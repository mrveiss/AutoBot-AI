// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #14689: the save dialog had no focus management at all — no trap, no initial
// focus, no restore, no Escape. Tab walked straight out of it into the canvas
// behind, which is the failure a trap exists to prevent.
//
// #14609 wired the same three helpers into CanvasNodeSidebar. This dialog was
// left out then because `readonly` hides it and Company OS cannot reach it —
// true, and still a live gap for the workflow builder, where it is reachable.

import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import WorkflowCanvas from '../WorkflowCanvas.vue'
import type { CanvasNode } from '../canvasNode'

const NODES: CanvasNode[] = [
  { id: 'n1', type: 'step', position: { x: 0, y: 0 }, data: { label: 'Step' }, connections: [] },
]

// #14860: one shared instance for the whole file. A fresh createI18n per
// mount re-ingested the ~400KB message bundle every time; nothing here
// mutates the instance, so building it once is enough.
const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

function mountCanvas() {
  return mount(WorkflowCanvas, {
    props: { nodes: NODES, selectedNodeId: null, readonly: false },
    attachTo: document.body,
    global: { plugins: [i18n] },
  })
}

type Wrapper = ReturnType<typeof mountCanvas>
const openBtn = (w: Wrapper) => w.get('.tool-btn.primary')
const dialog = (w: Wrapper) => w.find('.dialog')

beforeEach(() => {
  document.body.innerHTML = ''
})

describe('the save dialog manages focus (#14689)', () => {
  it('is a labelled modal dialog, not an unannounced div', async () => {
    const w = mountCanvas()
    await openBtn(w).trigger('click')

    const d = dialog(w)
    expect(d.attributes('role')).toBe('dialog')
    expect(d.attributes('aria-modal')).toBe('true')
    // Labelled by its own heading, so a screen reader announces what it is.
    const labelledBy = d.attributes('aria-labelledby')
    expect(labelledBy).toBeTruthy()
    expect(w.find(`#${labelledBy}`).exists()).toBe(true)
  })

  it('moves focus into the dialog when it opens', async () => {
    const w = mountCanvas()
    await openBtn(w).trigger('click')
    await new Promise((r) => setTimeout(r, 0))

    // Focus is inside the dialog, not left on the toolbar behind it.
    expect(dialog(w).element.contains(document.activeElement)).toBe(true)
  })

  it('returns focus to whatever opened it, on close', async () => {
    const w = mountCanvas()
    const trigger = openBtn(w).element as HTMLElement
    trigger.focus()
    expect(document.activeElement).toBe(trigger)

    await openBtn(w).trigger('click')
    await new Promise((r) => setTimeout(r, 0))
    await w.get('.dialog .btn-secondary').trigger('click')
    await new Promise((r) => setTimeout(r, 0))

    expect(document.activeElement).toBe(trigger)
  })

  it('closes on Escape', async () => {
    const w = mountCanvas()
    await openBtn(w).trigger('click')
    expect(dialog(w).exists()).toBe(true)

    await dialog(w).trigger('keydown.escape')

    expect(dialog(w).exists()).toBe(false)
  })

  // NOTE: there is deliberately no test for the Tab WRAP itself.
  //
  // `useFocusTrap` filters candidates through `isTabbable`, which depends on
  // layout — and jsdom computes none, so the candidate list comes back empty
  // and the handler returns before wrapping. A test asserting "focus is still
  // inside the dialog" DOES pass, and passes just as well with the trap
  // removed, because jsdom never moves focus on Tab in the first place. That
  // is evidence of nothing.
  //
  // What is proven above is that the handler is wired, that the dialog is a
  // labelled modal, and that focus enters and returns. The wrap is left to the
  // composable's own tests, where it can be exercised honestly.
})
