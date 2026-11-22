// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * #12741: "Showing 30 of 1947 used endpoints" was a label with nothing to press. The route
 * returns every used endpoint, so the panel holds the full list and the notice under it is a
 * real "show more" control that grows the list and keeps the count accurate.
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import CodebaseApiEndpointsPanel from '../CodebaseApiEndpointsPanel.vue'
import en from '@/i18n/locales/en.json'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

const used = (n: number) =>
  Array.from({ length: n }, (_, i) => ({
    endpoint: { path: `/api/e${i}`, method: 'GET' },
    call_count: i,
  }))

function mountPanel(count: number) {
  return mount(CodebaseApiEndpointsPanel, {
    props: {
      analysis: {
        coverage_percentage: 50,
        backend_endpoints: count,
        frontend_calls: count,
        used_endpoints: count,
        orphaned_endpoints: 0,
        missing_endpoints: 0,
        orphaned: [],
        missing: [],
        used: used(count),
      },
      loading: false,
      error: null,
    },
    global: { plugins: [i18n], stubs: { Icon: true, EmptyState: true } },
  })
}

describe('CodebaseApiEndpointsPanel used endpoints: show more (#12741)', () => {
  it('reveals the next rows on press and updates the count text', async () => {
    const w = mountPanel(75)
    await w.find('.accordion-header.success').trigger('click')
    const rows = () => w.findAll('.list-item.item-success')

    expect(rows()).toHaveLength(30)
    expect(w.get('[data-testid="truncation-count"]').text()).toBe('Showing 30 of 75')

    const button = w.get('[data-testid="truncation-show-more"]')
    expect(button.element.tagName).toBe('BUTTON')
    expect(button.text()).toBe('Show 30 more')
    await button.trigger('click')
    expect(rows()).toHaveLength(60)
    expect(w.get('[data-testid="truncation-count"]').text()).toBe('Showing 60 of 75')

    await w.get('[data-testid="truncation-show-more"]').trigger('click')
    expect(rows()).toHaveLength(75)
    expect(w.find('[data-testid="truncation-show-more"]').exists()).toBe(false)
  })

  it('shows no notice when the list fits', async () => {
    const w = mountPanel(10)
    await w.find('.accordion-header.success').trigger('click')
    expect(w.findAll('.list-item.item-success')).toHaveLength(10)
    expect(w.find('.truncation-notice').exists()).toBe(false)
  })
})
