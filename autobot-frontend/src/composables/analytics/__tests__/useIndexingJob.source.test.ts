// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest'
import { jobBelongsToSource } from '../indexingJobSource'

describe('jobBelongsToSource (#20491)', () => {
  it('refuses a job on another source', () => {
    expect(jobBelongsToSource('atlas', 'autobot')).toBe(false)
  })

  it('accepts a job on the selected source', () => {
    expect(jobBelongsToSource('autobot', 'autobot')).toBe(true)
  })

  it('accepts what it cannot tell apart', () => {
    expect(jobBelongsToSource(null, 'autobot')).toBe(true)
    expect(jobBelongsToSource(undefined, 'autobot')).toBe(true)
    expect(jobBelongsToSource('atlas', undefined)).toBe(true)
  })
})
