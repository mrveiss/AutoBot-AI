// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Tests for the GitLab / Gitea / Forgejo surface in ConnectorConfigModal (Issue #9011).
 *
 * Proves end-to-end UI wiring: the gitlab/gitea/forgejo type cards render, selecting
 * GitLab shows the token + URL form (no OAuth button — these are self-hosted token
 * connectors), and saving calls createConnector with connector_type 'gitlab' plus the
 * token in config (credential-store path, NOT secret_id / OAuth).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

import type { App } from 'vue'
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

function mountModal() {
  return mount(ConnectorConfigModal, {
    props: { modelValue: true, editConnector: null },
    global: {
      mocks: { $t: (k: string) => k },
      stubs: {
        ConnectorOAuthButton: { template: '<button class="oauth-stub">Connect</button>' },
        BaseModal: { template: '<div><slot /><slot name="actions" /></div>' },
        BaseButton: { template: '<button><slot /></button>' }
      },
      plugins: [
        {
          install(app: App) {
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

function findCard(wrapper: ReturnType<typeof mountModal>, labelKey: string) {
  return wrapper.findAll('.type-card').find(c => c.text().includes(labelKey))!
}

describe('ConnectorConfigModal — GitLab / Gitea / Forgejo (#9011)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    createSpy.mockResolvedValue({ connector_id: 'new-gitlab', connector_type: 'gitlab' })
  })

  it('renders GitLab, Gitea, and Forgejo type cards on step 1', () => {
    const wrapper = mountModal()
    const labels = wrapper.findAll('.type-card-label').map(n => n.text())
    expect(labels).toContain('knowledge.connectors.config.typeGitlab')
    expect(labels).toContain('knowledge.connectors.config.typeGitea')
    expect(labels).toContain('knowledge.connectors.config.typeForgejo')
  })

  it('shows the GitLab token + URL form (no OAuth button) after selecting GitLab', async () => {
    const wrapper = mountModal()
    await findCard(wrapper, 'knowledge.connectors.config.typeGitlab').trigger('click')
    await flushPromises()

    expect(wrapper.find('#gl-url').exists()).toBe(true)
    expect(wrapper.find('#gl-token').exists()).toBe(true)
    expect((wrapper.find('#gl-token').element as HTMLInputElement).type).toBe('password')
    // Token connectors do not use the OAuth Connect button.
    expect(wrapper.find('.oauth-stub').exists()).toBe(false)
  })

  it('creates the connector with connector_type gitlab and the token in config (not secret_id)', async () => {
    const wrapper = mountModal()
    await findCard(wrapper, 'knowledge.connectors.config.typeGitlab').trigger('click')
    await flushPromises()

    await wrapper.find('#gl-token').setValue('glpat-secrettoken')
    await wrapper.find('#gl-projects').setValue('42, group/proj')

    const vm = wrapper.vm as unknown as { connectorName: string; handleSave: () => Promise<void> }
    vm.connectorName = 'My GitLab'
    await vm.handleSave()
    await flushPromises()

    expect(createSpy).toHaveBeenCalledTimes(1)
    const payload = createSpy.mock.calls[0][0]
    expect(payload.connector_type).toBe('gitlab')
    expect(payload.secret_id).toBeUndefined()
    expect(payload.config.token).toBe('glpat-secrettoken')
    expect(payload.config.gitlab_url).toBe('https://gitlab.com')
    expect(payload.config.project_ids).toEqual(['42', 'group/proj'])
    expect(payload.config.sync_issues).toBe(true)
    expect(payload.config.sync_merge_requests).toBe(true)
  })

  it('selecting Gitea shows the required instance-URL + token form and sends gitea config', async () => {
    const wrapper = mountModal()
    await findCard(wrapper, 'knowledge.connectors.config.typeGitea').trigger('click')
    await flushPromises()

    expect(wrapper.find('#gt-url').exists()).toBe(true)
    await wrapper.find('#gt-url').setValue('https://git.example.com')
    await wrapper.find('#gt-token').setValue('gitea-token')
    await wrapper.find('#gt-repos').setValue('owner/repo')

    const vm = wrapper.vm as unknown as { connectorName: string; handleSave: () => Promise<void> }
    vm.connectorName = 'My Gitea'
    await vm.handleSave()
    await flushPromises()

    const payload = createSpy.mock.calls[0][0]
    expect(payload.connector_type).toBe('gitea')
    expect(payload.secret_id).toBeUndefined()
    expect(payload.config.gitea_url).toBe('https://git.example.com')
    expect(payload.config.token).toBe('gitea-token')
    expect(payload.config.repos).toEqual(['owner/repo'])
  })
})
