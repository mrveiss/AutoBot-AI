// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi } from 'vitest'

const post = vi.fn()
vi.mock('@/utils/ApiClient', () => ({ default: { post } }))
vi.mock('@/config/ssot-config', () => ({ getApiBase: () => '/api' }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() })
}))

import { useCommandPermissions } from '../useCommandPermissions'

describe('approveOrDeny on a decided approval (#19951)', () => {
  it('turns the 409 into the stale "No pending approval" answer the dialog already handles', async () => {
    post.mockRejectedValue({ status: 409 })
    const { approveOrDeny } = useCommandPermissions()
    expect(await approveOrDeny('sess-1', true)).toEqual({ status: 'error', error: 'No pending approval' })
  })

  it('still throws any other failure (#21174)', async () => {
    post.mockRejectedValue(new Error('network'))
    const { approveOrDeny } = useCommandPermissions()
    await expect(approveOrDeny('sess-1', false)).rejects.toThrow('network')
  })
})
