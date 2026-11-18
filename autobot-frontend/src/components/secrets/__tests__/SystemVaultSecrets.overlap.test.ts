// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * #20756: with the REAL shared confirm dialog, a confirmation that overlaps another one
 * must not leave the panel busy once the dialog is dismissed.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import { useConfirmDialog, _resetForTests } from '@/composables/useConfirmDialog'
import SystemVaultSecrets from '../SystemVaultSecrets.vue'

const deleteSecret = vi.fn()

vi.mock('@/utils/SecretsApiClient', () => ({
  secretsApiClient: {
    updateSecret: vi.fn(),
    deleteSecret: (...args: unknown[]) => deleteSecret(...args)
  }
}))

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })
const entry = { id: 'sys-1', name: 'audit-worker-key', type: 'api_key' }

beforeEach(() => {
  _resetForTests()
  deleteSecret.mockReset().mockResolvedValue({})
})

describe('SystemVaultSecrets with the shared confirm dialog (#20756)', () => {
  it('clears busy after a confirmation that overlapped another is dismissed', async () => {
    const { confirm, _resolve, dialogVisible } = useConfirmDialog()
    // A user-secret delete is awaiting its confirmation when the vault delete opens its own.
    const earlier = confirm({ title: 'user secret', message: 'delete?' })
    const wrapper = mount(SystemVaultSecrets, {
      props: { vault: { available: true, secrets: [entry] } },
      global: { plugins: [i18n] }
    })
    const button = wrapper.get('[data-testid="delete"]')
    await button.trigger('click')
    await expect(earlier).resolves.toBe(false)
    expect(button.attributes('disabled')).toBeDefined()
    _resolve(false)
    await flushPromises()
    expect(dialogVisible.value).toBe(false)
    expect(button.attributes('disabled')).toBeUndefined()
    expect(wrapper.get('[data-testid="rotate-start"]').attributes('disabled')).toBeUndefined()
    expect(deleteSecret).not.toHaveBeenCalled()
  })
})
