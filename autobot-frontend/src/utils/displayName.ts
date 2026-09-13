// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The render-time display-name rule for a user object (#14939).
 *
 * Mirrors `UserCore.full_name` on the backend: `display_name`, then `username`.
 * The last rung -- the user id, for a membership whose user row is gone -- is
 * owned by the server (`resolve_display_name` in `list_members` and
 * `_compose_human_nodes`), so it is not re-implemented here. `fallback` is for
 * the callers that hold an id but may get no user object back at all.
 */

export interface NamedUser {
  display_name?: string | null
  username?: string | null
}

export function displayNameOf(user: NamedUser | null | undefined, fallback = ''): string {
  return user?.display_name || user?.username || fallback
}
