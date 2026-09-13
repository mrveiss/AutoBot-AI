// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * `getSlmApiBase()` pinning (#15761).
 *
 * `getApiUrl()` in `stores/auth.ts` used to diverge from `getSlmApiBase()` in
 * DEV: it hard-returned `''` regardless of `VITE_API_URL`, while
 * `getSlmApiBase()` honoured it. They agreed only because the SLM `dev`
 * script happens to set no `VITE_API_URL` -- an incidental property of one
 * script, not a guarantee (#13140). `getApiUrl()` is now retired; these tests
 * pin `getSlmApiBase()`'s own resolution so a second resolver cannot silently
 * reintroduce the same divergence without a test noticing.
 */

import { describe, it, expect, afterEach } from 'vitest'
import config, { getSlmApiBase } from './ssot-config'

describe('getSlmApiBase (#15761)', () => {
  const originalApiBaseUrl = config.apiBaseUrl

  afterEach(() => {
    config.apiBaseUrl = originalApiBaseUrl
  })

  it('resolves the standalone base when no VITE_API_URL is set', () => {
    config.apiBaseUrl = ''

    expect(getSlmApiBase()).toBe('/api')
  })

  it('resolves the co-located base when VITE_API_URL is set, exactly as it would be with VITE_API_URL=/slm', () => {
    config.apiBaseUrl = '/slm'

    expect(getSlmApiBase()).toBe('/slm/api')
  })

  it('re-reads config.apiBaseUrl on every call, so a later env change is not cached', () => {
    config.apiBaseUrl = ''
    expect(getSlmApiBase()).toBe('/api')

    config.apiBaseUrl = '/slm'
    expect(getSlmApiBase()).toBe('/slm/api')
  })
})
