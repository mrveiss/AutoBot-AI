// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #19118: stored KB content must never reach the DOM as executable markup.
 * Mounts the real KnowledgeEntries and renders an entry in the view dialog.
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { nextTick } from 'vue'
import { createI18n } from 'vue-i18n'
import KnowledgeEntries from '../KnowledgeEntries.vue'

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {}, params: {} }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

async function renderEntry(content: string): Promise<HTMLElement> {
  const wrapper = mount(KnowledgeEntries, {
    attachTo: document.body,
    global: {
      plugins: [createPinia(), createI18n({ legacy: false, locale: 'en', missingWarn: false, messages: { en: {} } })],
    },
  })
  const vm = wrapper.vm as unknown as Record<string, unknown>
  vm.currentEntry = { id: 'e1', title: 't', content, tags: [], metadata: {} }
  vm.dialogMode = 'view'
  vm.manageTab = 'manage'
  vm.showDialog = true
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
