// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Stop is unavailable while this source is only queued: cancel acts on whichever job is running,
 * which would be another source's (#20513).
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import AnalyticsHeaderControls from '../AnalyticsHeaderControls.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const label = en.analytics.codebase.actions.stop

function stopButton(stopDisabled: boolean) {
  const wrapper = mount(AnalyticsHeaderControls, {
    props: {
      analyzing: true,
      stopDisabled,
      rootPath: '/repo',
      selectedSource: null,
      scanRunnerRunning: false,
      loadingApiEndpoints: false,
      analyzingCodeSmells: false,
      exportingReport: false,
      clearingCache: false,
    },
    global: { plugins: [i18n], stubs: { 'router-link': true } },
  })
  return wrapper.findAll('button').find((b) => b.text().includes(label))
}

describe('AnalyticsHeaderControls stop (#20513)', () => {
  it('is disabled while only queued', () => {
    expect(stopButton(true)?.attributes('disabled')).toBeDefined()
  })

  it('is enabled once there is a job to cancel', () => {
    const button = stopButton(false)
    expect(button).toBeDefined()
    expect(button?.attributes('disabled')).toBeUndefined()
  })
})
