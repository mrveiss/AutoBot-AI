// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The "open this node" link contract (#14611).
 *
 * The inbound counterpart to `workflowDeepLink.ts`'s outbound `?workflow=<id>`
 * link (#13963): a canvas node link is `?node=<id>` and `OrgChart.vue` opens
 * whatever it names — panning/zooming the canvas to it and, for a real
 * org-chart member, opening the same sidebar a click on it would.
 *
 * Kept as a sibling module rather than folded into `workflowDeepLink.ts`: the
 * two name different query keys for different targets (a workflow vs. a
 * canvas node), and a shared parser would have to thread which one a caller
 * meant. Mirrors that module's shape exactly — one exported query key, one
 * exported parser — so a rename on either side stays a compile error rather
 * than a link that still looks specific and silently opens nothing.
 */

/** Query key naming the canvas node to focus. */
export const CANVAS_NODE_QUERY_KEY = 'node'

/**
 * A route query, typed permissively on purpose — see `workflowDeepLink.ts`'s
 * identical `QueryLike` for why: `vue-router`'s own `LocationQuery` is not
 * assignable to a re-declared lookalike, and this module stays free of a
 * router dependency either way.
 */
type QueryLike = Record<string, unknown>

/**
 * The canvas node a route query asks to focus, or null when it asks for none.
 *
 * `vue-router` types a repeated query parameter as an array (`?node=a&node=b`
 * arrives as `['a', 'b']`); taking the first is deliberate, matching
 * `workflowIdFromQuery` — focusing one node is the only sensible reading, and
 * throwing would break a link a user can produce by accident.
 */
export function canvasNodeIdFromQuery(query: QueryLike | undefined): string | null {
  const requested = query?.[CANVAS_NODE_QUERY_KEY]
  const value = Array.isArray(requested) ? requested[0] : requested
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  return trimmed.length > 0 ? trimmed : null
}

/**
 * Build the query object for a shareable link to `nodeId` on the canvas.
 *
 * A plain object rather than a full URL: every caller so far already has a
 * `RouteLocation`/`router.push` in hand (mirrors how `OrgChart.vue` builds the
 * outbound `{ [WORKFLOW_QUERY_KEY]: workflowId }` query for #13963) — building
 * a full URL here would mean owning origin/path assembly this module has no
 * business doing.
 */
export function canvasNodeLinkQuery(nodeId: string): Record<string, string> {
  return { [CANVAS_NODE_QUERY_KEY]: nodeId }
}
