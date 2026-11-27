// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #22349: the Chat files toolbar -- count line, search, sort group and bulk-selection bar.
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-i18n')>()),
  useI18n: () => ({ t: (k: string) => k, locale: { value: 'en' } }),
}))

import ChatFilePanelToolbar from '../ChatFilePanelToolbar.vue'

const base = {
  totalFiles: 2, totalSizeLabel: '4 KB', search: '', sortField: 'name', sortDirection: 'asc',
  selectedCount: 0, allSelected: false,
} as const

const mountToolbar = (props: Record<string, unknown> = {}) =>
  mount(ChatFilePanelToolbar, {
    props: { ...base, ...props },
    global: { mocks: { $t: (k: string, ...rest: unknown[]) => (rest.length ? `${k}|${JSON.stringify(rest)}` : k) }, stubs: { Icon: true } },
  })

describe('ChatFilePanelToolbar (#22349)', () => {
  it('shows the count through the one pluralised key, passing the count as the plural choice', () => {
    const text = mountToolbar({ totalFiles: 1 }).get('[data-testid="file-count"]').text()
    expect(text).toContain('chat.filePanel.fileCount|[{"count":1},1]')
    expect(mountToolbar({ totalFiles: 2 }).get('[data-testid="file-count"]').text()).toContain('[{"count":2},2]')
  })

  it('hides the count line when the conversation has no files', () => {
    expect(mountToolbar({ totalFiles: 0 }).find('[data-testid="file-count"]').exists()).toBe(false)
  })

  it('emits the typed search text', async () => {
    const wrapper = mountToolbar()
    await wrapper.get('input[type="search"]').setValue('notes')
    expect(wrapper.emitted('update:search')?.[0]).toEqual(['notes'])
  })

  it('marks only the active sort field as pressed and emits the clicked field', async () => {
    const wrapper = mountToolbar({ sortField: 'size' })
    const buttons = wrapper.findAll('[data-testid="sort-button"]')
    expect(buttons.map((b) => b.attributes('aria-pressed'))).toEqual(['false', 'false', 'true', 'false'])
    await buttons[1].trigger('click')
    expect(wrapper.emitted('sort')?.[0]).toEqual(['date'])
  })

  it('exposes the sort buttons as one labelled group', () => {
    const group = mountToolbar().get('[role="group"]')
    expect(group.attributes('aria-label')).toBe('chat.filePanel.sortGroupLabel')
  })

  it('shows the selection bar only with a selection, and emits bulk delete and select all', async () => {
    expect(mountToolbar().find('[data-testid="selection-bar"]').exists()).toBe(false)
    const wrapper = mountToolbar({ selectedCount: 2 })
    expect(wrapper.find('[data-testid="selection-bar"]').exists()).toBe(true)
    await wrapper.get('[data-testid="bulk-delete"]').trigger('click')
    await wrapper.get('[data-testid="select-all"]').trigger('click')
    expect(wrapper.emitted('bulk-delete')).toHaveLength(1)
    expect(wrapper.emitted('select-all')).toHaveLength(1)
  })

  it('offers Deselect once everything is selected', () => {
    expect(mountToolbar({ selectedCount: 2, allSelected: true }).get('[data-testid="select-all"]').text()).toBe('chat.filePanel.deselect')
  })
})
