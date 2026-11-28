// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #19118: stored KB content must never reach the DOM as executable markup.
 * Mounts the real entry dialog (KnowledgeEntries renders it) and renders an entry in view mode.
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createI18n } from 'vue-i18n'
import KnowledgeEntryDialog from '../KnowledgeEntryDialog.vue'

async function renderEntry(content: string): Promise<HTMLElement> {
  mount(KnowledgeEntryDialog, {
    attachTo: document.body,
    props: {
      modelValue: true,
      mode: 'view',
      entry: { id: 'e1', title: 't', content, tags: [], metadata: {}, category: 'c', type: 'document', source: 's', createdAt: new Date(), updatedAt: new Date() },
      categories: [],
      canSave: true,
    },
    global: { plugins: [createI18n({ legacy: false, locale: 'en', missingWarn: false, messages: { en: {} } })] },
  })
  await nextTick()
  await nextTick()
  const viewer = document.body.querySelector('.content-viewer')
  expect(viewer).not.toBeNull()
  const el = document.createElement('div')
  el.innerHTML = viewer!.innerHTML
  return el
}

describe('KnowledgeEntries content viewer (#19118)', () => {
  it('neutralises script, img onerror and javascript: links', async () => {
    const el = await renderEntry(
      '<script>alert(1)</script><img src=x onerror="alert(2)"><a href="javascript:alert(3)">x</a><svg onload=alert(4)>',
    )
    expect(el.querySelector('script, img, a, svg')).toBeNull()
    expect(el.innerHTML).not.toMatch(/<[a-z][^>]*\son\w+=/i)
    expect(el.querySelectorAll('[href]').length).toBe(0)
  })

  it('still renders bold, italic, code and newlines', async () => {
    const el = await renderEntry('**b** *i* `c`\nnext')
    expect(el.querySelector('strong')?.textContent).toBe('b')
    expect(el.querySelector('em')?.textContent).toBe('i')
    expect(el.querySelector('code')?.textContent).toBe('c')
    expect(el.querySelector('br')).not.toBeNull()
  })
})
