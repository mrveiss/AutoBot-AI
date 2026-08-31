// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The "open this workflow" link contract (#13963).
 *
 * A process node on the Company OS org canvas links into the automation module
 * with `?workflow=<id>`, and `WorkflowBuilderView` opens whatever it names.
 * Producer and consumer therefore share one definition of the key and one
 * parser — if they each carried their own, a rename on one side would leave a
 * link that still looks specific and silently opens nothing.
 */

/** Query key naming the workflow to open. */
export const WORKFLOW_QUERY_KEY = 'workflow'

/**
 * A route query, typed permissively on purpose.
 *
 * `vue-router`'s own `LocationQuery` is `Record<string, string | null | (string
 * | null)[]>`. Re-declaring that shape here produced a lookalike that
 * `LocationQuery` was *not* assignable to, so the caller failed to typecheck
 * against a copy of the type it already had. Accepting a supertype and
 * narrowing below keeps this module free of a router dependency without
 * forking the router's definition.
 */
type QueryLike = Record<string, unknown>

/**
 * The workflow a route query asks for, or null when it asks for none.
 *
 * `vue-router` types a repeated query parameter as an array, so `?workflow=a&
 * workflow=b` arrives as `['a', 'b']`. Taking the first is deliberate: opening
 * one workflow is the only sensible reading, and throwing would break a link a
 * user can produce by accident.
 */
export function workflowIdFromQuery(query: QueryLike | undefined): string | null {
  const requested = query?.[WORKFLOW_QUERY_KEY]
  const value = Array.isArray(requested) ? requested[0] : requested
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  return trimmed.length > 0 ? trimmed : null
}
