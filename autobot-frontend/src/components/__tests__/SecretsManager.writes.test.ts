// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * SecretsManager writes and reloads: a user-secret delete takes the same path as the
 * system vault's (#20732), and overlapping loads keep the newest result (#20734).
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createPinia, setActivePinia } from 'pinia'
import { HttpError } from '@autobot/ui'
import en from '@/i18n/locales/en.json'
import SecretsManager from '../security/SecretsManager.vue'

const getSecrets = vi.fn()
const deleteSecret = vi.fn()
const confirm = vi.fn()

vi.mock('@/utils/SecretsApiClient', () => ({
  secretsApiClient: {
    getSecrets: (...args: unknown[]) => getSecrets(...args),
    getSecretsStats: vi.fn().mockResolvedValue({ total: 0, by_type: {}, by_scope: {} }),
    createSecret: vi.fn(),
    getSecret: vi.fn(),
    updateSecret: vi.fn(),
    deleteSecret: (...args: unknown[]) => deleteSecret(...args),
    transferSecrets: vi.fn(),
  },
}))
vi.mock('@/composables/security/useSecretsInfraApi', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/composables/security/useSecretsInfraApi')>()),
  useSecretsInfraApi: () => ({
    fetchInfraHosts: vi.fn().mockResolvedValue({ hosts: [] }),
    fetchSecretsUsage: vi.fn().mockResolvedValue({}),
    deleteInfraHost: vi.fn(),
  }),
}))
vi.mock('@/composables/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: (...args: unknown[]) => confirm(...args) }),
}))
vi.mock('@/stores/useUserStore', () => ({ useUserStore: () => ({ isAdmin: false }) }))
vi.mock('@/composables/useSessionActivityLogger', () => ({
  useSessionActivityLogger: () => ({ logSecretUsage: vi.fn() }),
}))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ info: vi.fn(), warn: vi.fn(), error: vi.fn(), debug: vi.fn() }),
}))

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en }, missingWarn: false, fallbackWarn: false })

const secret = (id: string) => ({ id, name: id, type: 'api_key', scope: 'general', chat_id: null, tags: [] })
const listing = (...ids: string[]) => ({ secrets: ids.map(secret), system_vault: { available: true, secrets: [] } })

type ManagerVm = {
  secrets: Array<{ id: string }>
  loadSecrets: () => Promise<void>
  confirmDelete: (s: unknown) => void
  deleteSecret: () => Promise<void>
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

async function deleteUserSecret(vm: ManagerVm) {
  vm.confirmDelete(secret('s1'))
  await vm.deleteSecret()
  await flushPromises()
}

describe('SecretsManager writes and reloads (#20732, #20734)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    getSecrets.mockReset().mockResolvedValue(listing('s1'))
    deleteSecret.mockReset()
    confirm.mockReset()
  })

  it('keeps the newer load when an older one answers last (#20734)', async () => {
    let answerFirst: (v: unknown) => void = () => {}
    getSecrets.mockReset()
      .mockImplementationOnce(() => new Promise((resolve) => { answerFirst = resolve }))
      .mockResolvedValue(listing('fresh'))
    const { vm } = await mountManager()
    await vm.loadSecrets()
    answerFirst(listing('stale'))
    await flushPromises()
    expect(vm.secrets.map((s) => s.id)).toEqual(['fresh'])
  })

  it('a delete refused for dependents lists them in a second confirm, then forces it', async () => {
    deleteSecret
      .mockRejectedValueOnce(new HttpError(409, 'Conflict', {
        detail: { code: 'secret_has_dependents', dependents: [{ dependent_kind: 'service', dependent_id: 'scheduler' }] },
      }))
      .mockResolvedValueOnce({})
    confirm.mockResolvedValue(true)
    const { vm } = await mountManager()
    await deleteUserSecret(vm)
    expect(confirm.mock.calls[0][0].message).toContain('service:scheduler')
    expect(deleteSecret).toHaveBeenLastCalledWith('s1', { chatId: null, confirmDependents: true })
  })

  it('a failed delete shows the unconfirmed-write alert and reloads the list', async () => {
    deleteSecret.mockRejectedValue(new HttpError(500, 'Server Error'))
    const { wrapper, vm } = await mountManager()
    const loadsBefore = getSecrets.mock.calls.length
    await deleteUserSecret(vm)
    expect(wrapper.get('[data-testid="secrets-write-failed"]').text()).toBe(en.security.secretsManager.writeFailed)
    expect(getSecrets.mock.calls.length).toBe(loadsBefore + 1)
  })
})
