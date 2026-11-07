// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #21045: Company OS router notices reach the user as toasts.
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { defineComponent, h, ref, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

type Cb = (ev: { event_type: string; payload: Record<string, unknown> }) => void

const subscribe = vi.fn()
const notifyInfo = vi.fn()
const notifyWarning = vi.fn()
const notifyError = vi.fn()

vi.mock('@/composables/useLiveEvents', () => ({ useLiveEvents: () => ({ subscribe }) }))
vi.mock('@/composables/useNotificationBus', () => ({
  useNotificationBus: () => ({ notifyInfo, notifyWarning, notifyError }),
}))

import { useLlcCompanyNotices } from '@/composables/useLlcCompanyNotices'

const companyId = ref<string>('c1')
const unsubs: Array<ReturnType<typeof vi.fn>> = []

function mountHost() {
  const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
  const Host = defineComponent({
    setup() {
      useLlcCompanyNotices(companyId)
      return () => h('div')
    },
  })
  return mount(Host, { global: { plugins: [i18n] } })
}

const callback = (n = 0): Cb => subscribe.mock.calls[n][1] as Cb

describe('useLlcCompanyNotices (#21045)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    unsubs.length = 0
    companyId.value = 'c1'
    subscribe.mockImplementation(() => {
      const u = vi.fn()
      unsubs.push(u)
      return u
    })
  })

  it('warns with the dedicated string for an unfiled recovery', () => {
    mountHost()
    expect(subscribe).toHaveBeenCalledWith('company:c1', expect.any(Function))
    callback()({ event_type: 'heartbeat_missed', payload: { agent_id: 'a7', reason: 'recovery_unfiled' } })
    expect(notifyWarning).toHaveBeenCalledWith(
      'Agent a7 timed out and no recovery item could be filed',
    )
  })

  it('uses the generic key for an unknown type', () => {
    mountHost()
    callback()({ event_type: 'mystery_thing', payload: {} })
    expect(notifyInfo).toHaveBeenCalledWith('Company update: mystery_thing')
  })

  it('ignores heartbeat_ok and activity events', () => {
    mountHost()
    callback()({ event_type: 'heartbeat_ok', payload: {} })
    callback()({ event_type: 'llc:activity_created', payload: {} })
    expect(notifyInfo).not.toHaveBeenCalled()
    expect(notifyWarning).not.toHaveBeenCalled()
    expect(notifyError).not.toHaveBeenCalled()
  })

  it('maps budget_exhausted to a sticky error', () => {
    mountHost()
    callback()({ event_type: 'budget_exhausted', payload: {} })
    expect(notifyError).toHaveBeenCalledTimes(1)
  })

  it('re-subscribes on company change and unsubscribes on unmount', async () => {
    const wrapper = mountHost()
    companyId.value = 'c2'
    await nextTick()
    expect(unsubs[0]).toHaveBeenCalledTimes(1)
    expect(subscribe).toHaveBeenLastCalledWith('company:c2', expect.any(Function))
    wrapper.unmount()
    expect(unsubs[1]).toHaveBeenCalledTimes(1)
  })
})
