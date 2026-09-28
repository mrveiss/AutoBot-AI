// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The desktop tab is offered to exactly the roles the socket admits (#17370).
 *
 * `enforce_ws_desktop_auth` requires `mcp.desktop.control` via
 * `role_has_permission` (#17054, PR #17369). The UI must ask the SAME source,
 * so the two cannot disagree.
 *
 * WHY `holdsPermission` AND NOT `hasPermission`. `hasPermission` short-circuits
 * on `isAdmin`, and `isAdmin` admits `superadmin` -- whose `ROLE_PERMISSIONS`
 * entry is EMPTY by #13854's ruling, so the socket refuses it. Gating on
 * `hasPermission` would show a superadmin a desktop the handshake then closes
 * with 1008. The superadmin case below is the one that fails if anyone swaps
 * the two functions, and it is the reason this file exists rather than a single
 * admin/non-admin pair.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import de from '@/i18n/locales/de.json'

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ error: vi.fn(), info: vi.fn(), warn: vi.fn(), debug: vi.fn() }),
}))

import ChatTabs from '../ChatTabs.vue'
import { useUserStore } from '@/stores/useUserStore'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en, de } })

function mountTabs(role: string) {
  const store = useUserStore()
  // Only `role` participates in the permission lookup; the store's user shape
  // is not otherwise exercised here.
  store.currentUser = { role } as never
  return mount(ChatTabs, {
    props: { activeTab: 'chat' },
    global: { plugins: [i18n] },
  })
}

function tabLabels(wrapper: ReturnType<typeof mount>): string[] {
  return wrapper.findAll('button').map(b => b.text())
}

const DESKTOP = en.chat.tabs.novnc

describe('ChatTabs desktop gate (#17370)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('offers the desktop tab to a role the table grants', () => {
    // `admin` holds mcp.desktop.control in ROLE_PERMISSIONS.
    expect(tabLabels(mountTabs('admin'))).toContain(DESKTOP)
  })

  it('offers it to operator too, which the socket also admits', () => {
    expect(tabLabels(mountTabs('operator'))).toContain(DESKTOP)
  })

  it('withholds it from an ordinary signed-in role', () => {
    // The other half of the pair: "hidden for everyone" would satisfy the
    // negative case on its own.
    const labels = tabLabels(mountTabs('user'))
    expect(labels).not.toContain(DESKTOP)
    expect(labels).toContain(en.chat.tabs.chat)
  })

  it('withholds it from superadmin, agreeing with the socket that refuses it', () => {
    // THE DISCRIMINATING CASE. `isAdmin` is true for superadmin, so
    // `hasPermission('mcp.desktop.control')` returns true, while
    // ROLE_PERMISSIONS[superadmin] is empty and the socket closes with 1008.
    // This is the only assertion here that distinguishes the two functions.
    expect(tabLabels(mountTabs('superadmin'))).not.toContain(DESKTOP)
  })

  it('keeps every non-desktop tab for a refused role', () => {
    // The gate removes one entry, not the tab bar.
    const labels = tabLabels(mountTabs('user'))
    for (const key of ['chat', 'files', 'terminal', 'browser'] as const) {
      expect(labels).toContain(en.chat.tabs[key])
    }
    expect(labels).toHaveLength(4)
  })

  it('renders tab labels from the locale file, not hardcoded English', () => {
    // All five labels were English literals in a `withDefaults` default
    // (#17370's fourth criterion). German is the only observation that can
    // tell a translated label from an English one, since en.json says what
    // the literals said -- 'Chat', 'Files', 'Terminal', 'Browser'.
    const deI18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'en', messages: { en, de } })
    const store = useUserStore()
    store.currentUser = { role: 'admin' } as never
    const wrapper = mount(ChatTabs, {
      props: { activeTab: 'chat' },
      global: { plugins: [deI18n] },
    })

    const labels = tabLabels(wrapper)
    expect(labels).toContain(de.chat.tabs.files)
    expect(labels).toContain(de.chat.tabs.novnc)
    expect(labels).not.toContain(en.chat.tabs.files)
    expect(labels).not.toContain(en.chat.tabs.novnc)
  })

  it('still honours an explicitly passed tab list, minus the desktop entry', () => {
    // The gate must filter caller-supplied tabs too, or a parent passing its
    // own list routes around it.
    const store = useUserStore()
    store.currentUser = { role: 'user' } as never
    const wrapper = mount(ChatTabs, {
      props: {
        activeTab: 'chat',
        tabs: [
          { key: 'chat', label: 'Given', icon: 'comments' },
          { key: 'novnc', label: 'Given desktop', icon: 'desktop' },
        ],
      },
      global: { plugins: [i18n] },
    })

    const labels = tabLabels(wrapper)
    expect(labels).toContain('Given')
    expect(labels).not.toContain('Given desktop')
  })
})
