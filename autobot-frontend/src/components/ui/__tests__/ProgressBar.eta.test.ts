// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/** ProgressBar's time remaining comes from the kit's duration formatter (#19905). */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import ProgressBar from '../ProgressBar.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en }, missingWarn: false, fallbackWarn: false })

function eta(seconds: number): string {
  const w = mount(ProgressBar, { props: { progress: 40, showDetails: true, eta: seconds }, global: { plugins: [i18n] } })
  return w.get('.progress-eta').text()
}

describe('ProgressBar time remaining (#19905)', () => {
  it('reads seconds, minutes and seconds, then hours and minutes', () => {
    expect(eta(45)).toBe('45s remaining')
    expect(eta(3 * 3600 + 5 * 60)).toBe('3h 5m remaining')
  })

  it('does not round a minute and a half up to two minutes', () => {
    // The local copy rounded the minutes, so 90 seconds read "2m 30s".
    expect(eta(90)).toBe('1m 30s remaining')
  })
})
