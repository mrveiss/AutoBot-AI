// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// AuditLogTable pages through the kit BasePagination (#14780) and keeps its cursor contract:
// Next follows hasMore, and the parent still receives prev-page / next-page.

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import AuditLogTable from '../AuditLogTable.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', missingWarn: false, messages: { en } })
const L = en.audit.logTable

function render(props: Record<string, unknown>) {
  return mount(AuditLogTable, { props: { entries: [], ...props }, global: { plugins: [i18n], stubs: { BaseModal: true, Icon: true } } })
}
const button = (w: ReturnType<typeof render>, text: string) => w.findAll('nav button').find((b) => b.text() === text)!

describe('AuditLogTable pagination', () => {
  it('is a named nav with the page summary', () => {
    const w = render({ currentPage: 3, hasMore: true })
    expect(w.find('nav').attributes('aria-label')).toBe(L.paginationAria)
    expect(w.find('nav').text()).toContain(L.pageOf.replace('{page}', '3'))
  })

  // Each direction on its own: clicking both and counting one emit of each would also pass with
  // the prev/next mapping inverted (#19078 review).
  it('Next emits next-page and never prev-page', async () => {
    const w = render({ currentPage: 2, hasMore: true })
    await button(w, L.next).trigger('click')
    expect(w.emitted('next-page')).toHaveLength(1)
    expect(w.emitted('prev-page')).toBeUndefined()
  })

  it('Previous emits prev-page and never next-page', async () => {
    const w = render({ currentPage: 2, hasMore: true })
    await button(w, L.previous).trigger('click')
    expect(w.emitted('prev-page')).toHaveLength(1)
    expect(w.emitted('next-page')).toBeUndefined()
  })

  it('disables Next when there is no further page, and Previous on page 1', () => {
    const w = render({ currentPage: 1, hasMore: false })
    expect(button(w, L.next).attributes('disabled')).toBeDefined()
    expect(button(w, L.previous).attributes('disabled')).toBeDefined()
  })
})
