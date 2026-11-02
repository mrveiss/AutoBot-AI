// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * SecretsManager offers only what the server enforces (#16450), and its
 * categories cover every canonical secret kind (#15008).
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createPinia, setActivePinia } from 'pinia'
import en from '@/i18n/locales/en.json'
import SecretsManager from '../security/SecretsManager.vue'

const createSecret = vi.fn().mockResolvedValue({})
const logSecretUsage = vi.fn()
let isAdmin = false

vi.mock('@/utils/SecretsApiClient', () => ({
  secretsApiClient: {
    getSecrets: vi.fn().mockResolvedValue({ secrets: [] }),
    getSecretsStats: vi.fn().mockResolvedValue({ total: 0, by_type: {}, by_scope: {} }),
    createSecret: (...args: unknown[]) => createSecret(...args),
    getSecret: vi.fn(),
    updateSecret: vi.fn(),
    deleteSecret: vi.fn(),
    transferSecrets: vi.fn(),
  },
}))
vi.mock('@/composables/security/useSecretsInfraApi', () => ({
  useSecretsInfraApi: () => ({
    fetchInfraHosts: vi.fn().mockResolvedValue({ hosts: [] }),
    fetchSecretsUsage: vi.fn().mockResolvedValue({}),
    deleteInfraHost: vi.fn(),
  }),
}))
vi.mock('@/stores/useUserStore', () => ({
  useUserStore: () => ({
    get isAdmin() {
      return isAdmin
    },
  }),
}))
vi.mock('@/composables/useSessionActivityLogger', () => ({
  useSessionActivityLogger: () => ({ logSecretUsage: (...args: unknown[]) => logSecretUsage(...args) }),
}))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ info: vi.fn(), warn: vi.fn(), error: vi.fn(), debug: vi.fn() }),
}))

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en }, missingWarn: false, fallbackWarn: false })

type ManagerVm = {
  openCreateModal: () => void
  saveSecret: () => Promise<void>
  secretForm: Record<string, unknown>
  credentialCategories: Array<{ type: string; label: string }>
  viewingSecret: Record<string, unknown> | null
  toggleSecretValue: () => void
  copySecretValue: () => Promise<void>
  getTypeLabel: (type?: string) => string
}

async function mountManager() {
  const wrapper = mount(SecretsManager, {
    global: {
      plugins: [i18n],
      stubs: {
        BaseModal: { template: '<div class="modal-stub"><slot /><slot name="footer" /></div>' },
        ShareSecretDialog: true,
        Teleport: true,
      },
    },
  })
  await flushPromises()
  return { wrapper, vm: wrapper.vm as unknown as ManagerVm }
}

describe('SecretsManager access controls (#16450)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    isAdmin = false
    createSecret.mockClear()
  })

  it('offers no Visibility / Organization / Team / Shared-With control in the create form', async () => {
    const { wrapper, vm } = await mountManager()
    vm.openCreateModal()
    // The form proper renders once a kind is chosen (before that: template picker).
    vm.secretForm.type = 'api_key'
    await flushPromises()

    // Contrast: the form did render -- its Scope control is there.
    expect(wrapper.find('#secret-scope').exists()).toBe(true)
    for (const id of ['#secret-visibility', '#secret-org-id', '#secret-team-ids', '#secret-shared-with']) {
      expect(wrapper.find(id).exists()).toBe(false)
    }
  })

  it('sends no access-control field the server would silently drop', async () => {
    const { vm } = await mountManager()
    vm.openCreateModal()
    Object.assign(vm.secretForm, { type: 'api_key', name: 'OPENAI_API_KEY', scope: 'general', value: 'sk-test' })
    await vm.saveSecret()

    expect(createSecret).toHaveBeenCalledTimes(1)
    const payload = createSecret.mock.calls[0][0] as Record<string, unknown>
    expect(payload).toMatchObject({ type: 'api_key', name: 'OPENAI_API_KEY', scope: 'general' })
    for (const field of ['visibility', 'org_id', 'team_ids', 'shared_with']) {
      expect(payload).not.toHaveProperty(field)
    }
  })
})

describe('SecretsManager categories (#15008)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('offers a translated category for every canonical kind, including the three that were missing', async () => {
    isAdmin = true
    const { vm } = await mountManager()
    const byType = Object.fromEntries(vm.credentialCategories.map((c) => [c.type, c.label]))

    expect(Object.keys(byType)).toHaveLength(10)
    expect(byType.oauth_refresh_token).toBe(en.security.secretsManager.categories.oauth_refresh_token)
    expect(byType.connector_oauth_token).toBe(en.security.secretsManager.categories.connector_oauth_token)
    expect(byType.infrastructure_host).toBe(en.security.secretsManager.categories.infrastructure_host)
  })

  it('keeps the admin-only infrastructure category from a non-admin', async () => {
    isAdmin = false
    const { vm } = await mountManager()
    expect(vm.credentialCategories.map((c) => c.type)).not.toContain('infrastructure_host')
  })

  it('labels a single secret by its translated kind, not by trimming a plural', async () => {
    const { vm } = await mountManager()
    expect(vm.getTypeLabel('connector_oauth_token')).toBe(en.security.secretsManager.kinds.connector_oauth_token)
    expect(vm.getTypeLabel('some_future_kind')).toBe('Some Future Kind')
  })
})

describe('SecretsManager session usage logging (#17976)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    logSecretUsage.mockClear()
  })

  it('logs a reveal once when the value is shown, not when it is hidden again', async () => {
    const { vm } = await mountManager()
    vm.viewingSecret = { id: 's1', name: 'CONNECTOR', type: 'connector_oauth_token', value: 'v' }

    vm.toggleSecretValue()
    vm.toggleSecretValue()

    expect(logSecretUsage).toHaveBeenCalledTimes(1)
    expect(logSecretUsage).toHaveBeenCalledWith('reveal', 's1', 'CONNECTOR', 'connector_oauth_token')
  })

  it('logs a copy after the value reaches the clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    const { vm } = await mountManager()
    vm.viewingSecret = { id: 's2', name: 'KEY', type: 'api_key', value: 'v' }

    await vm.copySecretValue()

    expect(writeText).toHaveBeenCalledWith('v')
    expect(logSecretUsage).toHaveBeenCalledWith('copy', 's2', 'KEY', 'api_key')
  })

  it('logs an unrecognised server kind as other rather than casting it through', async () => {
    const { vm } = await mountManager()
    vm.viewingSecret = { id: 's3', name: 'X', type: 'some_future_kind', value: 'v' }

    vm.toggleSecretValue()

    expect(logSecretUsage).toHaveBeenCalledWith('reveal', 's3', 'X', 'other')
  })
})
