// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #20631: `/setup` is admin only. A fresh install seeds the `admin` user as a platform admin
 * (autobot-slm-backend/main.py `_ensure_admin_user`), so the wizard stays reachable, and the
 * first-run redirect it triggers must not loop. This file owns its own router module because
 * the wizard check runs once per module load.
 */

import { describe, it, expect, vi } from 'vitest'

const auth = vi.hoisted(() => ({ isAuthenticated: true, isAdmin: true, checkAuth: async () => true }))
const statusGet = vi.hoisted(() => vi.fn(async () => ({ completed: false })))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))
vi.mock('@/utils/ApiClient', () => ({ default: { get: statusGet } }))

import router from './index'

describe('the setup wizard behind the admin guard', () => {
  it('sends a non-admin on /setup to sign-in with the reason, without looping', async () => {
    router.getRoutes().forEach((route) => {
      if (route.components) route.components.default = { render: () => null }
    })
    auth.isAdmin = false
    await router.push('/setup')
    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.error).toBe('admin_only')
    expect(statusGet).not.toHaveBeenCalled() // refused before the wizard check
  })

  it('lets an admin reach /setup', async () => {
    auth.isAdmin = true
    await router.push('/setup')
    expect(router.currentRoute.value.name).toBe('setup')
    expect(statusGet).not.toHaveBeenCalled() // the check skips /setup itself
  })

  it('the first-run redirect for an admin lands on /setup once and does not loop', async () => {
    await router.push('/fleet/nodes') // first guarded visit asks the wizard, which is not complete
    expect(statusGet).toHaveBeenCalledTimes(1)
    expect(router.currentRoute.value.name).toBe('setup')
    await router.push('/fleet/nodes') // asked once per session: now the admin may leave
    expect(router.currentRoute.value.name).toBe('fleet')
    expect(statusGet).toHaveBeenCalledTimes(1)
  })
})
