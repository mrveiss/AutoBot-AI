// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// ChatSessionList (#18243): one row per session, roving-tabindex keys, selection mode, empty states.
import { describe, it, expect } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import ChatSessionList from '../ChatSessionList.vue'
import type { ChatSession } from '@/stores/useChatStore'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const session = (id: string, title: string): ChatSession => ({ id, title, messages: [], updatedAt: new Date() }) as unknown as ChatSession
const SESSIONS = [session('a', 'Alpha'), session('b', 'Beta'), session('c', 'Gamma')]

function render(props: Record<string, unknown> = {}) {
  return mount(ChatSessionList, {
    props: {
      sessions: SESSIONS, totalCount: 3, currentSessionId: 'b', selectionMode: false,
      isSelected: () => false, titleOf: (s: ChatSession) => s.title, folders: [], ...props,
    },
    attachTo: document.body,
    global: { plugins: [i18n] },
  })
}
const rows = (w: ReturnType<typeof render>) => w.findAll('[role="button"][tabindex]')

describe('ChatSessionList', () => {
  it('renders a row per session and marks the current one', () => {
    const w = render()
    expect(rows(w)).toHaveLength(3)
    expect(w.findAll('[aria-current="page"]')).toHaveLength(1)
    w.unmount()
  })

  it('opens a session on click, and on Enter', async () => {
    const w = render()
    await rows(w)[0].trigger('click')
    await rows(w)[1].trigger('keydown', { key: 'Enter' })
    expect(w.emitted('open')?.map((e) => (e[0] as ChatSession).id)).toEqual(['a', 'b'])
    w.unmount()
  })

  it('moves focus with ArrowDown, ArrowUp, End and Home', async () => {
    const w = render()
    const press = async (i: number, key: string) => {
      await rows(w)[i].trigger('keydown', { key })
      await flushPromises()
    }
    await press(0, 'ArrowDown')
    expect(document.activeElement).toBe(rows(w)[1].element)
    await press(1, 'End')
    expect(document.activeElement).toBe(rows(w)[2].element)
    await press(2, 'ArrowUp')
    expect(document.activeElement).toBe(rows(w)[1].element)
    await press(1, 'Home')
    expect(document.activeElement).toBe(rows(w)[0].element)
    w.unmount()
  })

  it('toggles selection instead of opening in selection mode', async () => {
    const w = render({ selectionMode: true })
    await rows(w)[2].trigger('click')
    expect(w.emitted('open')).toBeUndefined()
    expect((w.emitted('toggle-select')?.[0][0] as ChatSession).id).toBe('c')
    w.unmount()
  })

  it('tells "no chats" from "nothing matches"', () => {
    expect(render({ sessions: [], totalCount: 0 }).text()).toContain('No chat sessions yet')
    expect(render({ sessions: [], totalCount: 3 }).text()).toContain('No chats match your search')
  })
})
