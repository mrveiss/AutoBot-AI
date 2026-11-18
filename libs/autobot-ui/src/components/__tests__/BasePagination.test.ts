// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// BasePagination (#14780): v-model:page, known-total and cursor (hasNext) paging, optional
// First/Last, a named nav landmark, and keyboard operation through real buttons.

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import BasePagination from '../BasePagination.vue'

const labels = { previous: 'Prev', next: 'Next', first: 'First', last: 'Last' }

function render(props: Record<string, unknown> = {}) {
  return mount(BasePagination, { props: { page: 2, totalPages: 5, labels, label: 'Pages', ...props } })
}

const button = (w: ReturnType<typeof render>, text: string) => w.findAll('button').find((b) => b.text() === text)

describe('BasePagination', () => {
  it('is a nav landmark named by label, with the summary slot on the left', () => {
    const w = mount(BasePagination, { props: { page: 1, totalPages: 3, labels, label: 'Audit pages' }, slots: { summary: 'Page 1 of 3' } })
    expect(w.find('nav').attributes('aria-label')).toBe('Audit pages')
    expect(w.find('.aui-pagination__summary').text()).toBe('Page 1 of 3')
  })

  it('emits the previous and next page', async () => {
    const w = render()
    await button(w, 'Prev')!.trigger('click')
    await button(w, 'Next')!.trigger('click')
    expect(w.emitted('update:page')).toEqual([[1], [3]])
  })

  it('disables Previous on the first page and Next on the last', () => {
    expect(button(render({ page: 1 }), 'Prev')!.attributes('disabled')).toBeDefined()
    expect(button(render({ page: 5 }), 'Next')!.attributes('disabled')).toBeDefined()
    expect(button(render({ page: 3 }), 'Next')!.attributes('disabled')).toBeUndefined()
  })

  it('cursor paging: Next follows hasNext when the total is unknown', () => {
    expect(button(render({ totalPages: undefined, hasNext: true }), 'Next')!.attributes('disabled')).toBeUndefined()
    expect(button(render({ totalPages: undefined, hasNext: false }), 'Next')!.attributes('disabled')).toBeDefined()
  })

  it('shows First and Last only when asked and the total is known', async () => {
    expect(button(render(), 'First')).toBeUndefined()
    expect(button(render({ showFirstLast: true, totalPages: undefined, hasNext: true }), 'Last')).toBeUndefined()
    const w = render({ showFirstLast: true, page: 3 })
    await button(w, 'First')!.trigger('click')
    await button(w, 'Last')!.trigger('click')
    expect(w.emitted('update:page')).toEqual([[1], [5]])
  })

  it('a page past the end: Next is disabled, and Previous steps back into range, not further out', async () => {
    const w = render({ page: 9, totalPages: 5, showFirstLast: true })
    expect(button(w, 'Next')!.attributes('disabled')).toBeDefined()
    expect(button(w, 'Last')!.attributes('disabled')).toBeDefined()
    await button(w, 'Prev')!.trigger('click')
    expect(w.emitted('update:page')).toEqual([[5]])
  })

  it.each([0, 1])('totalPages %i on page 1: both directions are disabled and nothing is emitted', async (totalPages) => {
    const w = render({ page: 1, totalPages, showFirstLast: true })
    for (const name of ['First', 'Prev', 'Next', 'Last']) {
      expect(button(w, name)!.attributes('disabled')).toBeDefined()
    }
    await Promise.all(w.findAll('button').map((b) => b.trigger('click')))
    expect(w.emitted('update:page')).toBeUndefined()
  })

  it('disabled turns every control off', () => {
    const w = render({ disabled: true, showFirstLast: true, page: 3 })
    expect(w.findAll('button').every((b) => b.attributes('disabled') !== undefined)).toBe(true)
  })

  it('is operable from the keyboard: each control is a real button in tab order', () => {
    const w = render({ showFirstLast: true, page: 3 })
    const buttons = w.findAll('button')
    expect(buttons.map((b) => b.element.tagName)).toEqual(['BUTTON', 'BUTTON', 'BUTTON', 'BUTTON'])
    expect(buttons.every((b) => b.attributes('tabindex') === undefined)).toBe(true)
  })
})
