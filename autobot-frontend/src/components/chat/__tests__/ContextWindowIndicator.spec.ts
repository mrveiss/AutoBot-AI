// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// ContextWindowIndicator (#18243): the usage bar is the kit's BaseProgress, named by the
// context-window label, and its variant follows the usage band.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import ContextWindowIndicator from '../ContextWindowIndicator.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const base = { tokensUsed: 12_300, contextWindow: 128_000, usagePercent: 10, isWarning: false, isCritical: false, hasData: true }
const render = (props: Record<string, unknown> = {}) =>
  mount(ContextWindowIndicator, { props: { ...base, ...props }, global: { plugins: [i18n] } })

describe('ContextWindowIndicator', () => {
  it('shows used / max and a named progressbar at the usage percent', () => {
    const w = render()
    expect(w.text()).toContain('12.3k / 128.0k')
    const bar = w.get('[role="progressbar"]')
    expect(bar.attributes('aria-label')).toBe('12.3k of 128.0k tokens used')
    expect(bar.attributes('aria-valuenow')).toBe('10')
  })

  it.each([
    [{}, 'success'],
    [{ isWarning: true }, 'warning'],
    [{ isWarning: true, isCritical: true }, 'error'],
    [{ isSummarizing: true, isCritical: true }, 'info'],
  ])('maps %j onto the %s variant', (props, variant) => {
    expect(render(props).get('[role="progressbar"]').classes()).toContain(`aui-progress--${variant}`)
  })

  it('says Summarizing instead of the count while summarizing', () => {
    expect(render({ isSummarizing: true }).text()).toContain('Summarizing...')
  })

  it('keeps the header visibility classes on a plain root, with the width on a wrapper', () => {
    const w = mount(ContextWindowIndicator, { props: base, attrs: { class: 'hidden sm:flex' }, global: { plugins: [i18n] } })
    expect(w.element.tagName).toBe('DIV')
    expect(w.classes()).toEqual(expect.arrayContaining(['hidden', 'sm:flex']))
    expect(w.get('[role="progressbar"]').element.parentElement?.classList.contains('w-12')).toBe(true)
  })

  it('renders nothing without data', () => {
    expect(render({ hasData: false }).find('[role="progressbar"]').exists()).toBe(false)
  })

  it('is focusable so the tooltip opens from the keyboard', () => {
    expect(render().get('.ctx-indicator').attributes('tabindex')).toBe('0')
  })
})
