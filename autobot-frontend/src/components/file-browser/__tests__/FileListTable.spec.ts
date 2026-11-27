// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #22349: the Files tab table on the kit BaseTable -- columns, row activation, row actions, sort and the empty state.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import FileListTable from '../FileListTable.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const files = [
  { name: 'docs', path: '/docs', is_dir: true },
  { name: 'a.txt', path: '/a.txt', is_dir: false, size: 2048, last_modified: '2026-01-02T03:04:05Z' },
  { name: 'b.json', path: '/b.json', is_dir: false, size: 10 },
]
const mountTable = (list = files) =>
  mount(FileListTable, {
    props: { files: list, sortField: 'name', sortOrder: 'asc' as const },
    attachTo: document.body,
    global: { plugins: [i18n], stubs: { Icon: true } },
  })

describe('FileListTable (#22349)', () => {
  it('shows the Name, Type, Size and Modified columns and one row per file', () => {
    const wrapper = mountTable()
    const heads = wrapper.findAll('thead th').map((th) => th.text())
    for (const label of ['Name', 'Type', 'Size', 'Modified']) expect(heads.join(' ')).toContain(label)
    expect(wrapper.findAll('tbody tr')).toHaveLength(3)
    expect(wrapper.text()).toContain('JSON')
    wrapper.unmount()
  })

  it('a folder row emits navigate with its path, a file row emits view-file', async () => {
    const wrapper = mountTable()
    await wrapper.get('[data-testid="file-row-docs"]').trigger('click')
    expect(wrapper.emitted('navigate')?.[0]).toEqual(['/docs'])
    await wrapper.get('[data-testid="file-row-a.txt"]').trigger('click')
    expect(wrapper.emitted('view-file')?.[0]).toEqual([files[1]])
    wrapper.unmount()
  })

  it('the row actions emit their own event and do not also activate the row', async () => {
    const wrapper = mountTable()
    const rows = wrapper.findAll('tbody tr')
    await rows[1].get('[data-testid="row-rename"]').trigger('click')
    await rows[1].get('[data-testid="row-delete"]').trigger('click')
    expect(wrapper.emitted('rename-file')?.[0]).toEqual([files[1]])
    expect(wrapper.emitted('delete-file')?.[0]).toEqual([files[1]])
    expect(wrapper.emitted('view-file')).toBeUndefined()
    await rows[0].get('[data-testid="row-open"]').trigger('click')
    expect(wrapper.emitted('navigate')).toHaveLength(1)
    wrapper.unmount()
  })

  it('a sortable header emits sort with its column key', async () => {
    const wrapper = mountTable()
    const sizeSort = wrapper.findAll('[data-slot="table-sort"]').find((b) => b.text().includes('Size'))!
    await sizeSort.trigger('click')
    expect(wrapper.emitted('sort')?.[0]).toEqual(['size'])
    wrapper.unmount()
  })

  it('ArrowDown moves focus to the next name button', async () => {
    const wrapper = mountTable()
    const first = wrapper.get('[data-testid="file-row-docs"]')
    ;(first.element as HTMLElement).focus()
    await first.trigger('keydown', { key: 'ArrowDown' })
    expect(document.activeElement).toBe(wrapper.get('[data-testid="file-row-a.txt"]').element)
    wrapper.unmount()
  })

  it('shows the empty message when there are no files', () => {
    const wrapper = mountTable([])
    expect(wrapper.text()).toContain('No files')
    expect(wrapper.find('[data-testid^="file-row-"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
