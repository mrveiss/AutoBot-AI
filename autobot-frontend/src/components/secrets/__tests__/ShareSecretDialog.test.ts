// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * #16443: ShareSecretDialog.vue's share() call now hits the real backend
 * (POST /sessions/{id}/secrets/share via useSessionCollaboration's
 * shareSecretWithSession) instead of the fake WS relay, passes the selected
 * participants through, and only closes the dialog on a real success -- the
 * previous version closed unconditionally, matching a fire-and-forget call
 * that could never actually fail.
 *
 * The "expires in" selector is gone: api/collaboration.py's
 * Secret.share_with() has no expiry concept at all, so the control had no
 * effect on anything (same class of finding as #16450).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import ShareSecretDialog from '../ShareSecretDialog.vue'

const shareSecretWithSession = vi.fn()

vi.mock('@/composables/useSessionCollaboration', () => ({
  useSessionCollaboration: () => ({
    sessionPresence: { value: [{ userId: 'user-a', username: 'alice', status: 'online', lastSeen: new Date() }] },
    shareSecretWithSession: (...args: unknown[]) => shareSecretWithSession(...args)
  })
}))

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

function mountDialog() {
  return mount(ShareSecretDialog, {
    props: { modelValue: true, secretId: 'sec-1', secretName: 'prod-db-password', secretType: 'password' }, // pragma: allowlist secret
    attachTo: document.body,
    global: { plugins: [i18n] }
  })
}

beforeEach(() => {
  document.body.innerHTML = ''
  shareSecretWithSession.mockReset()
})

describe('ShareSecretDialog (#16443)', () => {
  it('has no expiry selector -- the backend has no expiry concept', () => {
    const wrapper = mountDialog()
    expect(wrapper.html()).not.toContain('expire')
  })

  it('shares with the selected participant and closes on success', async () => {
    shareSecretWithSession.mockResolvedValue(true)
    const wrapper = mountDialog()

    const participantButton = wrapper.findAll('button').find(b => b.text().includes('alice'))
    await participantButton?.trigger('click')
    const shareButton = wrapper.findAll('button').find(b => b.text() === 'Share Secret')
    await shareButton?.trigger('click')
    await wrapper.vm.$nextTick()

    expect(shareSecretWithSession).toHaveBeenCalledWith('sec-1', ['user-a'])
    expect(wrapper.emitted('update:modelValue')).toBeTruthy()
  })

  it('stays open and does not emit shared when the backend call fails', async () => {
    shareSecretWithSession.mockResolvedValue(false)
    const wrapper = mountDialog()

    const participantButton = wrapper.findAll('button').find(b => b.text().includes('alice'))
    await participantButton?.trigger('click')
    const shareButton = wrapper.findAll('button').find(b => b.text() === 'Share Secret')
    await shareButton?.trigger('click')
    await wrapper.vm.$nextTick()

    expect(shareSecretWithSession).toHaveBeenCalled()
    expect(wrapper.emitted('shared')).toBeFalsy()
  })
})
