// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// Coverage for the `category` prop default in DocumentationResultCard
// (#14047). The prop drives the rendered `category-<value>` badge class.

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import DocumentationResultCard from '../DocumentationResultCard.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en: {} },
})

function mountCard(props: Record<string, unknown>) {
  return mount(DocumentationResultCard, {
    props: { title: 'Getting Started', content: 'Some content', ...props },
    global: { plugins: [i18n] },
  })
}

describe('DocumentationResultCard category default (#14047)', () => {
  it('missing category prop defaults to "general"', () => {
    const wrapper = mountCard({})

    expect(wrapper.find('.category-badge').classes()).toContain('category-general')
  })

  it('explicit category prop overrides the default', () => {
    const wrapper = mountCard({ category: 'security' })

    expect(wrapper.find('.category-badge').classes()).toContain('category-security')
    expect(wrapper.find('.category-badge').classes()).not.toContain('category-general')
  })
})
