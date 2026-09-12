// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #16243: usePermissions.ts hand-rolled its own `users:read`-style vocabulary
 * that shared nothing with the backend's real `Permission` strings
 * (`admin.users.read`-style, from `autobot_shared/auth/permissions.py`, now
 * generated into `@/types/_generated/workflow`). These tests pin the new
 * vocabulary so it can't silently drift back to an invented one -- the class
 * of bug this issue is about.
 */

import { describe, it, expect, vi } from 'vitest'

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ error: vi.fn(), info: vi.fn(), warn: vi.fn(), debug: vi.fn() })
}))

import { getPermissionsForRole, ROLE_PERMISSIONS, UNAUTHENTICATED_PERMISSIONS } from '@/composables/usePermissions'
import type { Permission } from '@/types/_generated/workflow'

/** Every real Permission value uses '.', or is the one legacy exception. */
const REAL_PERMISSION_SHAPE = /^[a-z_]+(\.[a-z_]+)*$/

describe('usePermissions vocabulary (#16243)', () => {
  it('every admin permission is a real dot-separated backend Permission, not the old colon vocabulary', () => {
    for (const permission of ROLE_PERMISSIONS.admin) {
      expect(permission).not.toContain(':')
      expect(permission).toMatch(REAL_PERMISSION_SHAPE)
    }
  })

  it('every role set uses only real Permission values', () => {
    const roles = Object.keys(ROLE_PERMISSIONS) as (keyof typeof ROLE_PERMISSIONS)[]
    for (const role of roles) {
      for (const permission of ROLE_PERMISSIONS[role]) {
        expect(permission).not.toContain(':')
      }
    }
  })

  it('the unauthenticated set uses real Permission values too', () => {
    for (const permission of UNAUTHENTICATED_PERMISSIONS) {
      expect(permission).not.toContain(':')
    }
  })

  it('drops the categories the backend has no Permission for (chat/teams/settings/audit)', () => {
    const all = [...ROLE_PERMISSIONS.admin, ...ROLE_PERMISSIONS.user, ...UNAUTHENTICATED_PERMISSIONS]
    for (const dropped of ['chat.use', 'chat.history', 'teams.read', 'settings.read', 'audit.read']) {
      expect(all).not.toContain(dropped as Permission)
    }
  })

  it('a real backend permission (admin.system) resolves for admin but not for user', () => {
    expect(getPermissionsForRole('admin')).toContain('admin.system')
    expect(getPermissionsForRole('user')).not.toContain('admin.system')
  })
})
