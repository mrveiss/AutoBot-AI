// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * The `GET /browser/mcp/status` contract, in one place (#15228).
 *
 * `BrowserTool.vue` read `data.status` and compared it against `'connected'`
 * or `'ready'`. Both halves were wrong and independently fatal: the route has
 * no top-level `status` (it is nested under `browser_vm`), and the server's
 * vocabulary — `healthy` / `degraded` / `unavailable` — shares no value with
 * the two the client tested. The indicator could therefore never read
 * connected, whatever the browser VM was doing.
 *
 * The mapping is explicit and total: every server value names the client state
 * it means. An unrecognised or missing value is `'unknown'`, which is NOT
 * `'disconnected'` — "the VM says it is down" and "we could not tell" are
 * different things to show an operator, and collapsing them is how the first
 * defect stayed invisible.
 *
 * The producing side is `autobot-backend/api/browser_mcp.py`
 * (`browser_mcp_status`); `tests/unit/api/test_browser_status_contract.py`
 * fails if either side's field name or vocabulary moves without the other.
 */

/** The field the route nests the VM's state under. */
export const BROWSER_VM_FIELD = 'browser_vm'

/** Every value `browser_vm.status` can carry, mapped to what the UI shows. */
export const BROWSER_VM_STATUS_MAP = {
  healthy: 'connected',
  degraded: 'degraded',
  unavailable: 'disconnected',
} as const

export type BrowserVmStatus = keyof typeof BROWSER_VM_STATUS_MAP
export type BrowserUiStatus = (typeof BROWSER_VM_STATUS_MAP)[BrowserVmStatus] | 'unknown' | 'connecting'

/**
 * Read the browser VM's state out of a `/browser/mcp/status` body.
 *
 * @param body - the parsed response, or anything at all — this is a contract
 *   boundary, so it validates rather than assumes.
 * @returns the UI state, or `'unknown'` when the field is absent or carries a
 *   value this client does not know. Never guesses `'disconnected'`.
 */
export function readBrowserVmStatus(body: unknown): BrowserUiStatus {
  if (typeof body !== 'object' || body === null) return 'unknown'
  const vm = (body as Record<string, unknown>)[BROWSER_VM_FIELD]
  if (typeof vm !== 'object' || vm === null) return 'unknown'
  const status = (vm as Record<string, unknown>).status
  if (typeof status !== 'string') return 'unknown'
  return BROWSER_VM_STATUS_MAP[status as BrowserVmStatus] ?? 'unknown'
}

/** Where fleet membership came from, so a degraded answer is never shown as live. */
export function readFleetMembershipSource(body: unknown): string | null {
  if (typeof body !== 'object' || body === null) return null
  const security = (body as Record<string, unknown>).security
  if (typeof security !== 'object' || security === null) return null
  const source = (security as Record<string, unknown>).fleet_membership_source
  return typeof source === 'string' ? source : null
}
