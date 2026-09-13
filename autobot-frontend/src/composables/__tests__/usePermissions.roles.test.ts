// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The role map is keyed by the canonical backend vocabulary (#14937), and since
 * #16491 it is the backend's own grant map, generated.
 *
 * Before #14937, `operator`, `analyst`, `editor` and `superadmin` had no entry and
 * fell through to the `guest` set -- less than a plain `user` -- while `viewer`
 * and `guest` held entries for roles the backend does not have. Before #16491,
 * the three non-admin roles collapsed onto `user`'s hand-curated set.
 */

import { describe, it, expect, vi } from 'vitest'
import {
  getPermissionsForRole,
  ROLE_PERMISSIONS,
  UNAUTHENTICATED_PERMISSIONS,
} from '@/composables/usePermissions'

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ error: vi.fn(), info: vi.fn(), warn: vi.fn(), debug: vi.fn() }),
}))

describe('usePermissions role map (#14937, #16491)', () => {
  it.each(['operator', 'analyst', 'editor', 'user', 'readonly'] as const)(
    'gives %s its own backend set, not the signed-out one',
    (role) => {
      expect(getPermissionsForRole(role)).toBe(ROLE_PERMISSIONS[role])
      expect(getPermissionsForRole(role)).not.toEqual(UNAUTHENTICATED_PERMISSIONS)
    },
  )

  it.each(['operator', 'analyst', 'editor'] as const)('no longer collapses %s onto the user set', (role) => {
    expect(ROLE_PERMISSIONS[role]).not.toEqual(ROLE_PERMISSIONS.user)
  })

  it('gives superadmin the backend empty set -- admitted by the admin short-circuit, not by a grant (#13854)', () => {
    expect(getPermissionsForRole('superadmin')).toEqual([])
  })

  it('carries an entry for exactly the canonical roles -- no viewer, no guest', () => {
    expect(Object.keys(ROLE_PERMISSIONS).sort()).toEqual(
      ['admin', 'analyst', 'editor', 'operator', 'readonly', 'superadmin', 'user'],
    )
  })

  it.each([null, undefined, '', 'guest', 'viewer', 'nonsense'])(
    'gives %j the signed-out set -- an unknown role sees less, never more',
    (role) => {
      expect(getPermissionsForRole(role)).toBe(UNAUTHENTICATED_PERMISSIONS)
    },
  )

  it('reads roles case-insensitively, as is_admin_role() does', () => {
    expect(getPermissionsForRole('Operator')).toBe(ROLE_PERMISSIONS.operator)
  })
})
