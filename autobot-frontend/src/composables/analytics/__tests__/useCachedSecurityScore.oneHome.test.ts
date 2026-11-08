// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * One home for the cached security score read (#18907, #20999).
 *
 * Only `useCachedSecurityScore.ts` may name `security/score/cached`; a second reader in any
 * other source file fails this sweep. The planted control proves the detector can fail.
 */
import { describe, expect, it } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const SRC = join(__dirname, '..', '..', '..')
const HOME = 'composables/analytics/useCachedSecurityScore.ts'
const ROUTE = /security\/score\/cached/
const SKIP = /(^types\/generated\/|\.test\.ts$|__tests__\/|__mocks__\/)/

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) return sourceFiles(full)
    return /\.(ts|vue|js)$/.test(name) ? [full] : []
  })
}

/** Code lines only: doc comments may mention the route. */
function names(text: string): boolean {
  return text.split('\n').some((l) => !/^\s*(\*|\/\/|\/\*)/.test(l) && ROUTE.test(l))
}

function readers(files: Record<string, string>): string[] {
  return Object.keys(files).filter(
    (f) => f !== HOME && !SKIP.test(f) && names(files[f]),
  )
}

describe('cached security score read has one home', () => {
  it('no source file other than the canonical composable names the route', () => {
    const files: Record<string, string> = {}
    for (const f of sourceFiles(SRC)) {
      files[relative(SRC, f)] = readFileSync(f, 'utf-8')
    }
    expect(names(files[HOME])).toBe(true)
    expect(readers(files)).toEqual([])
  })

  it('planted control: a second direct reader is detected', () => {
    const planted = {
      [HOME]: "path: '/api/code-intelligence/security/score/cached'",
      'composables/other.ts': "ApiClient.get('/code-intelligence/security/score/cached')",
    }
    expect(readers(planted)).toEqual(['composables/other.ts'])
  })
})
