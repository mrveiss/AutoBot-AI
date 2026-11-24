// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/** #22191: the desktop viewer shows a localised state, not a broken iframe, when the desktop VM is not available. */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/ApiClient', () => ({ default: { call: vi.fn() } }))
import ApiClient from '@/utils/ApiClient'

const call = vi.mocked(ApiClient.call) as unknown as ReturnType<typeof vi.fn>

import { desktopVmBlockedKey } from '../useDesktopVm'

describe('desktopVmBlockedKey', () => {
  // Braces matter: `() => call.mockReset()` RETURNS the mock, and vitest runs a function returned from a hook as
  // its teardown, so the mock was called again after the test and its rejection failed the test (#22191).
  beforeEach(() => {
    call.mockReset()
  })

  it('is null when a desktop node is registered (the viewer may load)', async () => {
    call.mockResolvedValue({ host: 'desk.example.test', port: 6090 })
    expect(await desktopVmBlockedKey()).toBeNull()
  })

  it('names desktop_vm_unavailable when no node is registered', async () => {
    call.mockResolvedValue(null)
    expect(await desktopVmBlockedKey()).toBe('desktop.interface.desktopVmUnavailable')
  })

  it('names the registry state when the registry cannot be read', async () => {
    call.mockRejectedValue(new Error('503'))
    expect(await desktopVmBlockedKey()).toBe('desktop.interface.registryUnavailable')
  })
})
