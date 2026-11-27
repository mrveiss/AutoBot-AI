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

  it('ArrowUp moves focus back, Home and End jump to the first and last name button', async () => {
    const wrapper = mountTable()
    const btn = (name: string) => wrapper.get(`[data-testid="file-row-${name}"]`)
    ;(btn('b.json').element as HTMLElement).focus()
    await btn('b.json').trigger('keydown', { key: 'ArrowUp' })
    expect(document.activeElement).toBe(btn('a.txt').element)
    await btn('a.txt').trigger('keydown', { key: 'End' })
    expect(document.activeElement).toBe(btn('b.json').element)
    await btn('b.json').trigger('keydown', { key: 'Home' })
    expect(document.activeElement).toBe(btn('docs').element)
    await btn('docs').trigger('keydown', { key: 'ArrowUp' })
    expect(document.activeElement).toBe(btn('docs').element)
    wrapper.unmount()
  })

  it('marks the sorted column ascending and every other sortable column none', () => {
    const wrapper = mountTable()
    const heads = wrapper.findAll('thead th').filter((th) => th.attributes('aria-sort'))
    const active = heads.filter((th) => th.attributes('aria-sort') !== 'none')
    expect(heads.length).toBeGreaterThan(1)
    expect(active).toHaveLength(1)
    expect(active[0].text()).toContain('Name')
    expect(active[0].attributes('aria-sort')).toBe('ascending')
    wrapper.unmount()
  })

  it('a name button click is the activation path: keydown alone emits nothing, the click emits view-file', async () => {
    const wrapper = mountTable()
    const button = wrapper.get('[data-testid="file-row-a.txt"]')
    ;(button.element as HTMLElement).focus()
    await button.trigger('keydown', { key: 'Enter' })
    await button.trigger('keydown', { key: ' ' })
    expect(wrapper.emitted('view-file')).toBeUndefined()
    await button.trigger('click')
    expect(wrapper.emitted('view-file')?.[0]).toEqual([files[1]])
    wrapper.unmount()
  })

  it('resolves a row by its path, not its DOM position or name', async () => {
    const twins = [
      { name: 'same.txt', path: '/one/same.txt', is_dir: false },
      { name: 'same.txt', path: '/two/same.txt', is_dir: false },
    ]
    const wrapper = mountTable(twins)
    const body = wrapper.get('tbody').element
    body.insertBefore(body.children[1], body.children[0]) // DOM order now differs from props.files order
    const first = wrapper.findAll('tbody tr')[0]
    expect(first.get('[data-row-primary]').attributes('data-path')).toBe('/two/same.txt')
    await first.get('[data-row-primary]').trigger('click')
    expect(wrapper.emitted('view-file')?.[0]).toEqual([twins[1]]) // index- or name-based lookup yields twins[0]
    wrapper.unmount()
  })

  it('shows the empty message when there are no files', () => {
    const wrapper = mountTable([])
    expect(wrapper.text()).toContain('No files')
    expect(wrapper.find('[data-testid^="file-row-"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
