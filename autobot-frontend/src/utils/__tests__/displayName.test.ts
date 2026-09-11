// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The frontend half of the display-name ladder (#14939). The backend owns the
 * user-id rung; this pins that the client's two rungs match `UserCore.full_name`
 * and that an empty display name is treated as absent, as the SQL form
 * `coalesce(nullif(display_name, ''), username)` treats it.
 */

import { describe, it, expect } from 'vitest'
import { displayNameOf } from '@/utils/displayName'

describe('displayNameOf (#14939)', () => {
  it('prefers the display name', () => {
    expect(displayNameOf({ display_name: 'Ada Lovelace', username: 'ada' })).toBe('Ada Lovelace')
  })

  it('falls back to the username when the display name is null or empty', () => {
    expect(displayNameOf({ display_name: null, username: 'ada' })).toBe('ada')
    expect(displayNameOf({ display_name: '', username: 'ada' })).toBe('ada')
  })

  it('uses the caller fallback only when the user carries neither name', () => {
    expect(displayNameOf({ display_name: null, username: null }, 'user-42')).toBe('user-42')
    expect(displayNameOf(null, 'user-42')).toBe('user-42')
  })

  it('never reaches for an email -- the rung ShareKnowledgeDialog used to add', () => {
    const user = { display_name: null, username: 'ada', email: 'ada@example.com' }
    expect(displayNameOf(user, 'user-42')).toBe('ada')
  })
})
