// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * #16470: PendingInvitations.vue surfaces useSessionCollaboration's
 * pendingInvitations (#16460) -- real GET /sessions/invitations/mine and
 * POST /sessions/{id}/invitations/respond REST shapes, not a mock.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import PendingInvitations from '../PendingInvitations.vue'

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
  return mount(PendingInvitations, {
    global: { plugins: [i18n] }
  })
}

beforeEach(() => {
  pendingInvitations.value = []
  refreshPendingInvitations.mockReset().mockResolvedValue(undefined)
  respondToInvitation.mockReset().mockResolvedValue(true)
})

describe('PendingInvitations (#16470)', () => {
  it('calls refreshPendingInvitations on mount', async () => {
    mountComponent()
    await flushPromises()

    expect(refreshPendingInvitations).toHaveBeenCalledTimes(1)
  })

  it('shows the empty state when there are no invitations', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    expect(wrapper.text()).toContain('No pending invitations')
  })

  it('renders each pending invitation with its permission and accept/decline actions', async () => {
    pendingInvitations.value = [
      { sessionId: 'chat-9', fromUserId: 'owner-9', permission: 'editor', invitedAt: new Date().toISOString(), expiresAt: null }
    ]
    const wrapper = mountComponent()
    await flushPromises()

    expect(wrapper.text()).toContain('chat-9')
    expect(wrapper.text()).toContain('Editor')
    expect(wrapper.findAll('button').some(b => b.text() === 'Accept')).toBe(true)
    expect(wrapper.findAll('button').some(b => b.text() === 'Decline')).toBe(true)
  })

  it('accepting calls respondToInvitation(sessionId, true) with the real REST shape', async () => {
    pendingInvitations.value = [
      { sessionId: 'chat-9', fromUserId: 'owner-9', permission: 'viewer', invitedAt: new Date().toISOString(), expiresAt: null }
    ]
    const wrapper = mountComponent()
    await flushPromises()

    const acceptButton = wrapper.findAll('button').find(b => b.text() === 'Accept')
    await acceptButton?.trigger('click')
    await flushPromises()

    expect(respondToInvitation).toHaveBeenCalledWith('chat-9', true)
  })

  it('declining calls respondToInvitation(sessionId, false)', async () => {
    pendingInvitations.value = [
      { sessionId: 'chat-9', fromUserId: 'owner-9', permission: 'viewer', invitedAt: new Date().toISOString(), expiresAt: null }
    ]
    const wrapper = mountComponent()
    await flushPromises()

    const declineButton = wrapper.findAll('button').find(b => b.text() === 'Decline')
    await declineButton?.trigger('click')
    await flushPromises()

    expect(respondToInvitation).toHaveBeenCalledWith('chat-9', false)
  })

  it('shows an inline error when respondToInvitation resolves false, and clears it on retry (review on #16472)', async () => {
    respondToInvitation.mockResolvedValueOnce(false)
    pendingInvitations.value = [
      { sessionId: 'chat-9', fromUserId: 'owner-9', permission: 'viewer', invitedAt: new Date().toISOString(), expiresAt: null }
    ]
    const wrapper = mountComponent()
    await flushPromises()

    const acceptButton = wrapper.findAll('button').find(b => b.text() === 'Accept')
    await acceptButton?.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain("Couldn't process this response. Please try again.")

    respondToInvitation.mockResolvedValueOnce(true)
    await wrapper.findAll('button').find(b => b.text() === 'Accept')?.trigger('click')
    await flushPromises()

    expect(wrapper.text()).not.toContain("Couldn't process this response. Please try again.")
  })
})
