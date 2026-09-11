// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * getContract is typed by the generated contract, and a wrong type fails the build (#16292).
 *
 * The assertions are checked by vue-tsc, whose tsconfig includes every .ts file under src. Each
 * `@ts-expect-error` below must meet a real error. If getContract accepted any
 * path, or returned `unknown`, a directive would go unused and the type-check
 * would fail, so these fail on a wrong type rather than merely compile.
 */

import { describe, it, expect, expectTypeOf } from 'vitest'
import type { GetPath, GetResponse } from '@autobot/ui'
import type { components, paths } from '@/types/generated/api'
import type { SlmApiClient } from './ApiClient'

type GpuNodes = components['schemas']['GPUNodeListResponse']

// Never called: its body exists for the type-checker only.
function contractTypeChecks(client: SlmApiClient) {
  // @ts-expect-error -- a path the contract does not declare
  void client.getContract('/api/no/such/route')
  // @ts-expect-error -- the contract's body is not a string
  const wrong: Promise<string> = client.getContract('/api/monitoring/gpu/nodes')
  const right: Promise<GpuNodes> = client.getContract('/api/monitoring/gpu/nodes')
  return [wrong, right]
}

describe('contract-typed GET (#16292)', () => {
  it('reads the response type from the contract', () => {
    expectTypeOf<GetResponse<paths, '/api/monitoring/gpu/nodes'>>().toEqualTypeOf<GpuNodes>()
    expectTypeOf<'/api/monitoring/gpu/nodes'>().toMatchTypeOf<GetPath<paths>>()
  })

  it('keeps the type checks compiled', () => {
    expect(typeof contractTypeChecks).toBe('function')
  })
})
