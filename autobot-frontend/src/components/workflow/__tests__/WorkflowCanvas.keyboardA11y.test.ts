// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * GH#14609: the canvas was entirely unreachable by keyboard — nodes were
 * plain `<div>`s with no tabindex, role or key handler. This covers:
 *   - roving tabindex (one Tab stop; the rest -1) and its `@focus` sync
 *   - Enter/Space selects (same effect as `@click`), Escape deselects
 *   - arrow keys move focus in visual order, RTL-aware for left/right
 *   - a Ctrl/Cmd+arrow moves the focused node (readonly disables this)
 *   - a keypress bubbling from a node's own input/select/button is left
 *     alone, never hijacked as a node-level shortcut
 *   - the accessible name states kind, name and (for org-person) state
 *   - focus survives a canvas re-layout (new node objects, same ids)
 */

import { describe, it, expect, afterEach, vi } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import ar from '@/i18n/locales/ar.json'

vi.mock('@/composables/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: vi.fn().mockResolvedValue(true) }),
}))

import WorkflowCanvas from '../WorkflowCanvas.vue'
import type { CanvasNode } from '../canvasNode'

/** Four org-person nodes on a clean 2x2 grid, far enough apart that the
 *  directional nearest-neighbour search has one unambiguous answer per key. */
function grid(): CanvasNode[] {
  return [
    { id: 'a', type: 'org-person', position: { x: 0, y: 0 }, data: { label: 'Ada', title: 'CEO', status: 'active', is_human: false, adapter_type: 'claude' }, connections: [] },
    { id: 'b', type: 'org-person', position: { x: 400, y: 0 }, data: { label: 'Bea', title: 'CTO', status: 'idle', is_human: false, adapter_type: 'claude' }, connections: [] },
    { id: 'c', type: 'org-person', position: { x: 0, y: 400 }, data: { label: 'Cid', title: 'COO', status: 'paused', is_human: true }, connections: [] },
    { id: 'd', type: 'org-person', position: { x: 400, y: 400 }, data: { label: 'Dee', title: 'CFO', status: 'error', is_human: false, adapter_type: 'ollama' }, connections: [] },
  ]
}

const WORKFLOW_NODES: CanvasNode[] = [
  {
    id: 'n1',
    type: 'step',
    position: { x: 10, y: 10 },
    data: { command: '', description: '', risk_level: 'low', requires_confirmation: true },
    connections: [],
  },
]

function makeI18n(locale: 'en' | 'ar') {
  return createI18n({ legacy: false, locale, fallbackLocale: 'en', messages: { en, ar } })
}

function mountCanvas(
  props: Record<string, unknown>,
  opts: { locale?: 'en' | 'ar'; attach?: boolean } = {},
) {
  return mount(WorkflowCanvas, {
    props: { selectedNodeId: null, ...props },
    global: { plugins: [makeI18n(opts.locale ?? 'en')] },
    ...(opts.attach ? { attachTo: document.body } : {}),
  })
}

function nodeDiv(wrapper: VueWrapper, id: string) {
  return wrapper.get(`[data-node-id="${id}"]`)
}

async function keydown(
  wrapper: VueWrapper,
  id: string,
  key: string,
  modifiers: Partial<KeyboardEventInit> = {},
) {
  await nodeDiv(wrapper, id).trigger('keydown', { key, ...modifiers })
}

afterEach(() => {
  document.documentElement.removeAttribute('dir')
})

describe('WorkflowCanvas roving tabindex (#14609)', () => {
  it('makes only the visually-first node a Tab stop', () => {
    const wrapper = mountCanvas({ nodes: grid(), readonly: true })

    expect(nodeDiv(wrapper, 'a').attributes('tabindex')).toBe('0')
    expect(nodeDiv(wrapper, 'b').attributes('tabindex')).toBe('-1')
    expect(nodeDiv(wrapper, 'c').attributes('tabindex')).toBe('-1')
    expect(nodeDiv(wrapper, 'd').attributes('tabindex')).toBe('-1')
  })

  it('moves the Tab stop to whichever node actually receives DOM focus', async () => {
    const wrapper = mountCanvas({ nodes: grid(), readonly: true })

    await nodeDiv(wrapper, 'c').trigger('focus')

    expect(nodeDiv(wrapper, 'c').attributes('tabindex')).toBe('0')
    expect(nodeDiv(wrapper, 'a').attributes('tabindex')).toBe('-1')
  })

  it('carries role=button and aria-pressed reflecting selection', () => {
    const wrapper = mountCanvas({ nodes: grid(), readonly: true, selectedNodeId: 'b' })

    expect(nodeDiv(wrapper, 'a').attributes('role')).toBe('button')
    expect(nodeDiv(wrapper, 'a').attributes('aria-pressed')).toBe('false')
    expect(nodeDiv(wrapper, 'b').attributes('aria-pressed')).toBe('true')
  })
})

