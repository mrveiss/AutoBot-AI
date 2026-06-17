// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import AsrProviderSelector from '@/components/transcriber/AsrProviderSelector.vue'

// --- API mock ---------------------------------------------------------------
const listAsrProviders = vi.fn()
const setAsrProvider = vi.fn()

// mockReset:true wipes factories — re-apply implementations in beforeEach.
vi.mock('@/composables/transcriber/useTranscriberApi', () => ({
  useTranscriberApi: () => ({
    listAsrProviders,
    setAsrProvider,
  }),
}))

const PROVIDERS = [
  { id: 'deepgram', name: 'Deepgram', configured: true, languages: ['en'] },
  { id: 'assemblyai', name: 'AssemblyAI', configured: true, languages: ['en'] },
  { id: 'google', name: 'Google Cloud STT v2', configured: false, languages: ['en'] },
]

function mountSelector() {
  return mount(AsrProviderSelector)
}

describe('AsrProviderSelector.vue', () => {
  beforeEach(() => {
    // Re-apply mock implementations (mockReset wipes them).
    listAsrProviders.mockResolvedValue({ selected: 'deepgram', providers: PROVIDERS })
    setAsrProvider.mockResolvedValue(undefined)
  })

  it('renders the list of providers after load', async () => {
    const wrapper = mountSelector()
    await flushPromises()

    expect(listAsrProviders).toHaveBeenCalledTimes(1)
    const options = wrapper.findAll('#asr-provider-select option')
    // Includes the disabled placeholder option + 3 providers.
    expect(options).toHaveLength(4)
    expect(wrapper.text()).toContain('Deepgram')
    expect(wrapper.text()).toContain('AssemblyAI')
    expect(wrapper.text()).toContain('Google Cloud STT v2')
  })

  it('disables unconfigured providers and shows a "not configured" badge', async () => {
    const wrapper = mountSelector()
    await flushPromises()

    const googleOption = wrapper
      .findAll('#asr-provider-select option')
      .find((o) => o.attributes('value') === 'google')
    expect(googleOption).toBeDefined()
    expect(googleOption!.attributes('disabled')).toBeDefined()

    expect(wrapper.text()).toContain('not configured')
  })

  it('reflects the server-selected provider', async () => {
    const wrapper = mountSelector()
    await flushPromises()

    const select = wrapper.find('#asr-provider-select').element as HTMLSelectElement
    expect(select.value).toBe('deepgram')
  })

  it('calls setAsrProvider when a configured provider is chosen', async () => {
    const wrapper = mountSelector()
    await flushPromises()

    const select = wrapper.find('#asr-provider-select')
    await select.setValue('assemblyai')
    await flushPromises()

    expect(setAsrProvider).toHaveBeenCalledWith('assemblyai')
    expect((wrapper.find('#asr-provider-select').element as HTMLSelectElement).value).toBe('assemblyai')
  })

  it('reverts the selection when setAsrProvider fails', async () => {
    setAsrProvider.mockRejectedValueOnce(new Error('save failed'))
    const wrapper = mountSelector()
    await flushPromises()

    const select = wrapper.find('#asr-provider-select')
    await select.setValue('assemblyai')
    await flushPromises()

    expect(setAsrProvider).toHaveBeenCalledWith('assemblyai')
    // Optimistic update reverted to the previously selected provider.
    expect((wrapper.find('#asr-provider-select').element as HTMLSelectElement).value).toBe('deepgram')
    expect(wrapper.text()).toContain('save failed')
  })

  it('shows an empty state when no providers are returned', async () => {
    listAsrProviders.mockResolvedValue({ selected: null, providers: [] })
    const wrapper = mountSelector()
    await flushPromises()

    expect(wrapper.find('#asr-provider-select').exists()).toBe(false)
    expect(wrapper.text()).toContain('No speech-to-text providers are available')
  })

  it('shows an error state with a retry control when load fails', async () => {
    listAsrProviders.mockRejectedValueOnce(new Error('network down'))
    const wrapper = mountSelector()
    await flushPromises()

    expect(wrapper.text()).toContain('network down')
    expect(wrapper.find('[role="alert"] .btn').exists()).toBe(true)
  })
})
