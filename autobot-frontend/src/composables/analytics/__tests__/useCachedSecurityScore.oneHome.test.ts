// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * One home for the cached security score read (#18907, #20999).
 *
 * Only `useCachedSecurityScore.ts` may name the route or import `CACHED_SECURITY_SCORE_PATH`;
 * a second reader in any other source file fails this sweep. Planted controls prove the
 * detector can fail, and a comment-only control proves it does not fire on prose.
 *
 * Limit: this is a LITERAL text match on code lines. It matches `security/score` (so template
 * literals and `'/security/score' + '/cached'` are caught), but a path assembled from pieces
 * that never spell `security/score` on one line (e.g. `['security', 'score'].join('/')`) is
 * invisible to it. The live, non-cached route `.../security/score` (path ends right after
 * `score`, a different endpoint, and no next line starts with `+`) is the one exempt shape.
 */
import { describe, expect, it } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const SRC = join(__dirname, '..', '..', '..')
const HOME = 'composables/analytics/useCachedSecurityScore.ts'
const ROUTE = /security\/score/
const PATH_CONST = /\bCACHED_SECURITY_SCORE_PATH\b/
const LIVE_ROUTE = /security\/score[`'"]\s*[,)]?\s*$/
const SKIP = /(^types\/generated\/|\.test\.ts$|__tests__\/|__mocks__\/)/

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) return sourceFiles(full)
    return /\.(ts|vue|js)$/.test(name) ? [full] : []
  })
}

function isCode(line: string): boolean {
  return !/^\s*(\*|\/\/|\/\*)/.test(line)
}

function namesRoute(line: string, next = ''): boolean {
  const exempt = LIVE_ROUTE.test(line) && !/^\s*\+/.test(next) // a following `+` concatenates
  return (ROUTE.test(line) && !exempt) || PATH_CONST.test(line)
}

/** Code lines only: doc comments may mention the route. */
function names(text: string): boolean {
  const lines = text.split('\n')
  return lines.some((l, i) => isCode(l) && namesRoute(l, lines[i + 1]))
}

function readers(files: Record<string, string>): string[] {
  return Object.keys(files).filter(
    (f) => f !== HOME && !SKIP.test(f) && names(files[f]),
  )
}

describe('cached security score read has one home', () => {
  it('no source file other than the canonical composable names the route or path constant', () => {
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

  it('planted control: dynamic and concatenated paths are detected', () => {
    const planted = {
      [HOME]: "path: '/api/code-intelligence/security/score/cached'",
      'composables/tpl.ts': 'get(`${base}/code-intelligence/security/score/${kind}`)',
      'composables/cat.ts': "get(base + '/security/score' + '/cached')",
    }
    expect(readers(planted).sort()).toEqual(['composables/cat.ts', 'composables/tpl.ts'])
  })

  it('planted control: multi-line concatenation after the live-route shape is detected', () => {
    const planted = {
      [HOME]: 'export const CACHED_SECURITY_SCORE_PATH = 1',
      'composables/multi.ts': "get(base + '/security/score'\n  + '/cached')",
    }
    expect(readers(planted)).toEqual(['composables/multi.ts'])
  })

  it('planted control: importing the path constant elsewhere is detected', () => {
    const planted = {
      [HOME]: 'export const CACHED_SECURITY_SCORE_PATH = 1',
      'composables/importer.ts': "import { CACHED_SECURITY_SCORE_PATH } from './x'",
    }
    expect(readers(planted)).toEqual(['composables/importer.ts'])
  })

  it('negative control: comment-only mentions are not readers', () => {
    const planted = {
      [HOME]: 'export const CACHED_SECURITY_SCORE_PATH = 1',
      'composables/doc.ts': '// GET /api/code-intelligence/security/score/cached\n/**\n * security/score\n */',
    }
    expect(readers(planted)).toEqual([])
  })

  it('negative control: the live non-cached route is not a cached reader', () => {
    const planted = {
      [HOME]: 'export const CACHED_SECURITY_SCORE_PATH = 1',
      'composables/live.ts': '`${getApiBase()}/code-intelligence/security/score`,',
    }
    expect(readers(planted)).toEqual([])
  })
})
