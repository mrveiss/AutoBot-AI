// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { numericFloor, meetsFloor } from './dependency-floor-reporter'

describe('numericFloor', () => {
  it('reads the major.minor.patch out of a caret range', () => {
    expect(numericFloor('^30.0.1')).toEqual([30, 0, 1])
  })

  it('reads a bare installed version the same way', () => {
    expect(numericFloor('4.1.9')).toEqual([4, 1, 9])
  })

  it('returns null for a range with no numeric floor (workspace/git/file protocol)', () => {
    expect(numericFloor('workspace:*')).toBeNull()
    expect(numericFloor('file:../libs/autobot-ui')).toBeNull()
  })
})

describe('meetsFloor', () => {
  it('passes when installed is newer', () => {
    expect(meetsFloor([5, 0, 0], [4, 1, 9])).toBe(true)
  })

  it('passes when installed exactly matches the floor', () => {
    expect(meetsFloor([30, 0, 1], [30, 0, 1])).toBe(true)
  })

  it('fails when installed is older -- this is #16919 itself: vitest 4.1.9 against a ^5.0.0 floor', () => {
    expect(meetsFloor([4, 1, 9], [5, 0, 0])).toBe(false)
  })

  it('fails when installed is older -- jsdom absent entirely reads as [0,0,0] by caller convention, below any real floor', () => {
    expect(meetsFloor([0, 0, 0], [30, 0, 1])).toBe(false)
  })
})

describe('findShortfalls (negative control over the whole scan)', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  it('reports nothing when every installed version meets its declared floor', async () => {
    vi.doMock('node:fs', () => {
      const existsSync = () => true
      const readFileSync = (path: string) => {
        if (path.endsWith('package.json') && !path.includes('node_modules')) {
          return JSON.stringify({ dependencies: { vue: '^3.5.0' }, devDependencies: {} })
        }
        return JSON.stringify({ version: '3.5.0' })
      }
      return { existsSync, readFileSync, default: { existsSync, readFileSync } }
    })
    const { findShortfalls } = await import('./dependency-floor-reporter')
    expect(findShortfalls()).toEqual([])
  })

  it('reports a shortfall when an installed version is below the declared floor -- proves the scan is not vacuous', async () => {
    vi.doMock('node:fs', () => {
      const existsSync = () => true
      const readFileSync = (path: string) => {
        if (path.endsWith('package.json') && !path.includes('node_modules')) {
          return JSON.stringify({ dependencies: {}, devDependencies: { vitest: '^5.0.0' } })
        }
        return JSON.stringify({ version: '4.1.9' })
      }
      return { existsSync, readFileSync, default: { existsSync, readFileSync } }
    })
    const { findShortfalls } = await import('./dependency-floor-reporter')
    const found = findShortfalls()
    expect(found).toEqual([{ name: 'vitest', declared: '^5.0.0', installed: '4.1.9' }])
  })

  it('reports a package as missing (not a version shortfall) when node_modules has no entry for it', async () => {
    vi.doMock('node:fs', () => {
      const existsSync = () => false
      const readFileSync = (_path: string) =>
        JSON.stringify({ dependencies: {}, devDependencies: { jsdom: '^30.0.1' } })
      return { existsSync, readFileSync, default: { existsSync, readFileSync } }
    })
    const { findShortfalls } = await import('./dependency-floor-reporter')
    expect(findShortfalls()).toEqual([{ name: 'jsdom', declared: '^30.0.1', installed: null }])
  })
})
