// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Canonical admin-role predicate (#14937).
 *
 * `autobot_shared/auth/permissions.py::is_admin_role()` is the backend source
 * of truth: a role is administrative when it is `admin` OR `superadmin`.
 * `superadmin` carries no granular ROLE_PERMISSIONS entries by design — it is
 * an administrative *predicate*, not a permission grant — so a hand-rolled
 * `role === 'admin'` check on the frontend silently rejects it. That bug
 * class was fixed on the backend by `is_admin_role()`; this is the frontend
 * equivalent, so there is exactly one place that answers "is this role an
 * administrator" instead of a per-file `=== 'admin'` comparison.
 *
 * Both lists below are checked against the generated canonical `Role` (#14937):
 * a member the backend vocabulary does not carry fails to compile.
 */

import type { Role } from '@/types/_generated/workflow'

export const ADMIN_ROLES = ['admin', 'superadmin'] as const satisfies readonly Role[]

export type AdminRole = (typeof ADMIN_ROLES)[number]

/**
 * The roles an administrator may assign in the UI (#14937). The owner kept this to
 * admin/user/readonly: `set_user_role` is guarded by `require_platform_admin`, so
 * offering `superadmin` would let an admin grant a role above their own. The
 * backend's `RoleUpdateRequest` pattern accepts the same three.
 */
export const ASSIGNABLE_ROLES = ['admin', 'user', 'readonly'] as const satisfies readonly Role[]

/** The role a user record without one is treated as -- the least-privileged named role an account is created with. */
export const DEFAULT_ROLE: Role = 'user'

export function isAssignableRole(role: string): boolean {
  return (ASSIGNABLE_ROLES as readonly string[]).includes(role)
}

/** Mirrors `is_admin_role()` — true for every administrative role, case-insensitively. */
export function isAdminRole(role: string | null | undefined): boolean {
  if (!role) return false
  return (ADMIN_ROLES as readonly string[]).includes(role.toLowerCase())
}

/**
 * Role rank, mirroring the backend's authoritative ordering in
 * `autobot_shared/auth/permissions.py::_ROLE_META` (#16244). `superadmin`
 * ranks above `admin` for the same reason `_ROLE_META`'s own comment gives:
 * it is administrative at every gate that admits `admin`, and a lower rank
 * here would sort the most privileged role below `readonly`.
 *
 * UI ROUTING ONLY — this never grants access the backend refuses. It backs
 * `meta.minRole`'s router guard alone; every actual permission decision
 * still goes through the backend's own gates.
 */
export const ROLE_RANK: Record<Role, number> = {
  superadmin: 110,
  admin: 100,
  operator: 80,
  analyst: 60,
  editor: 55,
  user: 50,
  readonly: 10
} as const satisfies Record<Role, number>

/** True when `role` meets or exceeds `minRole` in the ranking above. Unknown/missing `role` never meets any `minRole`. */
export function meetsMinRole(role: string | null | undefined, minRole: Role): boolean {
  if (!role || !(role in ROLE_RANK)) return false
  return ROLE_RANK[role as Role] >= ROLE_RANK[minRole]
}
