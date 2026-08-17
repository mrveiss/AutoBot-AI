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
import type { CanvasNode } from '../canvasNode'

const PROCESS_NODES: CanvasNode[] = [
  {
    id: 'org-process:wf-1',
    type: 'org-process',
    position: { x: 0, y: 0 },
    data: { workflow_id: 'wf-1', role_name: 'Head of Ops' },
    connections: [],
  },
]

function mountCanvas() {
  const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
  return mount(WorkflowCanvas, {
    props: { modelValue: PROCESS_NODES, readOnly: true },
    global: { plugins: [i18n] },
  })
}

describe('org-process node accessible description', () => {
  it('renders the description the locale file defines, not a bare key', () => {
    // Read from the locale file rather than hardcoding the sentence: deleting
    // the key makes this `undefined`, which cannot match the key path vue-i18n
    // falls back to rendering. Hardcoding the English text would let the key
    // be deleted while the assertion still passed against a literal.
    const expected = (en as Record<string, any>).llc?.orgChart?.processOpensWorkflow
    expect(expected).toBeTruthy()

    const title = mountCanvas().find('.org-title')
    expect(title.exists()).toBe(true)
    expect(title.attributes('aria-label')).toBe(expected)
  })

  it('exposes the same description on hover as to a screen reader', () => {
    const expected = (en as Record<string, any>).llc?.orgChart?.processOpensWorkflow
    const title = mountCanvas().find('.org-title')

    expect(title.attributes('title')).toBe(expected)
  })

  it('still renders the workflow id as the visible label', () => {
    // The description must not have replaced the node's own text.
    expect(mountCanvas().find('.org-title').text()).toBe('wf-1')
  })
})
