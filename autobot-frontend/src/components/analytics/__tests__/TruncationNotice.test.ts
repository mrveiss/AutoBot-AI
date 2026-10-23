// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * TruncationNotice (#12741): the one notice every capped list uses. With the whole list held
 * it is a real button that emits `show-more`; when the server capped the list it says so and
 * has no button; when nothing is hidden it renders nothing.
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import TruncationNotice from '../TruncationNotice.vue'
import en from '@/i18n/locales/en.json'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const mountNotice = (props: Record<string, unknown>) => mount(TruncationNotice, { props: props as never, global: { plugins: [i18n] } })

describe('TruncationNotice', () => {
  it('renders nothing when the list is complete', () => {
    expect(mountNotice({ shown: 5, total: 5 }).find('.truncation-notice').exists()).toBe(false)
  })

  it('is a button that emits show-more, offering at most one step', async () => {
    const w = mountNotice({ shown: 20, total: 25, step: 20 })
    expect(w.get('[data-testid="truncation-count"]').text()).toBe('Showing 20 of 25')
    const button = w.get('[data-testid="truncation-show-more"]')
    expect(button.element.tagName).toBe('BUTTON')
    expect(button.text()).toBe('Show 5 more')
    await button.trigger('click')
    expect(w.emitted('show-more')).toHaveLength(1)
  })

  it('formats large counts with separators', () => {
    expect(mountNotice({ shown: 30, total: 1947 }).get('[data-testid="truncation-count"]').text()).toBe('Showing 30 of 1,947')
  })

  it('server-limited: an honest explanation and no button', () => {
    const w = mountNotice({ shown: 50, total: 1947, serverLimited: true })
    expect(w.find('button').exists()).toBe(false)
    expect(w.get('[data-testid="truncation-server-limited"]').text()).toBe(en.analytics.truncation.serverLimited.replace('{shown}', '50').replace('{total}', '1,947'))
  })
})
