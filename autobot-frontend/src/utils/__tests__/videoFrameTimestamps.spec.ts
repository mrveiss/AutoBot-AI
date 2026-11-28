// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest'
import { calculateFrameTimestamps } from '../videoFrameTimestamps'

describe('calculateFrameTimestamps', () => {
  it('samples every interval seconds', () => {
    expect(calculateFrameTimestamps('interval', 6, 2, 10)).toEqual([0, 2, 4])
  })

  it('samples the start, quarters and the point before the end for keyframes', () => {
    expect(calculateFrameTimestamps('keyframes', 8, 2, 10)).toEqual([0, 2, 4, 6])
  })

  it('samples every half second for all, capped at maxFrames', () => {
    expect(calculateFrameTimestamps('all', 3, 2, 4)).toEqual([0, 0.5, 1, 1.5])
  })
})
