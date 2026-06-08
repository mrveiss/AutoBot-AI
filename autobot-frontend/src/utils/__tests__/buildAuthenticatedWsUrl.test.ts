// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { describe, it, expect, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { buildAuthenticatedWsUrl } from '@/utils/buildAuthenticatedWsUrl'
import { useUserStore } from '@/stores/useUserStore'

describe('buildAuthenticatedWsUrl', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('returns null when no token is present', () => {
    expect(buildAuthenticatedWsUrl('ws://localhost/api/ws/live')).toBeNull()
  })

  it('appends ?token= when URL has no query string', () => {
    const store = useUserStore()
    store.authState.token = 'jwt-abc'
    expect(buildAuthenticatedWsUrl('ws://localhost/api/ws/live')).toBe(
      'ws://localhost/api/ws/live?token=jwt-abc'
    )
  })

  it('appends &token= when URL already has a query string', () => {
    const store = useUserStore()
    store.authState.token = 'jwt-abc'
    expect(buildAuthenticatedWsUrl('ws://localhost/api/ws/live?room=42')).toBe(
      'ws://localhost/api/ws/live?room=42&token=jwt-abc'
    )
  })

  it('URL-encodes tokens with reserved characters', () => {
    const store = useUserStore()
    store.authState.token = 'jwt+with/special=chars'
    expect(buildAuthenticatedWsUrl('ws://localhost/api/ws/live')).toBe(
      'ws://localhost/api/ws/live?token=jwt%2Bwith%2Fspecial%3Dchars'
    )
  })

  it('returns null for empty-string token (treated as no auth)', () => {
    const store = useUserStore()
    store.authState.token = ''
    expect(buildAuthenticatedWsUrl('ws://localhost/api/ws/live')).toBeNull()
  })
})
