// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #16244: meta.minRole was declared and read by no guard. These tests pin
// the guard's actual behavior -- a user below a route's minRole is
// redirected home, one at or above it is let through -- without mocking
// the whole router or user store, since resolveMinRoleRedirect is a pure
// function of (to, userRole).

import { describe, it, expect, vi } from 'vitest'
import type { RouteLocationNormalized, RouteRecordNormalized } from 'vue-router'

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get: vi.fn().mockResolvedValue([]) })
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ error: vi.fn(), info: vi.fn(), warn: vi.fn(), debug: vi.fn() })
}))

import { resolveMinRoleRedirect } from '@/router'

function toWithMinRole(minRole: string | undefined): RouteLocationNormalized {
  const matched = [
    { meta: minRole ? { minRole } : {} } as unknown as RouteRecordNormalized
  ]
  return { matched } as unknown as RouteLocationNormalized
}

describe('resolveMinRoleRedirect (#16244)', () => {
  it('redirects a user below the route minRole', () => {
    const to = toWithMinRole('operator')
    expect(resolveMinRoleRedirect(to, 'user')).toEqual({ path: '/home' })
  })

  it('allows a user exactly at the route minRole', () => {
    const to = toWithMinRole('operator')
    expect(resolveMinRoleRedirect(to, 'operator')).toBeNull()
  })

  it('allows a user above the route minRole', () => {
    const to = toWithMinRole('operator')
    expect(resolveMinRoleRedirect(to, 'admin')).toBeNull()
  })

  it('allows any authenticated user when the route sets no minRole', () => {
    const to = toWithMinRole(undefined)
    expect(resolveMinRoleRedirect(to, 'readonly')).toBeNull()
  })

  it('redirects a user with no role at all when the route sets a minRole', () => {
    const to = toWithMinRole('user')
    expect(resolveMinRoleRedirect(to, undefined)).toEqual({ path: '/home' })
  })

  it('applies the strictest minRole among nested matched records', () => {
    const to = {
      matched: [
        { meta: { minRole: 'user' } } as unknown as RouteRecordNormalized,
        { meta: { minRole: 'operator' } } as unknown as RouteRecordNormalized
      ]
    } as unknown as RouteLocationNormalized

    expect(resolveMinRoleRedirect(to, 'user')).toEqual({ path: '/home' })
    expect(resolveMinRoleRedirect(to, 'operator')).toBeNull()
  })
})
