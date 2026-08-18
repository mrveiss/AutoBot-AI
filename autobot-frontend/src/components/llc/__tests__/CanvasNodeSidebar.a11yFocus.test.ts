// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// GH#14609: the Org Chart drawer (this component) is the destination of the
// canvas's own new keyboard-selection path (Enter/Space on a node). It must
// trap Tab/Shift+Tab while open, move focus into itself on mount, and give
// focus back to whatever triggered it — the canvas node, in
// `OrgChart.vue`'s usage — once it unmounts. `OrgChart.vue` gates this
// component behind `v-if="drawerOpen && selectedNode"`, so "on close" is
// "on unmount", which is exactly `useFocusRestore()`'s mount-based mode.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { defineComponent, h } from 'vue'
import en from '@/i18n/locales/en.json'

const get = vi.fn()

vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get, post: vi.fn() }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

import CanvasNodeSidebar from '../CanvasNodeSidebar.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

const AGENT_NODE = {
  id: 'dev',
  node_id: 'pk-dev-1',
  name: 'Grace',
  title: 'Engineer',
  status: 'idle' as const,
  adapter_type: 'claude_code',
  is_human: false,
  last_heartbeat: null,
  budget_spent: 0,
  budget_total: 0,
  assigned_item_count: 0,
  parent_id: null,
  children: [],
}

function mountSidebar() {
  return mount(CanvasNodeSidebar, {
    props: { node: AGENT_NODE, companyId: 'c1', terminating: false },
    global: { plugins: [i18n], stubs: { HandoffModal: true } },
    attachTo: document.body,
  })
}

const getFocusables = (root: Element) =>
  Array.from(
    root.querySelectorAll<HTMLElement>(
      'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])',
    ),
  )

const dispatchTab = (el: Element, shiftKey = false) => {
  const event = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true, shiftKey })
  el.dispatchEvent(event)
  return event
}

beforeEach(() => {
  get.mockReset()
  document.body.replaceChildren()
})

describe('CanvasNodeSidebar focus management (#14609)', () => {
  it('moves focus to the first focusable element (the close button) on mount', async () => {
    const wrapper = mountSidebar()
    await flushPromises()

    const panel = wrapper.get('[data-testid="node-sidebar"]').element as HTMLElement
    const first = getFocusables(panel)[0]
    expect(document.activeElement).toBe(first)
    wrapper.unmount()
  })

  it('Tab on the last focusable wraps to the first', async () => {
    const wrapper = mountSidebar()
    await flushPromises()
    const panel = wrapper.get('[data-testid="node-sidebar"]').element as HTMLElement
    const focusables = getFocusables(panel)
    const first = focusables[0]
    const last = focusables[focusables.length - 1]
    last.focus()

    const event = dispatchTab(panel, false)

    expect(event.defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(first)
    wrapper.unmount()
  })

  it('Shift+Tab on the first focusable wraps to the last', async () => {
    const wrapper = mountSidebar()
    await flushPromises()
    const panel = wrapper.get('[data-testid="node-sidebar"]').element as HTMLElement
    const focusables = getFocusables(panel)
    const first = focusables[0]
    const last = focusables[focusables.length - 1]
    first.focus()

    const event = dispatchTab(panel, true)

    expect(event.defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(last)
    wrapper.unmount()
  })

  it('emits close on Escape', async () => {
    const wrapper = mountSidebar()
    await flushPromises()

    await wrapper.get('[data-testid="node-sidebar"]').trigger('keydown', { key: 'Escape' })

    expect(wrapper.emitted('close')).toBeTruthy()
    wrapper.unmount()
  })

  it('restores focus to the triggering element once the parent unmounts it (v-if close, per OrgChart.vue)', async () => {
    // Mirrors OrgChart.vue's own gate: `v-if="drawerOpen && selectedNode"`.
    const Host = defineComponent({
      props: { show: { type: Boolean, required: true } },
      setup(props) {
        return () =>
          h('div', [
            h('button', { id: 'origin-node' }, 'origin canvas node'),
            props.show
              ? h(CanvasNodeSidebar, { node: AGENT_NODE, companyId: 'c1', terminating: false })
              : null,
          ])
      },
    })
    const wrapper = mount(Host, {
      props: { show: false },
      global: { plugins: [i18n], stubs: { HandoffModal: true } },
      attachTo: document.body,
    })
    const origin = wrapper.get('#origin-node').element as HTMLElement
    origin.focus()
    expect(document.activeElement).toBe(origin)

    await wrapper.setProps({ show: true })
    await flushPromises()
    expect(document.activeElement).not.toBe(origin)

    await wrapper.setProps({ show: false })
    await flushPromises()

    expect(document.activeElement).toBe(origin)
    wrapper.unmount()
  })
})
