// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #21784: the category menu is not part of the heading's accessible name, a category switch shows no
 * rows of the previous category, and the export is off while a load is in flight.
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import CodeSmellsSection from '../CodeSmellsSection.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const EmptyState = { props: ['message'], template: '<div class="empty-state">{{ message }}</div>' }
const SMELL = { severity: 'high', description: 'too long', file_path: 'a.py', line_number: 3, smell_type: 'long_function' }

const mountIt = (props: Record<string, unknown> = {}) =>
  mount(CodeSmellsSection as never, {
    props: { smells: [SMELL], codeHealthScore: null, ...props },
    global: { plugins: [i18n], stubs: { EmptyState } },
  } as never)

const exportButtons = (w: ReturnType<typeof mountIt>) => w.findAll('.export-btn')

describe('CodeSmellsSection loading behaviour (#21784)', () => {
  it('the heading holds no control: the category menu sits beside it', () => {
    const w = mountIt()
    expect(w.find('h3').exists()).toBe(true)
    expect(w.find('h3 select, h3 button, h3 [role="combobox"], h3 [role="listbox"]').exists()).toBe(false)
    expect(w.find('h3').text()).toContain('Code Smells')
  })

  it('the export buttons are enabled when idle', () => {
    const buttons = exportButtons(mountIt())
    expect(buttons).toHaveLength(2)
    expect(buttons.every((b) => b.attributes('disabled') === undefined)).toBe(true)
  })

  it('the export buttons are disabled while a load is in flight', () => {
    const buttons = exportButtons(mountIt({ loading: true }))
    expect(buttons).toHaveLength(2)
    expect(buttons.every((b) => b.attributes('disabled') !== undefined)).toBe(true)
  })

  it('the previous category rows are not shown, nor exportable, while the next category loads', () => {
    const w = mountIt({ loading: true, stale: true })
    expect(w.find('.section-content').exists()).toBe(false)
    expect(exportButtons(w)).toHaveLength(0)
    expect(w.find('.empty-state').exists()).toBe(false)
  })

  it('rows of the selected category stay visible while a refresh of it loads', () => {
    const w = mountIt({ loading: true, stale: false })
    expect(w.find('.section-content').exists()).toBe(true)
  })
})
