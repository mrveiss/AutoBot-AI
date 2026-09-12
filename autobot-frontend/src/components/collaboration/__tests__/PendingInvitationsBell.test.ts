// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * #16470 follow-up: PendingInvitationsBell.vue is the entry point for the
 * common case a plain "Invitations tab in the collaboration panel" can't
 * reach -- an invitee with NO collaborative session of their own (the
 * panel that hosts that tab only opens for an already-collaborative
 * session). This must be visible and usable independent of session mode.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import PendingInvitationsBell from '../PendingInvitationsBell.vue'

const refreshPendingInvitations = vi.fn()
const respondToInvitation = vi.fn()

const pendingInvitations = {
  value: [] as Array<{ sessionId: string; fromUserId: string; permission: string; invitedAt: string; expiresAt: string | null }>
}

vi.mock('@/composables/useSessionCollaboration', () => ({
  useSessionCollaboration: () => ({
    pendingInvitations,
    refreshPendingInvitations: (...args: unknown[]) => refreshPendingInvitations(...args),
    respondToInvitation: (...args: unknown[]) => respondToInvitation(...args)
  })
}))

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

function mountComponent() {
  return mount(PendingInvitationsBell, {
    global: { plugins: [i18n] }
  })
}

beforeEach(() => {
  pendingInvitations.value = []
  refreshPendingInvitations.mockReset().mockResolvedValue(undefined)
  respondToInvitation.mockReset().mockResolvedValue(true)
})

describe('PendingInvitationsBell (#16470 follow-up)', () => {
  it('renders nothing when there are no pending invitations and it has not been opened', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    expect(wrapper.find('button').exists()).toBe(false)
  })

  it('a user with zero collaborative sessions and one pending invite sees the indicator', async () => {
    // No `currentSession`/session-mode dependency anywhere in this
    // component or its mock -- the bell has no notion of "collaborative
    // session" at all, unlike ChatCollaborationPanel's own gating.
    pendingInvitations.value = [
      { sessionId: 'chat-9', fromUserId: 'owner-9', permission: 'editor', invitedAt: new Date().toISOString(), expiresAt: null }
    ]
    const wrapper = mountComponent()
    await flushPromises()

    const button = wrapper.find('button')
    expect(button.exists()).toBe(true)
    expect(wrapper.text()).toContain('1')
  })

  it('refreshes pending invitations on mount', async () => {
    mountComponent()
    await flushPromises()

    expect(refreshPendingInvitations).toHaveBeenCalledTimes(1)
  })

  it('clicking the bell opens a dropdown listing the invitation', async () => {
    pendingInvitations.value = [
      { sessionId: 'chat-9', fromUserId: 'owner-9', permission: 'editor', invitedAt: new Date().toISOString(), expiresAt: null }
    ]
    const wrapper = mountComponent()
    await flushPromises()

    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    await wrapper.find('button').trigger('click')

    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('chat-9')
  })

  it('stays open when the last invitation is resolved mid-interaction', async () => {
    pendingInvitations.value = [
      { sessionId: 'chat-9', fromUserId: 'owner-9', permission: 'viewer', invitedAt: new Date().toISOString(), expiresAt: null }
    ]
    const wrapper = mountComponent()
    await flushPromises()
    await wrapper.find('button').trigger('click')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)

    // Simulate the invitation resolving to empty (e.g. accepted) while open.
    pendingInvitations.value = []
    await wrapper.vm.$nextTick()

    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
  })
})
