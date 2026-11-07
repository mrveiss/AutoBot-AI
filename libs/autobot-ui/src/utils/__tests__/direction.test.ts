// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// resolveDirection (#14779, #20382): an explicit `dir` wins; otherwise the result follows
// html[dir], including a change made after the reader was first evaluated.

import { describe, it, expect, afterEach } from 'vitest'
import { computed } from 'vue'
import { resolveDirection } from '../direction'

const settle = () => new Promise((resolve) => setTimeout(resolve, 0))

afterEach(() => document.documentElement.removeAttribute('dir'))

describe('resolveDirection', () => {
  it('prefers the explicit dir', () => {
    document.documentElement.dir = 'rtl'
    expect(resolveDirection('ltr')).toBe('ltr')
  })

  it('reads html[dir] when no dir is passed', () => {
    document.documentElement.dir = 'rtl'
    expect(resolveDirection()).toBe('rtl')
  })

  it('a computed re-evaluates when html[dir] changes after it was first read', async () => {
    const direction = computed(() => resolveDirection())
    expect(direction.value).toBe('ltr')
    document.documentElement.dir = 'rtl'
    await settle()
    expect(direction.value).toBe('rtl')
    document.documentElement.dir = 'ltr'
    await settle()
    expect(direction.value).toBe('ltr')
  })
})
