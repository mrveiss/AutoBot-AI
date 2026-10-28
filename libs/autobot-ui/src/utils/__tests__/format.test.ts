// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest'
import { formatDuration, formatFileSize } from '../format'

describe('formatDuration msCompound (#19680)', () => {
  it('walks seconds, minutes and hours from milliseconds', () => {
    expect(formatDuration(0, { style: 'msCompound' })).toBe('0s')
    expect(formatDuration(59999, { style: 'msCompound' })).toBe('59s')
    expect(formatDuration(61000, { style: 'msCompound' })).toBe('1m 1s')
    expect(formatDuration(3_660_000, { style: 'msCompound' })).toBe('1h 1m')
  })

  it('returns the null text for a missing value', () => {
    expect(formatDuration(null, { style: 'msCompound', nullText: '-' })).toBe('-')
  })
})

describe('formatFileSize with a short unit ladder (#19680)', () => {
  const short = { decimals: 1, units: ['B', 'KB', 'MB', 'GB'], nullText: '0 B' } as const
  it('keeps the file-browser text', () => {
    expect(formatFileSize(0, short)).toBe('0 B')
    expect(formatFileSize(1536, short)).toBe('1.5 KB')
    expect(formatFileSize(null, short)).toBe('0 B')
  })
})

describe('millisecond duration styles keep their sites output (#19680)', () => {
  const dp = { style: 'msSeconds1dp' } as const
  const sm = { style: 'msSecondsMinutes' } as const
  it('msSeconds1dp rounds sub-second ms and never adds minutes', () => {
    expect(formatDuration(500, dp)).toBe('500ms')
    expect(formatDuration(12.345, dp)).toBe('12ms')
    expect(formatDuration(75000, dp)).toBe('75.0s')
    expect(formatDuration(119000, dp)).toBe('119.0s')
  })
  it('msSecondsMinutes adds Xm Ys from a minute up', () => {
    expect(formatDuration(500, sm)).toBe('500ms')
    expect(formatDuration(12.345, sm)).toBe('12ms')
    expect(formatDuration(75000, sm)).toBe('1m 15s')
    expect(formatDuration(119000, sm)).toBe('1m 59s')
  })
})

describe('range form with a numeric style (#19680)', () => {
  const start = '2026-01-01T00:00:00Z'
  it('floors for msCompound, rounds for msMinutesSeconds, keeps minutes over an hour', () => {
    expect(formatDuration(start, '2026-01-01T00:00:00.900Z', { style: 'msCompound' })).toBe('0s')
    expect(formatDuration(start, '2026-01-01T01:15:03Z', { style: 'msMinutesSeconds' })).toBe('75m 3s')
    expect(formatDuration(start, '2026-01-01T00:00:59.600Z', { style: 'msMinutesSeconds' })).toBe('1m 0s')
  })
  it('shows a missing start as the null text and a negative span as zero', () => {
    expect(formatDuration(null, null, { style: 'msCompound', nullText: '-' })).toBe('-')
    expect(formatDuration(start, '2025-12-31T23:59:55Z', { style: 'msCompound' })).toBe('0s')
  })
})

describe('per-tier decimals and separator (#19680)', () => {
  it('formats the tree-node sizes as before', () => {
    const o = {
      decimals: [0, 0, 1],
      units: ['B', 'KB', 'MB'],
      integerBase: true,
      keepTrailingZeros: true,
      separator: '',
      zeroText: '0B',
    } as const
    expect(formatFileSize(0, o)).toBe('0B')
    expect(formatFileSize(512, o)).toBe('512B')
    expect(formatFileSize(1536, o)).toBe('2KB')
    expect(formatFileSize(1048576, o)).toBe('1.0MB')
  })
  it('keeps two decimals for GB only', () => {
    const o = {
      decimals: [0, 1, 1, 2],
      units: ['B', 'KB', 'MB', 'GB'],
      integerBase: true,
      keepTrailingZeros: true,
    } as const
    expect(formatFileSize(1536, o)).toBe('1.5 KB')
    expect(formatFileSize(1073741824, o)).toBe('1.00 GB')
  })
})
