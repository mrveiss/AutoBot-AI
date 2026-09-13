// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest'
import {
  BROWSER_VM_FIELD,
  BROWSER_VM_STATUS_MAP,
  readBrowserVmStatus,
  readFleetMembershipSource,
} from './browserVmStatus'

/**
 * The status contract with `GET /browser/mcp/status` (#15228).
 *
 * The defect had two independent halves, and a test that only asserted "the
 * call succeeds" passed through both: the client read a top-level `status`
 * the route does not send, and compared it against `'connected'` / `'ready'`,
 * two values the server's vocabulary does not contain. Either alone made the
 * indicator permanently red. These pin both.
 */
describe('readBrowserVmStatus', () => {
  it('reads the nested field the route actually sends', () => {
    expect(readBrowserVmStatus({ success: true, browser_vm: { status: 'healthy' } })).toBe('connected')
  })

  it('ignores a top-level status — the route has none, so trusting one is the bug', () => {
    // This body is exactly what the old client thought it was getting.
    expect(readBrowserVmStatus({ status: 'connected' })).toBe('unknown')
    expect(readBrowserVmStatus({ status: 'ready' })).toBe('unknown')
  })

  it('maps every value the server can send, and only those', () => {
    expect(Object.keys(BROWSER_VM_STATUS_MAP).sort()).toEqual(['degraded', 'healthy', 'unavailable'])
    expect(readBrowserVmStatus({ browser_vm: { status: 'degraded' } })).toBe('degraded')
    expect(readBrowserVmStatus({ browser_vm: { status: 'unavailable' } })).toBe('disconnected')
  })

  it('does not accept the vocabulary the old client tested for', () => {
    // 'connected'/'ready' are UI words. If the server ever sends them the
    // mapping must be updated deliberately, not absorbed silently.
    expect(readBrowserVmStatus({ browser_vm: { status: 'connected' } })).toBe('unknown')
    expect(readBrowserVmStatus({ browser_vm: { status: 'ready' } })).toBe('unknown')
  })

  it('distinguishes "cannot tell" from "the VM is down"', () => {
    // The vacuity probe: an absent field must NOT read as a falsy/disconnected
    // state, or a renamed field would look exactly like a healthy report of a
    // dead VM and nothing here would fail.
    expect(readBrowserVmStatus({ browser_vm: {} })).toBe('unknown')
    expect(readBrowserVmStatus({})).toBe('unknown')
    expect(readBrowserVmStatus(null)).toBe('unknown')
    expect(readBrowserVmStatus(undefined)).toBe('unknown')
    expect(readBrowserVmStatus('healthy')).toBe('unknown')
    expect(readBrowserVmStatus({ browser_vm: { status: 42 } })).toBe('unknown')
    expect(readBrowserVmStatus({ browser_vm: { status: 'unavailable' } })).not.toBe('unknown')
  })

  it('names the field it depends on, so a rename is a one-line change here', () => {
    expect(BROWSER_VM_FIELD).toBe('browser_vm')
  })
})

describe('readFleetMembershipSource', () => {
  it('reports the source the backend declares', () => {
    expect(readFleetMembershipSource({ security: { fleet_membership_source: 'slm_node_registry' } })).toBe(
      'slm_node_registry',
    )
    expect(readFleetMembershipSource({ security: { fleet_membership_source: 'ssot_fallback' } })).toBe('ssot_fallback')
  })

  it('returns null rather than guessing when the backend says nothing', () => {
    expect(readFleetMembershipSource({ security: {} })).toBeNull()
    expect(readFleetMembershipSource({})).toBeNull()
    expect(readFleetMembershipSource(null)).toBeNull()
  })
})
