// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
import { describe, it, expect } from 'vitest'
import { isAdminRole, ADMIN_ROLES, ROLE_RANK, meetsMinRole } from '../roles'

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

describe('ROLE_RANK / meetsMinRole (#16244)', () => {
  it('ranks superadmin above admin, mirroring the backend _ROLE_META comment', () => {
    expect(ROLE_RANK.superadmin).toBeGreaterThan(ROLE_RANK.admin)
  })

  it('matches the backend _ROLE_META ordering exactly', () => {
    expect(ROLE_RANK).toEqual({
      superadmin: 110,
      admin: 100,
      operator: 80,
      analyst: 60,
      editor: 55,
      user: 50,
      readonly: 10
    })
  })

  it('meetsMinRole admits a role above the floor', () => {
    expect(meetsMinRole('admin', 'operator')).toBe(true)
  })

  it('meetsMinRole admits a role exactly at the floor', () => {
    expect(meetsMinRole('operator', 'operator')).toBe(true)
  })

  it('meetsMinRole rejects a role below the floor', () => {
    expect(meetsMinRole('user', 'operator')).toBe(false)
  })

  it('meetsMinRole fails safe on missing/unknown role', () => {
    expect(meetsMinRole(null, 'readonly')).toBe(false)
    expect(meetsMinRole(undefined, 'readonly')).toBe(false)
    expect(meetsMinRole('not-a-real-role', 'readonly')).toBe(false)
  })
})
