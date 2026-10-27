// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// PollingPausedAlert (#19482): shown only while the poller is paused on errors; Retry emits.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import PollingPausedAlert from '../PollingPausedAlert.vue'

function mountWith(paused: boolean) {
  const pausedOnErrors = ref(paused)
  const w = mount(PollingPausedAlert, {
    props: { poller: { pausedOnErrors }, message: 'Updates paused', retryLabel: 'Retry' },
  })
  return { w, pausedOnErrors }
}

describe('PollingPausedAlert', () => {
  it('renders nothing while the poller is running or was stopped on purpose', () => {
    expect(mountWith(false).w.find('[data-polling-paused]').exists()).toBe(false)
  })

  it('shows the translated message and a Retry button that emits retry', async () => {
    const { w } = mountWith(true)
    expect(w.find('[data-polling-paused]').text()).toContain('Updates paused')
    await w.find('button').trigger('click')
    expect(w.emitted('retry')).toHaveLength(1)
  })

  it('follows the poller: it hides once polling restarts', async () => {
    const { w, pausedOnErrors } = mountWith(true)
    pausedOnErrors.value = false
    await w.vm.$nextTick()
    expect(w.find('[data-polling-paused]').exists()).toBe(false)
  })
})
