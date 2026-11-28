// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * KnowledgeGraph3D's static layout is a still picture (#18694): the layout is
 * computed up front and frozen, and no link particle keeps moving after it, so
 * two screenshots of the same story match. The animated layout keeps them.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const calls: Array<[string, unknown[]]> = []

vi.mock('3d-force-graph', () => ({
  default: class {
    constructor() {
      const proxy: object = new Proxy(this, {
        get: (_target, name) => (...args: unknown[]) => {
          calls.push([String(name), args])
          return proxy
        },
      })
      return proxy
    }
  },
}))
vi.mock('three-spritetext', () => ({ default: class { position = { y: 0 } } }))
vi.mock('three', () => ({ Texture: class {} }))

import KnowledgeGraph3D from '../KnowledgeGraph3D.vue'

const entities = [
  { id: 'a', name: 'A', type: 'concept', observations: [] },
  { id: 'b', name: 'B', type: 'concept', observations: [] },
]
const edges = [{ from: 'a', to: 'b', type: 'relates_to' }]

function argsOf(method: string): unknown[] | undefined {
  return calls.find(([name]) => name === method)?.[1]
}

async function render(staticLayout: boolean): Promise<void> {
  mount(KnowledgeGraph3D, {
    props: { entities, edges, staticLayout },
    global: { mocks: { $t: (key: string) => key }, stubs: { Icon: true } },
  })
  await flushPromises()
}

describe('KnowledgeGraph3D link particles', () => {
  beforeEach(() => {
    calls.length = 0
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('draws no link particles in a static layout', async () => {
    await render(true)
    expect(argsOf('cooldownTicks')).toEqual([0])
    expect(argsOf('linkDirectionalParticles')).toEqual([0])
  })

  it('keeps the link particles in the animated layout', async () => {
    await render(false)
    expect(argsOf('cooldownTicks')).toEqual([Infinity])
    expect(argsOf('linkDirectionalParticles')).toEqual([1])
  })
})
