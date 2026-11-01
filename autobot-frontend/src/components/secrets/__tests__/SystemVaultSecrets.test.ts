// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * #17099: SYSTEM-vault secrets are listed in the Secrets Manager, and rotate and
 * delete reach PUT/DELETE /api/secrets/{id} -- the routes that write the vault.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import SystemVaultSecrets from '../SystemVaultSecrets.vue'

const updateSecret = vi.fn()
const deleteSecret = vi.fn()
const confirm = vi.fn()

vi.mock('@/utils/SecretsApiClient', () => ({
  secretsApiClient: {
    updateSecret: (...args: unknown[]) => updateSecret(...args),
    deleteSecret: (...args: unknown[]) => deleteSecret(...args)
  }
}))
vi.mock('@/components/ui/Icon.vue', () => ({ default: { name: 'Icon', template: '<i />' } }))
vi.mock('@/composables/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: (...args: unknown[]) => confirm(...args) })
}))

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })
const entry = { id: 'sys-1', name: 'audit-worker-key', type: 'api_key' }

function mountList(vault: { available: boolean; secrets: (typeof entry)[] } | null) {
  return mount(SystemVaultSecrets, { props: { vault }, global: { plugins: [i18n] } })
}

beforeEach(() => {
  updateSecret.mockReset().mockResolvedValue({})
  deleteSecret.mockReset().mockResolvedValue({})
  confirm.mockReset()
})

describe('SystemVaultSecrets (#17099)', () => {
  it('renders nothing for a caller without system-vault data', () => {
    expect(mountList(null).find('[data-testid="system-vault"]').exists()).toBe(false)
  })

  it('shows the entry by name and type, with no value', () => {
    const wrapper = mountList({ available: true, secrets: [entry] })
    expect(wrapper.text()).toContain('audit-worker-key')
    expect(wrapper.text()).toContain('api_key')
    expect(wrapper.find('input').exists()).toBe(false)
  })

  it('says so when the vault is unavailable instead of omitting the section', () => {
    const wrapper = mountList({ available: false, secrets: [] })
    expect(wrapper.find('[role="alert"]').text()).toContain('system vault is unavailable')
  })

  it('rotate sends the new value to PUT /secrets/{id} and asks for a reload', async () => {
    const wrapper = mountList({ available: true, secrets: [entry] })
    await wrapper.find('[data-testid="rotate-start"]').trigger('click')
    await wrapper.find('input').setValue('new-secret-value')
    await wrapper.find('[data-testid="rotate-save"]').trigger('click')
    await flushPromises()
    expect(updateSecret).toHaveBeenCalledWith('sys-1', { value: 'new-secret-value' })
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('delete confirms, then calls DELETE /secrets/{id}', async () => {
    confirm.mockResolvedValue(true)
    const wrapper = mountList({ available: true, secrets: [entry] })
    await wrapper.find('[data-testid="delete"]').trigger('click')
    await flushPromises()
    expect(confirm).toHaveBeenCalledOnce()
    expect(deleteSecret).toHaveBeenCalledWith('sys-1')
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('a declined confirmation deletes nothing', async () => {
    confirm.mockResolvedValue(false)
    const wrapper = mountList({ available: true, secrets: [entry] })
    await wrapper.find('[data-testid="delete"]').trigger('click')
    await flushPromises()
    expect(deleteSecret).not.toHaveBeenCalled()
  })

  it('a refused write is reported and does not reload as if it worked', async () => {
    confirm.mockResolvedValue(true)
    deleteSecret.mockRejectedValue(new Error('403'))
    const wrapper = mountList({ available: true, secrets: [entry] })
    await wrapper.find('[data-testid="delete"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Nothing was modified')
    expect(wrapper.emitted('changed')).toBeUndefined()
  })
})