describe('WorkflowCanvas accessible name states kind, name and state (#14609)', () => {
  it('announces kind and name for a workflow authoring node with no status concept', () => {
    const wrapper = mountCanvas({ nodes: WORKFLOW_NODES })
    const expected = en.workflow.canvas.nodeAriaLabel
      .replace('{kind}', en.workflow.canvas.stepLabel)
      .replace('{name}', en.workflow.canvas.stepLabel)

    expect(nodeDiv(wrapper, 'n1').attributes('aria-label')).toBe(expected)
  })

  it('announces kind, name and status for an org-person node', () => {
    const wrapper = mountCanvas({ nodes: grid(), readonly: true })
    const expected = en.workflow.canvas.nodeAriaLabelWithState
      .replace('{kind}', en.llc.orgChart.aiAgent)
      .replace('{name}', 'Ada')
      .replace('{state}', en.llc.canvasRules.status.active)

    expect(nodeDiv(wrapper, 'a').attributes('aria-label')).toBe(expected)
  })

  it('announces the human owner kind for a human org-person node', () => {
    const wrapper = mountCanvas({ nodes: grid(), readonly: true })
    const expected = en.workflow.canvas.nodeAriaLabelWithState
      .replace('{kind}', en.llc.orgChart.human)
      .replace('{name}', 'Cid')
      .replace('{state}', en.llc.canvasRules.status.paused)

    expect(nodeDiv(wrapper, 'c').attributes('aria-label')).toBe(expected)
  })
})

describe('WorkflowCanvas Enter/Space/Escape (#14609)', () => {
  it('Enter selects the focused node — the same effect as a click', async () => {
    const wrapper = mountCanvas({ nodes: grid(), readonly: true })
    await keydown(wrapper, 'b', 'Enter')

    expect(wrapper.emitted('node-selected')).toEqual([['b']])
  })

  it('Space selects the focused node', async () => {
    const wrapper = mountCanvas({ nodes: grid(), readonly: true })
    await keydown(wrapper, 'b', ' ')

    expect(wrapper.emitted('node-selected')).toEqual([['b']])
  })

  it('Escape deselects', async () => {
    const wrapper = mountCanvas({ nodes: grid(), readonly: true, selectedNodeId: 'b' })
    await keydown(wrapper, 'b', 'Escape')

    expect(wrapper.emitted('node-selected')).toEqual([[null]])
  })

  it('does not hijack a space typed into the node’s own input', async () => {
    const wrapper = mountCanvas({ nodes: WORKFLOW_NODES })
    const input = wrapper.get('.workflow-node.step input')
    await input.trigger('keydown', { key: ' ' })

    expect(wrapper.emitted('node-selected')).toBeUndefined()
  })
})

describe('WorkflowCanvas arrow-key focus movement follows visual order (#14609)', () => {
  it('ArrowRight from the top-left node focuses the node to its right', async () => {
    const wrapper = mountCanvas({ nodes: grid(), readonly: true }, { attach: true })
    await nodeDiv(wrapper, 'a').trigger('focus')

    await keydown(wrapper, 'a', 'ArrowRight')

    expect(document.activeElement).toBe(nodeDiv(wrapper, 'b').element)
    wrapper.unmount()
  })

  it('ArrowDown from the top-left node focuses the node below it', async () => {
    const wrapper = mountCanvas({ nodes: grid(), readonly: true }, { attach: true })
    await nodeDiv(wrapper, 'a').trigger('focus')

    await keydown(wrapper, 'a', 'ArrowDown')

    expect(document.activeElement).toBe(nodeDiv(wrapper, 'c').element)
    wrapper.unmount()
  })

  it('ArrowLeft from the bottom-right node focuses the node to its left', async () => {
    const wrapper = mountCanvas({ nodes: grid(), readonly: true }, { attach: true })
    await nodeDiv(wrapper, 'd').trigger('focus')

    await keydown(wrapper, 'd', 'ArrowLeft')

    expect(document.activeElement).toBe(nodeDiv(wrapper, 'c').element)
    wrapper.unmount()
  })
})

