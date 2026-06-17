// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Tests for the Google Drive surface in ConnectorConfigModal (Issue #9003).
 *
 * Proves end-to-end UI wiring: the gdrive type card renders, selecting it shows
 * the gdrive config form with the OAuth "Connect" button, and saving calls
 * createConnector with the gdrive config plus the OAuth secret_id by reference.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

import ConnectorConfigModal from '../ConnectorConfigModal.vue'
import { knowledgeRepository } from '@/models/repositories/KnowledgeRepository'

vi.mock('@/models/repositories/KnowledgeRepository', () => ({
  knowledgeRepository: {
    createConnector: vi.fn(),
    updateConnector: vi.fn(),
    testConnector: vi.fn()
  }
}))

const createSpy = knowledgeRepository.createConnector as unknown as ReturnType<typeof vi.fn>

// Stub the OAuth button so we can drive its `connected` event directly.
const OAuthButtonStub = {
  name: 'ConnectorOAuthButton',
  props: ['provider', 'label', 'scopes', 'disabled'],
  emits: ['connected', 'error'],
  template: '<button class="oauth-stub" @click="$emit(\'connected\', { secretId: \'sec-1\' })">Connect</button>'
}

function mountModal() {
  return mount(ConnectorConfigModal, {
    props: { modelValue: true, editConnector: null },
    global: {
      mocks: { $t: (k: string) => k },
      stubs: {
        ConnectorOAuthButton: OAuthButtonStub,
        BaseModal: { template: '<div><slot /><slot name="actions" /></div>' },
        BaseButton: { template: '<button><slot /></button>' }
      },
      plugins: [
        {
          install(app: any) {
            app.config.globalProperties.$t = (k: string) => k
          }
        }
      ]
    }
  })
}

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k })
}))

describe('ConnectorConfigModal — Google Drive (#9003)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    createSpy.mockResolvedValue({ connector_id: 'new-gdrive', connector_type: 'gdrive' })
  })

  it('renders a Google Drive type card on step 1', () => {
    const wrapper = mountModal()
    const labels = wrapper.findAll('.type-card-label').map(n => n.text())
    expect(labels).toContain('knowledge.connectors.config.typeGdrive')
  })

  it('shows the gdrive form with the OAuth Connect button after selecting Google Drive', async () => {
    const wrapper = mountModal()
    const cards = wrapper.findAll('.type-card')
    const gdriveCard = cards.find(c =>
      c.text().includes('knowledge.connectors.config.typeGdrive')
    )!
    await gdriveCard.trigger('click')
    await flushPromises()

    // Step advanced to config; the OAuth button is present.
    expect(wrapper.find('.oauth-stub').exists()).toBe(true)
  })

  it('captures the OAuth secret and creates the connector with gdrive config + secret_id', async () => {
    const wrapper = mountModal()
    const gdriveCard = wrapper
      .findAll('.type-card')
      .find(c => c.text().includes('knowledge.connectors.config.typeGdrive'))!
    await gdriveCard.trigger('click')
    await flushPromises()

    // Simulate the OAuth popup completing → emits connected with secretId.
    await wrapper.find('.oauth-stub').trigger('click')
    await flushPromises()

    // Drive the component to call createConnector via its save handler.
    const vm = wrapper.vm as any
    vm.connectorName = 'My Drive'
    await vm.handleSave()
    await flushPromises()

    expect(createSpy).toHaveBeenCalledTimes(1)
    const payload = createSpy.mock.calls[0][0]
    expect(payload.connector_type).toBe('gdrive')
    expect(payload.secret_id).toBe('sec-1')
    expect(payload.config.source_type).toBe('mydrive')
    expect(payload.config.sync_subfolders).toBe(true)
  })
})
