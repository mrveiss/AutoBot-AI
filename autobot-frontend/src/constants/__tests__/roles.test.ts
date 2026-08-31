// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
import { describe, it, expect } from 'vitest'
import { isAdminRole, ADMIN_ROLES } from '../roles'

describe('isAdminRole (#14937)', () => {
  it('admits admin', () => {
    expect(isAdminRole('admin')).toBe(true)
  })

  it('admits superadmin — the bug #14937 was filed for', () => {
    expect(isAdminRole('superadmin')).toBe(true)
  })

  it('is case-insensitive', () => {
    expect(isAdminRole('SuperAdmin')).toBe(true)
    expect(isAdminRole('ADMIN')).toBe(true)
  })

  it('rejects every non-administrative role', () => {
    for (const role of ['operator', 'analyst', 'editor', 'user', 'readonly', 'viewer', 'guest']) {
      expect(isAdminRole(role)).toBe(false)
    }
  })

  it('fails safe on missing/empty role', () => {
    expect(isAdminRole(null)).toBe(false)
    expect(isAdminRole(undefined)).toBe(false)
    expect(isAdminRole('')).toBe(false)
  })

  it('ADMIN_ROLES holds exactly admin and superadmin', () => {
    expect([...ADMIN_ROLES].sort()).toEqual(['admin', 'superadmin'])
  })
})
