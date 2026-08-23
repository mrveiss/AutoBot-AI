// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #14549: the process node's own detach control. It must not call the API
// itself — `WorkflowCanvas.vue` is shared with real workflow editing — and it
// must not hijack the node's own click, which navigates to the workflow
// builder (`OrgChart.vue`'s `onCanvasNodeSelected`).

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { memoizeByLocale } from '@/test/utils/i18n-cache'
import en from '@/i18n/locales/en.json'
import ar from '@/i18n/locales/ar.json'

import WorkflowCanvas from '../WorkflowCanvas.vue'
import { buildProcessCanvasNodes } from '@/composables/llc/orgCanvasGraph'

const PROCESS_NODES = buildProcessCanvasNodes(
  [{ role_id: 'role-1', role_name: 'Head of Ops', workflow_id: 'wf-1' }],
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

function mountCanvas(locale: 'en' | 'ar' = 'en') {
  const i18n = makeI18n(locale)
  return mount(WorkflowCanvas, {
    props: { nodes: PROCESS_NODES, selectedNodeId: null, readonly: true },
    global: { plugins: [i18n] },
  })
}

describe('org-process node detach control (#14549)', () => {
  it('emits process-detached with the role and workflow id, not node-selected', async () => {
    const wrapper = mountCanvas()

    await wrapper.find('[data-testid="process-detach-btn"]').trigger('click')

    expect(wrapper.emitted('process-detached')).toEqual([['role-1', 'wf-1']])
    // The click must not have bubbled to the node's own click handler, which
    // would have selected it and (in OrgChart.vue) navigated away.
    expect(wrapper.emitted('node-selected')).toBeUndefined()
  })

  it('renders regardless of the readonly prop', () => {
    // OrgChart.vue always mounts this canvas `readonly` (view-only authoring
    // controls). The detach control is an LLC action, not an authoring one,
    // and must not be gated behind the same flag as `addStepNode`/`deleteNode`.
    const wrapper = mountCanvas()

    expect(wrapper.find('[data-testid="process-detach-btn"]').exists()).toBe(true)
  })

  it('names the workflow and role in its accessible name', () => {
    const wrapper = mountCanvas()
    const expected = (en as { llc: { orgChart: { processDetach: string } } }).llc.orgChart
      .processDetach
      .replace('{workflow}', 'wf-1')
      .replace('{role}', 'Head of Ops')

    expect(wrapper.find('[data-testid="process-detach-btn"]').attributes('aria-label')).toBe(
      expected,
    )
  })

  it('names the workflow and role in a non-English (RTL) locale', () => {
    const wrapper = mountCanvas('ar')
    const expected = (ar as { llc: { orgChart: { processDetach: string } } }).llc.orgChart
      .processDetach
      .replace('{workflow}', 'wf-1')
      .replace('{role}', 'Head of Ops')

    expect(wrapper.find('[data-testid="process-detach-btn"]').attributes('aria-label')).toBe(
      expected,
    )
  })
})
