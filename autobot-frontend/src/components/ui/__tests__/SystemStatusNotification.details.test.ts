// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #16253 — the status details panel words the backend state with a translated label in a
 * theme-token colour; it never prints the raw state or a palette step.
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import SystemStatusNotification from '../SystemStatusNotification.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en }, missingWarn: false, fallbackWarn: false })

function mountWith(status: string) {
  return mount(SystemStatusNotification, {
    props: {
      visible: true,
      severity: 'error',
      title: 'Backend unreachable',
      message: 'm',
      showDetails: true,
      autoHide: 0,
      statusDetails: { status, lastCheck: 0, consecutiveFailures: 3, timestamp: 0 },
    },
    global: { plugins: [i18n], stubs: { Teleport: true } },
  })
}

describe('SystemStatusNotification details (#16253)', () => {
  it.each([
    ['healthy', en.ui.systemStatus.states.healthy, 'text-autobot-pill-ok-fg'],
    ['degraded', en.ui.systemStatus.states.degraded, 'text-autobot-pill-warn-fg'],
    ['critical', en.ui.systemStatus.states.critical, 'text-autobot-pill-bad-fg'],
  ])('%s is shown as %j in %s', (state, label, tone) => {
    const html = mountWith(state).html()
    expect(html).toContain(label)
    expect(html).toContain(tone)
  })

  it('uses no palette steps for its colours', () => {
    expect(mountWith('critical').html()).not.toMatch(/\b(text|bg|border)-(red|green|yellow|blue)-\d{2,3}\b/)
  })
})
