// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #22349: the create / edit file dialog on the kit modal.
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import ChatFileEditorDialog from '../ChatFileEditorDialog.vue'

const find = (sel: string) => document.body.querySelector(sel) as HTMLElement | null
const mountDialog = (props: Record<string, unknown>) =>
  mount(ChatFileEditorDialog, {
    props: { open: true, mode: 'create', ...props },
    attachTo: document.body,
    global: { mocks: { $t: (k: string) => k } },
  })

function type(el: HTMLElement | null, value: string): void {
  const field = el as HTMLInputElement | HTMLTextAreaElement
  field.value = value
  field.dispatchEvent(new Event('input'))
}

describe('ChatFileEditorDialog (#22349)', () => {
  beforeEach(() => { document.body.innerHTML = '' })

  it('create is disabled on an empty name and enabled once a name is typed', async () => {
    const wrapper = mountDialog({})
    expect(find('[data-testid="editor-submit"]')?.hasAttribute('disabled')).toBe(true)
    type(find('[data-testid="editor-name"] input'), 'a.txt')
    await wrapper.vm.$nextTick()
    expect(find('[data-testid="editor-submit"]')?.hasAttribute('disabled')).toBe(false)
    wrapper.unmount()
  })

  it('create emits the trimmed name and the content', async () => {
    const wrapper = mountDialog({})
    type(find('[data-testid="editor-name"] input'), ' a.txt ')
    type(find('[data-testid="editor-content"]'), 'hello')
    await wrapper.vm.$nextTick()
    find('[data-testid="editor-submit"]')!.click()
    expect(wrapper.emitted('submit')?.[0]).toEqual([{ name: 'a.txt', content: 'hello' }])
    wrapper.unmount()
  })

  it('edit mode titles the dialog with the file name, opens with its content and has no name field', () => {
    const wrapper = mountDialog({ mode: 'edit', filename: 'notes.txt', content: 'draft' })
    expect(document.body.querySelector('h3')?.textContent).toBe('notes.txt')
    expect((find('[data-testid="editor-content"]') as HTMLTextAreaElement).value).toBe('draft')
    expect(find('[data-testid="editor-name"]')).toBeNull()
    expect(find('[data-testid="editor-submit"]')?.hasAttribute('disabled')).toBe(false)
    wrapper.unmount()
  })

  it('Cancel closes without emitting a submit', () => {
    const wrapper = mountDialog({})
    find('[data-testid="editor-cancel"]')!.click()
    expect(wrapper.emitted('update:open')?.[0]).toEqual([false])
    expect(wrapper.emitted('submit')).toBeUndefined()
    wrapper.unmount()
  })

  it('Escape closes without emitting a submit', () => {
    const wrapper = mountDialog({})
    find('[role="dialog"]')!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(wrapper.emitted('update:open')?.[0]).toEqual([false])
    expect(wrapper.emitted('submit')).toBeUndefined()
    wrapper.unmount()
  })

  it('renders nothing while closed', () => {
    const wrapper = mountDialog({ open: false })
    expect(find('[role="dialog"]')).toBeNull()
    wrapper.unmount()
  })
})
