// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The role map is keyed by the canonical backend vocabulary (#14937).
 *
 * Before this, `operator`, `analyst`, `editor` and `superadmin` had no entry and
 * fell through to the `guest` set -- less than a plain `user` -- while `viewer`
 * and `guest` held entries for roles the backend does not have.
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

describe('usePermissions role map (#14937)', () => {
  it.each(['operator', 'analyst', 'editor'])('gives %s the user set, not the signed-out one', (role) => {
    expect(getPermissionsForRole(role)).toEqual(ROLE_PERMISSIONS.user)
    expect(getPermissionsForRole(role)).not.toEqual(UNAUTHENTICATED_PERMISSIONS)
  })

  it('maps superadmin like admin', () => {
    expect(getPermissionsForRole('superadmin')).toEqual(ROLE_PERMISSIONS.admin)
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
    expect(getPermissionsForRole('Operator')).toEqual(ROLE_PERMISSIONS.user)
  })
})
