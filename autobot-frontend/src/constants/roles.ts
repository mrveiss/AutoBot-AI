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
 * Deliberately narrow: this file does not attempt the full role-vocabulary
 * unification #14937 asks for (three more drifted unions, i18n for
 * `superadmin` assignment, the `viewer`/`guest` cleanup) — those are separate,
 * larger slices with their own review surface.
 */

export const ADMIN_ROLES = ['admin', 'superadmin'] as const

export type AdminRole = (typeof ADMIN_ROLES)[number]

/** Mirrors `is_admin_role()` — true for every administrative role, case-insensitively. */
export function isAdminRole(role: string | null | undefined): boolean {
  if (!role) return false
  return (ADMIN_ROLES as readonly string[]).includes(role.toLowerCase())
}
