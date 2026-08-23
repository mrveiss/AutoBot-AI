// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #13963: the org-process node is a way in to the automation module, but the
// only text it renders is a workflow id and a role name — neither says that
// activating it goes anywhere. `processOpensWorkflow` carries that, and it
// shipped translated into all 11 locales while no component referenced it.
//
// A translation key nothing renders is a string eleven translators maintain
// for no reader, and it goes unnoticed precisely because nothing fails. This
// asserts the rendered output, so it fails if the template stops referencing
// the key AND if the key is removed from the locale file.

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

import WorkflowCanvas from '../WorkflowCanvas.vue'
import { buildProcessCanvasNodes } from '@/composables/llc/orgCanvasGraph'

// Built by the real producer rather than hand-rolled. A hand-written node can
// drift into a shape nothing actually emits — and then the test passes against
// data the canvas never receives.
const PROCESS_NODES = buildProcessCanvasNodes(
  [{ role_id: 'role-1', role_name: 'Head of Ops', workflow_id: 'wf-1' }],
  0,
)

// Read the sentence from the locale file rather than hardcoding it: deleting
// the key makes this `undefined`, which cannot match the key path vue-i18n
// falls back to rendering. A hardcoded English string would let the key be
// deleted while this file still passed against a literal.
const LOCALE = en as unknown as {
  llc: { orgChart: { processOpensWorkflow?: string } }
}
const EXPECTED = LOCALE.llc.orgChart.processOpensWorkflow

// #14860: one shared instance for the whole file. A fresh createI18n per
// mount re-ingested the ~400KB message bundle every time; nothing here
// mutates the instance, so building it once is enough.
const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  messages: { en },
})

function mountCanvas() {
  return mount(WorkflowCanvas, {
    props: { nodes: PROCESS_NODES, selectedNodeId: null, readonly: true },
    global: { plugins: [i18n] },
  })
}

describe('org-process node accessible description', () => {
  it('defines the description in the locale file', () => {
    expect(EXPECTED).toBeTruthy()
  })

  it('renders the description the locale file defines, not a bare key', () => {
    const title = mountCanvas().find('.org-title')

    expect(title.exists()).toBe(true)
    expect(title.attributes('aria-label')).toBe(EXPECTED)
  })

  it('exposes the same description on hover as to a screen reader', () => {
    expect(mountCanvas().find('.org-title').attributes('title')).toBe(EXPECTED)
  })

  it('still renders the workflow id as the visible label', () => {
    // The description must not have replaced the node's own text.
    expect(mountCanvas().find('.org-title').text()).toBe('wf-1')
  })
})
