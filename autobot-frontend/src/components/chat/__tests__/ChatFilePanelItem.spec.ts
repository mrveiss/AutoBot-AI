// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #22349: one file card of the Chat files panel -- named controls, conditional actions, the More menu and rename.
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { BaseDropdownMenu } from '@autobot/ui'

vi.mock('vue-i18n', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-i18n')>()),
  useI18n: () => ({ t: (k: string) => k, locale: { value: 'en' } }),
}))

import ChatFilePanelItem from '../ChatFilePanelItem.vue'

const file = {
  file_id: 'f1', filename: 'notes.txt', file_type: 'upload', mime_type: 'text/plain',
  size_bytes: 5, upload_timestamp: '2026-11-01T10:00:00Z', download_url: '/d/f1',
} as const

const mountItem = (props: Record<string, unknown> = {}) =>
  mount(ChatFilePanelItem, {
    props: { file, selected: false, icon: 'file-alt', sizeLabel: '5 B', previewable: true, editable: true, ...props },
    global: { mocks: { $t: (k: string) => k }, stubs: { Icon: true } },
  })

const menu = (wrapper: ReturnType<typeof mountItem>) => wrapper.findComponent(BaseDropdownMenu)

describe('ChatFilePanelItem (#22349)', () => {
  it('names the checkbox per file and emits select', async () => {
    const wrapper = mountItem()
    const box = wrapper.get('input[type="checkbox"]')
    expect(box.attributes('aria-label')).toBe('chat.filePanel.selectFile')
    await box.trigger('change')
    expect(wrapper.emitted('select')).toHaveLength(1)
  })

  it('offers Preview only for a previewable file', () => {
    expect(mountItem().find('[data-testid="action-preview"]').exists()).toBe(true)
    expect(mountItem({ previewable: false }).find('[data-testid="action-preview"]').exists()).toBe(false)
  })

  it('offers Edit in the More menu only for an editable file; Rename and Duplicate always', () => {
    const keys = (w: ReturnType<typeof mountItem>) => (menu(w).props('items') as { key: string }[]).map((i) => i.key)
    expect(keys(mountItem())).toEqual(['edit', 'rename', 'duplicate'])
    expect(keys(mountItem({ editable: false }))).toEqual(['rename', 'duplicate'])
  })

  it('shows the AI generated badge only for generated files', () => {
    expect(mountItem().find('[data-testid="ai-badge"]').exists()).toBe(false)
    expect(mountItem({ file: { ...file, file_type: 'generated' } }).find('[data-testid="ai-badge"]').exists()).toBe(true)
  })

  it('emits preview, download and delete from the visible icon buttons', async () => {
    const wrapper = mountItem()
    await wrapper.get('[data-testid="action-preview"] button').trigger('click')
    await wrapper.get('[data-testid="action-download"] button').trigger('click')
    await wrapper.get('[data-testid="action-delete"] button').trigger('click')
    expect(['preview', 'download', 'delete'].map((e) => wrapper.emitted(e)?.length)).toEqual([1, 1, 1])
  })

  it('every icon-only button has an accessible name', () => {
    const wrapper = mountItem()
    // ChatHeaderIconButton puts data-testid on its tooltip wrapper; the button is inside it.
    for (const id of ['action-preview', 'action-download', 'action-delete']) {
      expect(wrapper.get(`[data-testid="${id}"] button`).attributes('aria-label')).toBeTruthy()
    }
    expect(wrapper.get('[data-testid="action-more"]').attributes('aria-label')).toBeTruthy()
  })

  it('opens the same More menu on right-click', async () => {
    const wrapper = mountItem()
    expect(menu(wrapper).props('open')).toBe(false)
    await wrapper.get('[data-testid="file-item"]').trigger('contextmenu')
    expect(menu(wrapper).props('open')).toBe(true)
  })

  it('emits edit and duplicate from the menu', async () => {
    const wrapper = mountItem()
    menu(wrapper).vm.$emit('select', 'edit')
    menu(wrapper).vm.$emit('select', 'duplicate')
    expect(wrapper.emitted('edit')).toHaveLength(1)
    expect(wrapper.emitted('duplicate')).toHaveLength(1)
  })

  it('renames: Rename opens a field filled with the name, Enter saves the trimmed name', async () => {
    const wrapper = mountItem()
    menu(wrapper).vm.$emit('select', 'rename')
    await wrapper.vm.$nextTick()
    const input = wrapper.get('input:not([type="checkbox"])')
    expect((input.element as HTMLInputElement).value).toBe('notes.txt')
    await input.setValue('  plan.txt ')
    await input.trigger('keyup', { key: 'Enter' })
    expect(wrapper.emitted('rename')?.[0]).toEqual(['plan.txt'])
    expect(wrapper.find('input:not([type="checkbox"])').exists()).toBe(false)
  })

  it('Escape cancels a rename without emitting', async () => {
    const wrapper = mountItem()
    menu(wrapper).vm.$emit('select', 'rename')
    await wrapper.vm.$nextTick()
    await wrapper.get('input:not([type="checkbox"])').trigger('keyup', { key: 'Escape' })
    expect(wrapper.emitted('rename')).toBeUndefined()
    expect(wrapper.find('input:not([type="checkbox"])').exists()).toBe(false)
  })

  it('does not save an empty name', async () => {
    const wrapper = mountItem()
    menu(wrapper).vm.$emit('select', 'rename')
    await wrapper.vm.$nextTick()
    const input = wrapper.get('input:not([type="checkbox"])')
    await input.setValue('   ')
    await input.trigger('keyup', { key: 'Enter' })
    expect(wrapper.emitted('rename')).toBeUndefined()
  })
})
