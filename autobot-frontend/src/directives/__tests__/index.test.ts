// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #16243: registerDirectives() existed but had zero callers -- v-permission
 * was defined, tested in isolation (permission.adminRoles.test.ts mounts it
 * directly via withDirectives), but never actually registered on the real
 * app, so `v-permission="..."` in a real template would have been a no-op.
 * main.ts now calls this on startup; this test pins what that call does.
 */

import { describe, it, expect, vi } from 'vitest'
import type { App } from 'vue'
import { registerDirectives } from '@/directives'
import { vPermission } from '@/directives/permission'

describe('registerDirectives (#16243)', () => {
  it('registers v-permission on the app', () => {
    const directive = vi.fn()
    const app = { directive } as unknown as App

    registerDirectives(app)

    expect(directive).toHaveBeenCalledWith('permission', vPermission)
  })
})
