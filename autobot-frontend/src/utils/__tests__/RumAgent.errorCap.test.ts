// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// RumAgent keeps only the latest RUM_MAX_ERRORS tracked errors (#21583): the retired ErrorHandler.js bounded its
// error log at 100 entries, and the live error log (RumAgent.metrics.errors) that replaced it must stay bounded too.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import rum from '@/utils/RumAgent'
import { RUM_MAX_API_CALLS, RUM_MAX_ERRORS } from '@/utils/rumBufferCap'

type Buffers = {
  metrics: { errors: Array<{ message?: string }> }
  pendingJsErrors: Array<{ error_type: string }>
  pendingCriticalIssues: unknown[]
  prometheusEnabled: boolean
}

const buffers = (): Buffers => rum as unknown as Buffers

describe('RumAgent.trackError buffers', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))
    rum.clear()
    buffers().pendingJsErrors = []
    buffers().pendingCriticalIssues = []
    buffers().prometheusEnabled = true
  })
  afterEach(() => {
    rum.stop()
    vi.unstubAllGlobals()
  })

  it('keeps the latest N tracked errors when N+1 are tracked', () => {
    for (let i = 0; i <= RUM_MAX_ERRORS; i++) rum.trackError('javascript_error', { message: `boom ${i}` })
    const kept = buffers().metrics.errors
    expect(kept).toHaveLength(RUM_MAX_ERRORS)
    expect(kept[0].message).toBe('boom 1')
    expect(kept[RUM_MAX_ERRORS - 1].message).toBe(`boom ${RUM_MAX_ERRORS}`)
  })

  it('bounds the unflushed JS-error metrics queue the same way', () => {
    for (let i = 0; i <= RUM_MAX_ERRORS; i++) rum.trackError('javascript_error', { message: `boom ${i}` })
    expect(buffers().pendingJsErrors).toHaveLength(RUM_MAX_ERRORS)
  })

  it('keeps every error while under the bound (control)', () => {
    rum.trackError('javascript_error', { message: 'one' })
    rum.trackError('vue_error', { message: 'two' })
    expect(buffers().metrics.errors.map(e => e.message)).toEqual(['one', 'two'])
    expect(buffers().pendingJsErrors.map(e => e.error_type)).toEqual(['javascript_error', 'vue_error'])
  })

  it('defaults to the retired error log bound, separate from the API-call bound', () => {
    expect(RUM_MAX_ERRORS).toBe(100)
    expect(RUM_MAX_API_CALLS).toBe(200)
  })
})
