// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Tests for ConnectorOAuthButton — the "Connect <provider>" OAuth launcher
 * (ADR-007 / #9019). Verifies the popup flow and that a backend-callback
 * postMessage surfaces as a `connected` event with the secret reference.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

import ConnectorOAuthButton from '../ConnectorOAuthButton.vue'
import { knowledgeRepository } from '@/models/repositories/KnowledgeRepository'

vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/api'
}))

vi.mock('@/models/repositories/KnowledgeRepository', () => ({
  knowledgeRepository: { startConnectorOAuth: vi.fn() }
}))

const startSpy = knowledgeRepository.startConnectorOAuth as unknown as ReturnType<typeof vi.fn>

describe('ConnectorOAuthButton', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Default: popup opens successfully.
    window.open = vi.fn(() => ({ close: vi.fn() })) as unknown as typeof window.open
  })

  function mountButton() {
    return mount(ConnectorOAuthButton, {
      props: { provider: 'google', label: 'Google Drive', scopes: ['drive.readonly'] }
    })
  }

  it('starts the flow with the absolute callback URL and opens a popup', async () => {
    startSpy.mockResolvedValue({ authorize_url: 'https://provider/auth', state: 's', connector_id: 'c' })
    const wrapper = mountButton()

    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(startSpy).toHaveBeenCalledWith(
      'google',
      `${window.location.origin}/api/knowledge_base/connectors/oauth/callback`,
      ['drive.readonly']
    )
    expect(window.open).toHaveBeenCalledWith(
      'https://provider/auth',
      'connector-oauth',
      expect.any(String)
    )
  })

  it('emits "connected" when the callback posts a success message', async () => {
    startSpy.mockResolvedValue({ authorize_url: 'https://provider/auth', state: 's', connector_id: 'c' })
    const wrapper = mountButton()
    await wrapper.find('button').trigger('click')
    await flushPromises()

    window.dispatchEvent(
      new MessageEvent('message', {
        origin: window.location.origin,
        data: { type: 'connector-oauth', ok: true, secret_id: 'sec-1', connector_id: 'c', provider: 'google' }
      })
    )
    await flushPromises()

    expect(wrapper.emitted('connected')?.[0]?.[0]).toEqual({
      secretId: 'sec-1',
      connectorId: 'c',
      provider: 'google'
    })
  })

  it('emits "error" when the callback posts a failure message', async () => {
    startSpy.mockResolvedValue({ authorize_url: 'https://provider/auth', state: 's', connector_id: 'c' })
    const wrapper = mountButton()
    await wrapper.find('button').trigger('click')
    await flushPromises()

    window.dispatchEvent(
      new MessageEvent('message', {
        origin: window.location.origin,
        data: { type: 'connector-oauth', ok: false, error: 'access_denied' }
      })
    )
    await flushPromises()

    expect(wrapper.emitted('error')?.[0]?.[0]).toBe('access_denied')
  })

  it('ignores messages from a foreign origin', async () => {
    startSpy.mockResolvedValue({ authorize_url: 'https://provider/auth', state: 's', connector_id: 'c' })
    const wrapper = mountButton()
    await wrapper.find('button').trigger('click')
    await flushPromises()

    window.dispatchEvent(
      new MessageEvent('message', {
        origin: 'https://evil.example.com',
        data: { type: 'connector-oauth', ok: true, secret_id: 'sec-evil' }
      })
    )
    await flushPromises()

    expect(wrapper.emitted('connected')).toBeUndefined()
  })

  it('emits "error" when starting the flow fails', async () => {
    startSpy.mockRejectedValue(new Error('boom'))
    const wrapper = mountButton()

    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(wrapper.emitted('error')?.[0]?.[0]).toBe('boom')
  })
})
