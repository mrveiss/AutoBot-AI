// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * No WebSocket client puts the auth token in the URL, ever again (#16457).
 *
 * `useSessionCollaboration.ts` and `TerminalService.ts` both called
 * `buildAuthenticatedWsUrl()` to open `/ws/sessions/{id}/presence` and
 * `/ws/{session_id}` with the JWT embedded as `?token=...` -- the exact
 * exposure this issue exists to close, and the live nginx access log records
 * `$request` (query string included), so this leaked real tokens. A third
 * shape leaked indirectly: `SSHTerminal.vue` built its URL the same way and
 * handed it to the generic `useWebSocket()` composable, which had no way to
 * carry a subprotocol at all -- fixed by giving it a `protocols` option.
 *
 * This guard is deliberately NOT scoped to files that call `new WebSocket(`
 * directly. `SSHTerminal.vue` never calls it -- `useWebSocket.ts` does, on
 * its behalf -- so a check scoped to direct callers would have missed
 * exactly the shape that slipped through review once already. The
 * population here is every source file that so much as mentions
 * `WebSocket` (covers a file that only *drives* a connection through a
 * composable, not just one that opens the socket itself); scoping BOTH
 * forbidden-pattern checks to that population, rather than to the whole
 * tree, is what keeps `usePairingQR.ts`'s unrelated `?token=` (a mobile
 * device-pairing challenge code, nothing to do with WebSocket auth) from
 * being reported as an offender -- the first version of this guard did scan
 * the whole tree and flagged it.
 *
 * Mirrors `repo_tests/websocket_subprotocol_echo_guard_test.py` on the
 * backend: a reach floor so an empty sweep cannot read as a clean tree, and
 * negative controls proving the detector fires on exactly what it forbids.
 */

import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const HERE = dirname(fileURLToPath(import.meta.url))
// this file: autobot-frontend/src/__tests__/ -> up 3 levels is the repo root.
const REPO_ROOT = resolve(HERE, '../../../')

interface Tree {
  label: string
  dir: string
}

const TREES: Tree[] = [
  { label: 'autobot-frontend', dir: resolve(REPO_ROOT, 'autobot-frontend/src') },
  { label: 'autobot-slm-frontend', dir: resolve(REPO_ROOT, 'autobot-slm-frontend/src') },
]

const SOURCE_EXT = /\.(ts|tsx|js|jsx|vue)$/
const EXCLUDED_PATH = /(__tests__\/|\.test\.|\.spec\.|\/mocks\/|\/test\/)/
/** The helper's own definition necessarily contains its own name and, in a
 * doc comment, the string it exists to stop others from writing -- excluded
 * so the guard does not report itself. */
const HELPER_DEFINITION = 'utils/buildAuthenticatedWsUrl.ts'

const MENTIONS_WEBSOCKET = /WebSocket/
const USES_URL_HELPER = /\bbuildAuthenticatedWsUrl\s*\(/
const EMBEDS_TOKEN_QUERY = /[?&]token=/

interface ScannedFile {
  tree: string
  relPath: string
  source: string
}

/**
 * Strip `//` and `/* *\/` comments before matching (not spec-complete, good
 * enough here): several files -- the helper's own definition,
 * `redactUrlForLogging.ts`'s doc comment describing the pattern it
 * redacts -- mention `buildAuthenticatedWsUrl(` or `?token=` only in prose,
 * never in code. Un-stripped, those already read as false offenders in this
 * guard's first draft. `//` is only stripped when not preceded by `:`, so
 * `https://` survives.
 */
function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
}

function scanTree(tree: Tree): ScannedFile[] {
  return (readdirSync(tree.dir, { recursive: true }) as string[])
    .filter((rel) => SOURCE_EXT.test(rel) && !EXCLUDED_PATH.test(rel))
    .map((rel) => ({
      tree: tree.label,
      relPath: rel,
      source: stripComments(readFileSync(resolve(tree.dir, rel), 'utf-8')),
    }))
}

