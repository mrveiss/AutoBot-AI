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
  beforeEach(() => call.mockReset())

  it('is null when a desktop node is registered (the viewer may load)', async () => {
    call.mockResolvedValue({ host: 'desk.example.test', port: 6090 })
    expect(await desktopVmBlockedKey()).toBeNull()
  })

  it('names desktop_vm_unavailable when no node is registered', async () => {
    call.mockResolvedValue(null)
    expect(await desktopVmBlockedKey()).toBe('desktop.interface.desktopVmUnavailable')
  })
})
