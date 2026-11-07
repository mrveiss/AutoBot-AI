// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #20671: the selector's text comes from the locale, its Retry control is the
 * kit BaseButton, and a request settled after unmount writes nothing.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createI18n } from 'vue-i18n'
import { BaseButton } from '@autobot/ui'
import AsrProviderSelector from '@/components/transcriber/AsrProviderSelector.vue'

const listAsrProviders = vi.fn()
const setAsrProvider = vi.fn()
const loggerError = vi.fn()

vi.mock('@/composables/transcriber/useTranscriberApi', () => ({
  useTranscriberApi: () => ({ listAsrProviders, setAsrProvider }),
}))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ error: loggerError, warn: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

// Distinct strings, so a hardcoded English literal cannot pass for a translated one.
const asr = {
  heading: 'h-x', help: 'help-x', loading: 'loading-x', empty: 'empty-x',
  activeProvider: 'active-x', selectPlaceholder: 'placeholder-x',
  optionNotConfigured: 'opt-{name}-x', saving: 'saving-x',
  notConfigured: 'badge-x', notConfiguredHelp: 'badgehelp-x',
}
const i18n = createI18n({
  legacy: false, locale: 'xx',
  messages: { xx: { transcriber: { asr }, common: { retry: 'retry-x' } } },
  missingWarn: false, fallbackWarn: false,
})
const PROVIDERS = [
  { id: 'a', name: 'Alpha', configured: true, languages: ['en'] },
  { id: 'g', name: 'Gamma', configured: false, languages: ['en'] },
]
const mountIt = () => mount(AsrProviderSelector, { global: { plugins: [i18n] } })

describe('AsrProviderSelector i18n and kit control', () => {
  beforeEach(() => {
    listAsrProviders.mockResolvedValue({ selected: 'a', providers: PROVIDERS })
    setAsrProvider.mockResolvedValue(undefined)
  })

  it('renders every string from the locale', async () => {
    listAsrProviders.mockImplementationOnce(() => new Promise(() => {}))
    const loading = mountIt()
    await nextTick()
    expect(loading.text()).toContain(asr.loading)
    const w = mountIt()
    await flushPromises()
    const t = w.text()
    for (const k of ['heading', 'help', 'activeProvider', 'notConfigured', 'notConfiguredHelp'] as const) {
      expect(t).toContain(asr[k])
    }
    expect(w.find('option[disabled][value=""]').text()).toBe(asr.selectPlaceholder)
    expect(w.find('option[value="g"]').text()).toBe('opt-Gamma-x')
  })

  it('renders the empty state from the locale', async () => {
    listAsrProviders.mockResolvedValue({ selected: null, providers: [] })
    const w = mountIt()
    await flushPromises()
    expect(w.text()).toContain(asr.empty)
  })

  it('Retry is the kit BaseButton with a translated label', async () => {
    listAsrProviders.mockRejectedValueOnce(new Error('down'))
    const w = mountIt()
    await flushPromises()
    const btn = w.findComponent(BaseButton)
    expect(btn.exists()).toBe(true)
    expect(btn.text()).toBe('retry-x')
    listAsrProviders.mockResolvedValue({ selected: 'a', providers: PROVIDERS })
    await btn.trigger('click')
    await flushPromises()
    expect(listAsrProviders).toHaveBeenCalledTimes(2)
  })

  it('shows the saving label from the locale', async () => {
    setAsrProvider.mockImplementationOnce(() => new Promise(() => {}))
    const w = mountIt()
    await flushPromises()
    await w.find('select').setValue('g')
    expect(w.text()).toContain(asr.saving)
  })

  it('a save failing after unmount leaves no late write and no error log', async () => {
    let reject!: (e: Error) => void
    setAsrProvider.mockImplementationOnce(() => new Promise((_, rej) => { reject = rej }))
    const w = mountIt()
    await flushPromises()
    await w.find('select').setValue('g')
    const vm = w.vm as unknown as { selected: string | null; saving: boolean; saveError: string }
    w.unmount()
    reject(new Error('late'))
    await flushPromises()
    expect(vm.selected).toBe('g') // not reverted
    expect(vm.saving).toBe(true) // not cleared
    expect(vm.saveError).toBe('')
    expect(loggerError).not.toHaveBeenCalled()
  })

  it('a load settling after unmount writes nothing', async () => {
    let resolve!: (v: unknown) => void
    listAsrProviders.mockImplementationOnce(() => new Promise((r) => { resolve = r }))
    const w = mountIt()
    const vm = w.vm as unknown as { providers: unknown[] }
    w.unmount()
    resolve({ selected: 'a', providers: PROVIDERS })
    await flushPromises()
    expect(vm.providers).toHaveLength(0)
  })
})
