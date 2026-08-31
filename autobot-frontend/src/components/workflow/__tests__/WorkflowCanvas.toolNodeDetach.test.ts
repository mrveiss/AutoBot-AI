// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #14597: the tool node's own per-role detach controls. It must not call the
// API itself — `WorkflowCanvas.vue` is shared with real workflow editing —
// and it must not hijack the node's own click. Mirrors
// `WorkflowCanvas.processNodeDetach.test.ts` for the tool node's sibling
// control, with the added wrinkle that a tool node can carry several roles
// and so several detach controls.

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { memoizeByLocale } from '@/test/utils/i18n-cache'
import en from '@/i18n/locales/en.json'
import ar from '@/i18n/locales/ar.json'

import WorkflowCanvas from '../WorkflowCanvas.vue'
import { buildToolCanvasNodes } from '@/composables/llc/orgCanvasGraph'

const ONE_ROLE_TOOL_NODES = buildToolCanvasNodes(
  [{ role_id: 'role-1', role_name: 'Head of Ops', tool_name: 'web_search' }],
  [],
  0,
)

const SHARED_TOOL_NODES = buildToolCanvasNodes(
  [
    { role_id: 'role-1', role_name: 'Head of Ops', tool_name: 'web_search' },
    { role_id: 'role-2', role_name: 'SRE', tool_name: 'web_search' },
  ],
  [],
  0,
)

// #14860: memoized per locale. This helper ran on EVERY mount and each call
// re-ingested the ~400KB `en` and `ar` message bundles. The locale is a real
// parameter here, so a blind hoist would be wrong — one instance per locale
// is not. Nothing in this file mutates the returned instance.
const makeI18n = memoizeByLocale((locale: string) =>
  createI18n({
    legacy: false,
    locale,
    fallbackLocale: 'en',
    messages: { en, ar },
  }),
)

function mountCanvas(nodes = ONE_ROLE_TOOL_NODES, locale: 'en' | 'ar' = 'en') {
  const i18n = makeI18n(locale)
  return mount(WorkflowCanvas, {
    props: { nodes, selectedNodeId: null, readonly: true },
    global: { plugins: [i18n] },
  })
}

describe('org-tool node (#14597)', () => {
  it('renders the tool name as its title', () => {
    const wrapper = mountCanvas()

    expect(wrapper.find('.org-title').text()).toBe('web_search')
  })

  it('renders one role chip per role that carries the tool, sharing one node', () => {
    const wrapper = mountCanvas(SHARED_TOOL_NODES)

    // Positive companion to the detach-control tests below: the node itself
    // rendered, so an absent chip cannot be blamed on the whole node failing
    // to draw.
    expect(wrapper.findAll('.tool-role-chip')).toHaveLength(2)
    expect(wrapper.text()).toContain('Head of Ops')
    expect(wrapper.text()).toContain('SRE')
  })

  it('emits tool-detached with the role and tool name, not node-selected', async () => {
    const wrapper = mountCanvas()

    await wrapper.find('[data-testid="tool-detach-btn"]').trigger('click')

    expect(wrapper.emitted('tool-detached')).toEqual([['role-1', 'web_search']])
    // The click must not have bubbled to the node's own click handler.
    expect(wrapper.emitted('node-selected')).toBeUndefined()
  })

  it('detaches the correct role when the node carries several', async () => {
    const wrapper = mountCanvas(SHARED_TOOL_NODES)

    const buttons = wrapper.findAll('[data-testid="tool-detach-btn"]')
    expect(buttons).toHaveLength(2)
    await buttons[1].trigger('click')

    expect(wrapper.emitted('tool-detached')).toEqual([['role-2', 'web_search']])
  })

  it('renders regardless of the readonly prop', () => {
    // OrgChart.vue always mounts this canvas `readonly` (view-only authoring
    // controls). The detach control is an LLC action, not an authoring one,
    // and must not be gated behind the same flag as `addStepNode`/`deleteNode`.
    const wrapper = mountCanvas()

    expect(wrapper.find('[data-testid="tool-detach-btn"]').exists()).toBe(true)
  })

  it('names the tool and role in its accessible name', () => {
    const wrapper = mountCanvas()
    const expected = (en as { llc: { orgChart: { toolDetach: string } } }).llc.orgChart.toolDetach
      .replace('{tool}', 'web_search')
      .replace('{role}', 'Head of Ops')

    expect(wrapper.find('[data-testid="tool-detach-btn"]').attributes('aria-label')).toBe(
      expected,
    )
  })

  it('names the tool and role in a non-English (RTL) locale', () => {
    const wrapper = mountCanvas(ONE_ROLE_TOOL_NODES, 'ar')
    const expected = (ar as { llc: { orgChart: { toolDetach: string } } }).llc.orgChart.toolDetach
      .replace('{tool}', 'web_search')
      .replace('{role}', 'Head of Ops')

    expect(wrapper.find('[data-testid="tool-detach-btn"]').attributes('aria-label')).toBe(
      expected,
    )
  })
})
