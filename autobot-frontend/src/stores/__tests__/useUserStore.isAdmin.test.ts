// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useUserStore, type UserProfile } from '../useUserStore'

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ error: vi.fn(), info: vi.fn(), warn: vi.fn(), debug: vi.fn() }),
}))

const mockUser = (role: UserProfile['role']): UserProfile => ({
  id: 'user-1',
  username: 'someone',
  displayName: 'Someone',
  role,
  preferences: {
    theme: 'auto',
    language: 'en',
    timezone: 'UTC',
    notifications: { email: true, browser: true, sound: true },
    ui: { sidebarCollapsed: false, compactMode: false, showTooltips: true, animationsEnabled: true },
    accessibility: {
      highContrast: false,
      reducedMotion: false,
      fontSize: 'medium',
      keyboardNavigation: false,
    },
    chat: { autoSave: true, messageHistory: 100, typingIndicators: true, timestamps: true },
  },
  createdAt: new Date(),
})

describe('useUserStore.isAdmin (#14937)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('admits admin', () => {
    const store = useUserStore()
    store.currentUser = mockUser('admin')
    expect(store.isAdmin).toBe(true)
  })

  it('admits superadmin — a hand-rolled === "admin" check previously rejected this', () => {
    const store = useUserStore()
    store.currentUser = mockUser('superadmin')
    expect(store.isAdmin).toBe(true)
  })

  it('rejects a non-administrative role', () => {
    const store = useUserStore()
    store.currentUser = mockUser('user')
    expect(store.isAdmin).toBe(false)
  })

  it('rejects when no user is set', () => {
    const store = useUserStore()
    store.currentUser = null
    expect(store.isAdmin).toBe(false)
  })

  it('does not grant hasServiceManagement to superadmin — its ROLE_PERMISSIONS entry is empty by backend design', () => {
    const store = useUserStore()
    store.currentUser = mockUser('superadmin')
    expect(store.hasServiceManagement).toBe(false)
  })
})
