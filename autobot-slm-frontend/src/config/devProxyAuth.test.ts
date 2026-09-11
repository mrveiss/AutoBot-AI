// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #16382/#16385: truth table for the dev-proxy internal-API-key opt-in.
 *
 * `shouldInjectInternalApiKey()` gates whether the dev server's
 * `/autobot-api` proxy attaches `X-Internal-API-Key` — an unconditional
 * backend-admin credential — to every proxied request. It must default OFF
 * and require BOTH env vars to be set, not just one, since the dev server
 * binds to 0.0.0.0 (see `vite.config.ts`).
 */

import { describe, it, expect } from 'vitest'
import { shouldInjectInternalApiKey } from './devProxyAuth'

describe('shouldInjectInternalApiKey', () => {
  it.each([
    // [optIn, apiKey, expected, description]
    [undefined, undefined, false, 'neither var set'],
    ['true', undefined, false, 'opt-in set but no key'],
    [undefined, 'secret-key', false, 'key set but no opt-in'],
    ['false', 'secret-key', false, 'opt-in explicitly false'],
    ['TRUE', 'secret-key', false, 'opt-in wrong case is not "true"'],
    ['true', '', false, 'opt-in set but key is empty string'],
    ['true', 'secret-key', true, 'both vars set correctly'],
  ] as const)('%s / %s -> %s (%s)', (optIn, apiKey, expected) => {
    const env: NodeJS.ProcessEnv = {}
    if (optIn !== undefined) env.AUTOBOT_DEV_INJECT_INTERNAL_API_KEY = optIn
    if (apiKey !== undefined) env.AUTOBOT_INTERNAL_API_KEY = apiKey

    expect(shouldInjectInternalApiKey(env)).toBe(expected)
  })
})
