// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * #17099: SYSTEM-vault secrets are listed in the Secrets Manager, and rotate and
 * delete reach PUT/DELETE /api/secrets/{id} -- the routes that write the vault.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { HttpError } from '@autobot/ui'
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
    expect(wrapper.text()).toContain('system vault is unavailable')
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

  it('offers no second write while one is in flight (#20756)', async () => {
    updateSecret.mockReturnValue(new Promise(() => {}))
    const other = { id: 'sys-2', name: 'other-key', type: 'api_key' }
    const wrapper = mountList({ available: true, secrets: [entry, other] })
    await wrapper.find('[data-testid="rotate-start"]').trigger('click')
    await wrapper.find('input').setValue('new-secret-value')
    await wrapper.find('[data-testid="rotate-save"]').trigger('click')
    expect(wrapper.get('[data-testid="delete"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="rotate-start"]').attributes('disabled')).toBeDefined()
  })

  it('a second delete click while the confirm is open or the write is in flight does nothing (#20756)', async () => {
    let answer: (ok: boolean) => void = () => {}
    confirm.mockReturnValue(new Promise<boolean>((resolve) => (answer = resolve)))
    deleteSecret.mockReturnValue(new Promise(() => {}))
    const wrapper = mountList({ available: true, secrets: [entry] })
    const button = wrapper.get('[data-testid="delete"]')
    await button.trigger('click')
    expect(button.attributes('disabled')).toBeDefined()
    await button.trigger('click')
    answer(true)
    await flushPromises()
    await button.trigger('click')
    await flushPromises()
    expect(confirm).toHaveBeenCalledOnce()
    expect(deleteSecret).toHaveBeenCalledOnce()
  })

  it('remove() itself ignores a re-entrant call while busy, bypassing the disabled button (#20756)', async () => {
    confirm.mockReturnValue(new Promise<boolean>(() => {}))
    const wrapper = mountList({ available: true, secrets: [entry] })
    const button = wrapper.getComponent('[data-testid="delete"]')
    await button.trigger('click')
    expect(button.attributes('disabled')).toBeDefined()
    // trigger() is a no-op on a disabled element; emit the click straight to the bound handler.
    await button.vm.$emit('click')
    await button.vm.$emit('click')
    await flushPromises()
    expect(confirm).toHaveBeenCalledOnce()
    expect(deleteSecret).not.toHaveBeenCalled()
  })

  it('remove() ignores a click emitted while the DELETE is pending, past the first confirmation (#20756)', async () => {
    confirm.mockResolvedValue(true)
    deleteSecret.mockReturnValue(new Promise(() => {}))
    const wrapper = mountList({ available: true, secrets: [entry] })
    const button = wrapper.getComponent('[data-testid="delete"]')
    await button.trigger('click')
    await flushPromises()
    expect(deleteSecret).toHaveBeenCalledOnce()
    // trigger() is a no-op on a disabled element; emit the click straight to the bound handler.
    await button.vm.$emit('click')
    await flushPromises()
    expect(confirm).toHaveBeenCalledOnce()
    expect(deleteSecret).toHaveBeenCalledOnce()
  })

  it('cancelling the confirm re-enables Delete and deletes nothing (#20756)', async () => {
    confirm.mockResolvedValue(false)
    const wrapper = mountList({ available: true, secrets: [entry] })
    const button = wrapper.get('[data-testid="delete"]')
    await button.trigger('click')
    await flushPromises()
    expect(confirm).toHaveBeenCalledOnce()
    expect(deleteSecret).not.toHaveBeenCalled()
    expect(button.attributes('disabled')).toBeUndefined()
  })

  it('delete confirms, then calls DELETE /secrets/{id}', async () => {
    confirm.mockResolvedValue(true)
    const wrapper = mountList({ available: true, secrets: [entry] })
    await wrapper.find('[data-testid="delete"]').trigger('click')
    await flushPromises()
    expect(confirm).toHaveBeenCalledOnce()
    expect(deleteSecret).toHaveBeenCalledWith('sys-1', { chatId: undefined })
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('a declined confirmation deletes nothing', async () => {
    confirm.mockResolvedValue(false)
    const wrapper = mountList({ available: true, secrets: [entry] })
    await wrapper.find('[data-testid="delete"]').trigger('click')
    await flushPromises()
    expect(deleteSecret).not.toHaveBeenCalled()
  })

  it('a failed write is reported as unconfirmed and reloads the list to show what is stored', async () => {
    confirm.mockResolvedValue(true)
    deleteSecret.mockRejectedValue(new Error('403'))
    const wrapper = mountList({ available: true, secrets: [entry] })
    await wrapper.find('[data-testid="delete"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('could not be confirmed')
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('a delete refused for dependents lists them in a second confirm, then forces it (#20557)', async () => {
    confirm.mockResolvedValue(true)
    const detail = { code: 'secret_has_dependents', dependents: [{ dependent_kind: 'service', dependent_id: 'scheduler' }] }
    deleteSecret.mockRejectedValueOnce(new HttpError(409, 'Dependents use this secret', { detail })).mockResolvedValue({})
    const wrapper = mountList({ available: true, secrets: [entry] })
    await wrapper.find('[data-testid="delete"]').trigger('click')
    await flushPromises()
    expect(confirm).toHaveBeenCalledTimes(2)
    expect(confirm.mock.calls[1][0].message).toContain('service:scheduler')
    expect(deleteSecret).toHaveBeenLastCalledWith('sys-1', { confirmDependents: true })
  })

  it('declining the dependents confirm sends no forced delete (#20557)', async () => {
    confirm.mockResolvedValueOnce(true).mockResolvedValueOnce(false)
    const detail = { code: 'secret_has_dependents', dependents: [{ dependent_kind: 'agent', dependent_id: 'a-1' }] }
    deleteSecret.mockRejectedValue(new HttpError(409, 'Dependents use this secret', { detail }))
    const wrapper = mountList({ available: true, secrets: [entry] })
    await wrapper.find('[data-testid="delete"]').trigger('click')
    await flushPromises()
    expect(deleteSecret).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('changed')).toBeUndefined()
  })

  it('deleting one secret keeps the unsaved rotation draft of another', async () => {
    confirm.mockResolvedValue(true)
    const other = { id: 'sys-2', name: 'other-key', type: 'api_key' }
    const wrapper = mountList({ available: true, secrets: [entry, other] })
    await wrapper.findAll('[data-testid="rotate-start"]')[0].trigger('click')
    await wrapper.find('input').setValue('draft-value')
    await wrapper.find('[data-testid="delete"]').trigger('click')
    await flushPromises()
    expect(deleteSecret).toHaveBeenCalledWith('sys-2', { chatId: undefined })
    expect((wrapper.find('input').element as HTMLInputElement).value).toBe('draft-value')
  })
})
