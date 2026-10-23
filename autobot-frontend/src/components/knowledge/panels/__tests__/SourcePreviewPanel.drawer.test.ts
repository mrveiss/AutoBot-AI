// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// SourcePreviewPanel on the kit BaseDrawer (#14780): a labelled dialog carrying the document,
// its path and the footer actions; the drawer's own close closes it; the left-edge handle
// still resizes the width within 300..800 px.

import { describe, it, expect, vi, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import SourcePreviewPanel, { type SourceDocument } from '../SourcePreviewPanel.vue'

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', missingWarn: false, messages: { en } })
const L = en.knowledge.panels.sourcePreview
const doc: SourceDocument = { id: 'd1', title: 'Install guide', content: 'one two three', path: 'docs/install.md', type: 'guide' }

function render(document: SourceDocument | null = doc) {
  return mount(SourcePreviewPanel, {
    props: { modelValue: true, document },
    global: { plugins: [i18n], stubs: { Teleport: true, Icon: true } },
    attachTo: window.document.body,
  })
}

afterEach(() => { window.document.body.innerHTML = '' })

describe('SourcePreviewPanel on BaseDrawer', () => {
  it('is a labelled dialog with the title, path and both footer actions', async () => {
    const w = render()
    await flushPromises()
    const panel = w.find('[role="dialog"]')
    expect(panel.exists()).toBe(true)
    expect(w.find(`#${panel.attributes('aria-labelledby')}`).text()).toContain('Install guide')
    expect(w.find('.aui-drawer-subtitle').text()).toBe('docs/install.md')
    const actions = w.find('.aui-drawer-actions').text()
    expect(actions).toContain(L.copy)
    expect(actions).toContain(L.openInKnowledgeManager)
    w.unmount()
  })

  it("the drawer's close button closes it", async () => {
    const w = render()
    await w.find('.aui-drawer-close').trigger('click')
    expect(w.emitted('update:modelValue')).toEqual([[false]])
    expect(w.find('.aui-drawer-close').attributes('aria-label')).toBe(L.closePanel)
    w.unmount()
  })

  it('Escape and a backdrop click close it, as the drawer does', async () => {
    const w = render()
    await w.find('.aui-drawer-overlay').trigger('keydown', { key: 'Escape' })
    await w.find('.aui-drawer-overlay').trigger('click')
    expect(w.emitted('update:modelValue')).toEqual([[false], [false]])
    w.unmount()
  })

  it('the left-edge handle resizes the drawer, clamped to 300..800 px', async () => {
    const w = render()
    const width = () => (w.find('.aui-drawer').element as HTMLElement).style.width
    expect(width()).toBe('400px')
    await w.find('.resize-handle').trigger('mousedown')
    window.document.dispatchEvent(new MouseEvent('mousemove', { clientX: window.innerWidth - 650 }))
    await flushPromises()
    expect(width()).toBe('650px')
    window.document.dispatchEvent(new MouseEvent('mousemove', { clientX: window.innerWidth - 2000 }))
    await flushPromises()
    expect(width()).toBe('800px')
    window.document.dispatchEvent(new MouseEvent('mouseup'))
    // mouseup ends the drag: a later move no longer resizes
    window.document.dispatchEvent(new MouseEvent('mousemove', { clientX: window.innerWidth - 500 }))
    await flushPromises()
    expect(width()).toBe('800px')
    w.unmount()
  })

  it('the Copied feedback timer is cleared on unmount, so it never fires afterwards', async () => {
    vi.useFakeTimers()
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } })
    const w = render()
    await w.findAll('.aui-drawer-actions button')[0].trigger('click')
    await flushPromises()
    expect(vi.getTimerCount()).toBe(1)
    w.unmount()
    expect(vi.getTimerCount()).toBe(0)
    vi.useRealTimers()
  })

  it('without a document it shows the empty state and disables the actions', () => {
    const w = render(null)
    expect(w.text()).toContain(L.noDocument)
    expect(w.findAll('.aui-drawer-actions button').every((b) => b.attributes('disabled') !== undefined)).toBe(true)
    w.unmount()
  })
})
