// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #16754 AC3 — the collaboration presence indicator renders the online participants that
 * useSessionCollaboration holds (seeded from GET .../presence and the presence socket):
 * one other participant, and several, with the stacked-avatar overflow.
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import type { UserPresence } from '@/composables/useSessionCollaboration'

const state = vi.hoisted(() => ({ presence: [] as unknown[], me: null as unknown }))
vi.mock('@/composables/useSessionCollaboration', () => ({
  useSessionCollaboration: () => ({
    sessionPresence: ref(state.presence),
    myPresence: ref(state.me),
    isConnected: ref(true),
  }),
}))

import PresenceIndicator from '../PresenceIndicator.vue'

function person(userId: string, username: string): UserPresence {
  return { userId, username, status: 'online', currentTab: 'chat' } as UserPresence
}

function mountWith(others: UserPresence[], expanded = false) {
  const me = person('me', 'Alex Doe')
  state.me = me
  state.presence = [me, ...others]
  return mount(PresenceIndicator, {
    props: { expanded },
    global: { mocks: { $t: (key: string, p?: Record<string, unknown>) => `${key}${p ? JSON.stringify(p) : ''}` } },
  })
}

const collaboratorTitles = (w: ReturnType<typeof mount>) =>
  w.findAll('[title^="collaboration.presence.collaboratorTooltip"]').map((el) => el.attributes('title'))

describe('PresenceIndicator renders who is present (#16754)', () => {
  it('one other participant: their avatar, initials and status tooltip', () => {
    const wrapper = mountWith([person('u1', 'ada_lovelace')])
    const titles = collaboratorTitles(wrapper)
    expect(titles).toHaveLength(1)
    expect(titles[0]).toContain('"name":"ada_lovelace"')
    expect(wrapper.text()).toContain('AL')
  })

  it('several participants: three stacked avatars and a +N overflow', () => {
    const others = ['ada', 'bob', 'cy', 'dee', 'eve'].map((n, i) => person(`u${i}`, n))
    const wrapper = mountWith(others)
    expect(collaboratorTitles(wrapper)).toHaveLength(3)
    expect(wrapper.text()).toContain('+2')
  })

  it('the expanded view counts everyone present, me included', () => {
    const wrapper = mountWith([person('u1', 'ada'), person('u2', 'bob')], true)
    expect(wrapper.text()).toContain('collaboration.presence.participants{"count":3}')
  })
})