describe('WorkflowCanvas arrow-key direction follows writing direction in RTL (#14609)', () => {
  it('ArrowRight moves focus toward the visually-left node in an RTL document', async () => {
    document.documentElement.setAttribute('dir', 'rtl')
    const wrapper = mountCanvas({ nodes: grid(), readonly: true }, { locale: 'ar', attach: true })
    await nodeDiv(wrapper, 'b').trigger('focus')

    // 'b' sits visually to the right of 'a'. In RTL, ArrowRight is "back" in
    // reading order — the same node ArrowLeft would reach in LTR.
    await keydown(wrapper, 'b', 'ArrowRight')

    expect(document.activeElement).toBe(nodeDiv(wrapper, 'a').element)
    wrapper.unmount()
  })

  it('ArrowLeft moves focus toward the visually-right node in an RTL document', async () => {
    document.documentElement.setAttribute('dir', 'rtl')
    const wrapper = mountCanvas({ nodes: grid(), readonly: true }, { locale: 'ar', attach: true })
    await nodeDiv(wrapper, 'a').trigger('focus')

    await keydown(wrapper, 'a', 'ArrowLeft')

    expect(document.activeElement).toBe(nodeDiv(wrapper, 'b').element)
    wrapper.unmount()
  })
})

describe('WorkflowCanvas Ctrl+Arrow moves the focused node (#14609)', () => {
  it('moves the node by a fixed step, mirroring a drag’s node-moved emit', async () => {
    const wrapper = mountCanvas({ nodes: grid(), readonly: false })
    await keydown(wrapper, 'a', 'ArrowRight', { ctrlKey: true })

    expect(wrapper.emitted('node-moved')).toEqual([['a', { x: 20, y: 0 }]])
  })

  it('never moves the node when readonly — dragging is a mutation the read-only canvas must not offer', async () => {
    const wrapper = mountCanvas({ nodes: grid(), readonly: true })
    await keydown(wrapper, 'a', 'ArrowRight', { ctrlKey: true })

    expect(wrapper.emitted('node-moved')).toBeUndefined()
  })

  it('clamps to zero rather than moving off-canvas', async () => {
    const wrapper = mountCanvas({ nodes: grid(), readonly: false })
    await keydown(wrapper, 'a', 'ArrowLeft', { ctrlKey: true })

    expect(wrapper.emitted('node-moved')).toEqual([['a', { x: 0, y: 0 }]])
  })
})

describe('WorkflowCanvas focus survives a canvas re-layout (#14609)', () => {
  it('keeps the same node focused after `nodes` is replaced with new objects carrying the same ids', async () => {
    const wrapper = mountCanvas({ nodes: grid(), readonly: true }, { attach: true })
    nodeDiv(wrapper, 'c').element.focus()
    expect(document.activeElement).toBe(nodeDiv(wrapper, 'c').element)

    // Simulate OrgChart.vue's relayout watcher: a brand new array of new node
    // objects, same ids, different position references.
    const relaidOut = grid().map((n) => ({ ...n, position: { ...n.position } }))
    await wrapper.setProps({ nodes: relaidOut })

    expect(document.activeElement).toBe(nodeDiv(wrapper, 'c').element)
    expect(nodeDiv(wrapper, 'c').attributes('tabindex')).toBe('0')
    wrapper.unmount()
  })
})

describe('WorkflowCanvas keyboard instructions are exposed to assistive tech (#14609)', () => {
  it('describes every node, and only advertises the move shortcut when not readonly', () => {
    const editable = mountCanvas({ nodes: WORKFLOW_NODES, readonly: false })
    expect(editable.text()).toContain(en.workflow.canvas.a11yInstructions)
    expect(editable.text()).toContain(en.workflow.canvas.a11yInstructionsMove)
    const describedBy = nodeDiv(editable, 'n1').attributes('aria-describedby')
    expect(describedBy).toBeTruthy()
    expect(describedBy!.split(' ')).toHaveLength(2)

    const readonlyWrapper = mountCanvas({ nodes: grid(), readonly: true })
    expect(readonlyWrapper.text()).not.toContain(en.workflow.canvas.a11yInstructionsMove)
    const readonlyDescribedBy = nodeDiv(readonlyWrapper, 'a').attributes('aria-describedby')
    expect(readonlyDescribedBy!.split(' ')).toHaveLength(1)
  })
})
