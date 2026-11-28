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
import { defineComponent, nextTick, ref } from 'vue'
import { BaseDrawer } from '@autobot/ui'
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

// The node sidebar renders inside OrgChart's kit BaseDrawer (#14780), which owns the dialog
// semantics #14609 asked for. This mounts that exact composition (drawer + the real sidebar,
// opened from a trigger) so the guarantees stay pinned to the node sidebar itself.
const Host = defineComponent({
  components: { BaseDrawer, CanvasNodeSidebar },
  setup() {
    const open = ref(false)
    return { open, node: AGENT_NODE }
  },
  template: `<button id="origin-node" @click="open = true">origin canvas node</button>
    <BaseDrawer v-model="open" title="Agent detail" width="24rem" flush close-label="Close">
      <CanvasNodeSidebar :node="node" company-id="c1" :terminating="false" />
    </BaseDrawer>`,
})

async function openDrawer() {
  const wrapper = mount(Host, {
    global: { plugins: [i18n], stubs: { HandoffModal: true, Teleport: true } },
    attachTo: document.body,
  })
  const origin = document.getElementById('origin-node') as HTMLElement
  origin.focus()
  await wrapper.find('#origin-node').trigger('click')
  await flushPromises()
  // the drawer's Transition calls focusFirst on after-enter; jsdom has no animation, so run it
  ;(wrapper.find('[role="dialog"]').element as HTMLElement).querySelector<HTMLElement>('button')?.focus()
  return { wrapper, origin, panel: wrapper.find('[role="dialog"]').element as HTMLElement }
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
  get.mockResolvedValue([])
  document.body.replaceChildren()
})

describe('CanvasNodeSidebar in its drawer: focus management (#14609, #14780)', () => {
  it('is a labelled modal dialog that contains the node sidebar', async () => {
    const { wrapper, panel } = await openDrawer()
    expect(panel.getAttribute('aria-modal')).toBe('true')
    expect(document.getElementById(panel.getAttribute('aria-labelledby')!)?.textContent).toContain('Agent detail')
    expect(panel.querySelector('[data-testid="node-sidebar"]')).not.toBeNull()
    wrapper.unmount()
  })

  it('the sidebar itself is no longer a second dialog', async () => {
    const { wrapper, panel } = await openDrawer()
    expect(panel.querySelectorAll('[role="dialog"]').length).toBe(0)
    wrapper.unmount()
  })

  it('Tab on the last focusable wraps to the first, Shift+Tab on the first to the last', async () => {
    const { wrapper, panel } = await openDrawer()
    const focusables = getFocusables(panel)
    const first = focusables[0]
    const last = focusables[focusables.length - 1]
    last.focus()
    expect(dispatchTab(panel).defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(first)
    first.focus()
    expect(dispatchTab(panel, true).defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(last)
    wrapper.unmount()
  })

  it('Escape closes it and focus returns to the triggering node', async () => {
    const { wrapper, origin } = await openDrawer()
    await wrapper.find('.aui-drawer-overlay').trigger('keydown', { key: 'Escape' })
    await nextTick()
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(document.activeElement).toBe(origin)
    wrapper.unmount()
  })
})
