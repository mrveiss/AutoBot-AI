// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// ChatCollaborationPanel (#18243, #21993): the Participants tab mounts PresenceIndicator above
// ParticipantList; the tabs are the kit's, with the tabpanel owned here.
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

vi.mock('@/composables/useSessionCollaboration', () => ({
  useSessionCollaboration: () => ({
    secretNotifications: ref([{ id: 1 }]), pendingInvitations: ref([]),
    sessionPresence: ref([]), myPresence: ref(null), isConnected: ref(true),
  }),
}))
vi.mock('@/stores/useChatStore', () => ({ useChatStore: () => ({ currentSession: { id: 's1' } }) }))
vi.mock('@/services/api', () => ({ apiService: {} }))
vi.mock('@/components/collaboration/PresenceIndicator.vue', () => ({ default: { template: '<div data-testid="presence" />' } }))
vi.mock('@/components/collaboration/ParticipantList.vue', () => ({ default: { template: '<div data-testid="participants" />' } }))
vi.mock('@/components/collaboration/ActivityFeed.vue', () => ({ default: { template: '<div data-testid="activity" />' } }))
vi.mock('@/components/collaboration/SecretNotifications.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/collaboration/PendingInvitations.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/collaboration/InviteUserDialog.vue', () => ({ default: { template: '<div />' } }))

import ChatCollaborationPanel from '../ChatCollaborationPanel.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const render = () => mount(ChatCollaborationPanel, { attachTo: document.body, global: { plugins: [i18n] } })

describe('ChatCollaborationPanel', () => {
  it('mounts PresenceIndicator in the Participants tab, before ParticipantList', async () => {
    const w = render()
    await flushPromises()
    const html = w.html()
    expect(w.find('[data-testid="presence"]').exists()).toBe(true)
    expect(html.indexOf('data-testid="presence"')).toBeLessThan(html.indexOf('data-testid="participants"'))
    w.unmount()
  })

  it('is a named tablist whose active tab controls the panel, with the pending count in the label', async () => {
    const w = render()
    await flushPromises()
    const tabs = w.findAll('[role="tab"]')
    expect(tabs.map((t) => t.text())).toEqual(['Participants', 'Activity', 'Notifications (1)', 'Invitations'])
    expect(tabs[0].attributes('aria-controls')).toBe('chat-collab-tabpanel')
    expect(w.get('[role="tabpanel"]').attributes('aria-labelledby')).toBe('chat-collab-tab-participants')
    w.unmount()
  })

  it('switches tab and drops the presence indicator with the Participants tab', async () => {
    const w = render()
    await flushPromises()
    await w.get('#chat-collab-tab-activity').trigger('mousedown')
    await flushPromises()
    expect(w.find('[data-testid="activity"]').exists()).toBe(true)
    expect(w.find('[data-testid="presence"]').exists()).toBe(false)
    w.unmount()
  })

  it('closes from its named close button', async () => {
    const w = render()
    await w.get('[aria-label="Close panel"]').trigger('click')
    expect(w.emitted('close')).toHaveLength(1)
    w.unmount()
  })
})