function allSourceFiles(): ScannedFile[] {
  return TREES.flatMap(scanTree).filter((f) => !f.relPath.endsWith(HELPER_DEFINITION))
}

/** WebSocket-related files -- the reach population this guard examines. */
export function websocketRelatedFiles(files: ScannedFile[]): ScannedFile[] {
  return files.filter((f) => MENTIONS_WEBSOCKET.test(f.source))
}

/**
 * Does this source leak the auth token into a WebSocket URL -- either via
 * the shared `buildAuthenticatedWsUrl()` helper (which embeds it as
 * `?token=...`), or a hand-built literal `?token=`/`&token=` query string?
 */
export function leaksTokenInUrl(source: string): boolean {
  return USES_URL_HELPER.test(source) || EMBEDS_TOKEN_QUERY.test(source)
}

//: MEASURED 2026-09-18 against this branch, after fixing the three call
//: sites the review found: 61 WebSocket-related files across both frontend
//: trees (56 in autobot-frontend, 5 in autobot-slm-frontend). Floor set 6
//: below that so ordinary file churn (a new composable that imports
//: useWebSocket, a new component using GlobalWebSocketService) doesn't fail
//: this on an unrelated PR; a floor this close to the live population is
//: still far enough from zero to catch a narrowed glob or a moved
//: directory, which is the failure this floor exists to catch, not the
//: normal week-to-week drift.
const MIN_WEBSOCKET_RELATED_FILES = 55

describe('no WebSocket client puts the auth token in the URL (#16457)', () => {
  it('no WebSocket-related file leaks the token into the URL', () => {
    const population = websocketRelatedFiles(allSourceFiles())
    // Reach, not just a clean result: a scan that found no WebSocket-related
    // files would report zero offenders having looked at nothing.
    expect(population.length).toBeGreaterThanOrEqual(MIN_WEBSOCKET_RELATED_FILES)

    const offenders = population.filter((f) => leaksTokenInUrl(f.source)).map((f) => `${f.tree}/${f.relPath}`)
    expect(
      offenders,
      'these leak the auth token into a WebSocket URL (via buildAuthenticatedWsUrl() or a literal ' +
        `?token=/&token= query string) instead of the Sec-WebSocket-Protocol subprotocol: ${offenders.join(', ')}`,
    ).toEqual([])
  })

  it('reached both frontend trees', () => {
    const population = websocketRelatedFiles(allSourceFiles())
    for (const tree of TREES) {
      const inTree = population.filter((f) => f.tree === tree.label)
      expect(inTree.length, `${tree.label} contributed nothing to the population`).toBeGreaterThan(0)
    }
  })

  // --- negative controls: the detector fires on exactly what it forbids ---

  it('flags a call to buildAuthenticatedWsUrl()', () => {
    expect(leaksTokenInUrl("const url = buildAuthenticatedWsUrl(base)\nnew WebSocket(url)")).toBe(true)
  })

  it('flags a literal ?token= query string', () => {
    expect(leaksTokenInUrl('const url = `${base}?token=${token}`\nnew WebSocket(url)')).toBe(true)
  })

  it('flags a literal &token= query string after another param', () => {
    expect(leaksTokenInUrl('const url = `${base}?a=1&token=${token}`\nnew WebSocket(url)')).toBe(true)
  })

  it('does not flag the subprotocol form', () => {
    expect(leaksTokenInUrl("new WebSocket(url, ['bearer', token])")).toBe(false)
  })

  it('does not flag an unrelated ?token= with no WebSocket in the file', () => {
    // The exact shape of `usePairingQR.ts`'s device-pairing challenge URL --
    // proves the population filter, not the pattern match, is what keeps it
    // out: leaksTokenInUrl() alone WOULD flag this string; websocketRelatedFiles()
    // is what excludes the file that contains it.
    const source = 'const qrUrl = `autobot://pair?token=${challengeToken}`'
    expect(leaksTokenInUrl(source)).toBe(true)
    expect(websocketRelatedFiles([{ tree: 't', relPath: 'x.ts', source }])).toEqual([])
  })
})
