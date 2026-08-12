// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// Coverage for the `category` prop default in DocumentationSuggestionChip
// (#14047). The prop drives the rendered `category-<value>` icon-wrapper
// class, so the default/override behaviour is asserted through it.

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import DocumentationSuggestionChip from '../DocumentationSuggestionChip.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en: { chat: { docSuggestion: { dismiss: 'Dismiss' } } } },
})

function mountChip(props: Record<string, unknown>) {
  return mount(DocumentationSuggestionChip, {
    props: { label: 'Getting Started', ...props },
    global: { plugins: [i18n] },
  })
}

describe('DocumentationSuggestionChip category default (#14047)', () => {
  it('missing category prop defaults to "general"', () => {
    const wrapper = mountChip({})

    expect(wrapper.find('.chip-icon').classes()).toContain('category-general')
  })

  it('explicit category prop overrides the default', () => {
    const wrapper = mountChip({ category: 'security' })

    expect(wrapper.find('.chip-icon').classes()).toContain('category-security')
    expect(wrapper.find('.chip-icon').classes()).not.toContain('category-general')
  })
})
