// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Guard (#20135, #19614): numeric `VITE_*` parsing lives in the kit's
 * `getEnvPositiveInt` only. An app file that reads a `VITE_*` variable and also
 * parses a number, or declares a reader of its own, is a second parser; that is
 * how the two apps came to disagree on 0 and negatives. Covers both apps.
 * Vite built-ins (`BASE_URL`, `DEV`) are not configuration.
 */

import { readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, it, expect } from 'vitest'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', '..')
const APPS = ['autobot-frontend', 'autobot-slm-frontend']
const ENV_READ = /import\.meta\.env\??\.VITE_|import\.meta\.env\??\[/
const NUMERIC_PARSE = /\bparseInt\(|\bparseFloat\(|\bNumber\(/
const OWN_READER = /\b(?:function|const)\s+getEnv(?:Number|PositiveInt|Int)\b/

/**
 * Files that match the heuristic without parsing an env value. CacheBuster parses a
 * `<meta>` content and a localStorage timestamp; its only env read, VITE_BUILD_TIMESTAMP,
 * is an opaque build id that is never parsed.
 */
const NOT_ENV_PARSERS = new Set([join('autobot-frontend', 'utils', 'CacheBuster.js')])

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) return name === 'node_modules' ? [] : sourceFiles(full)
    return /\.(ts|vue|js)$/.test(name) && !/\.(test|spec)\.[tj]s$/.test(name) ? [full] : []
  })
}

/** Files that read a VITE_* variable and parse a number, or declare their own reader. */
function strayNumericParsers(files: Array<[string, string]>): string[] {
  return files
    .filter(([rel]) => !NOT_ENV_PARSERS.has(rel))
    .filter(([, text]) => (ENV_READ.test(text) && NUMERIC_PARSE.test(text)) || OWN_READER.test(text))
    .map(([rel]) => rel)
}

describe('no numeric VITE_* parser in either app (#20135)', () => {
  for (const app of APPS) {
    it(`finds no local parser in ${app}`, () => {
      const src = join(ROOT, app, 'src')
      const files = sourceFiles(src).map((f): [string, string] => [
        join(app, relative(src, f)),
        readFileSync(f, 'utf-8'),
      ])
      expect(files.length).toBeGreaterThan(100)
      expect(strayNumericParsers(files)).toEqual([])
    })
  }

  it('control: flags an inline parse and a locally declared reader', () => {
    const inline = 'const raw = import.meta.env.VITE_X\nconst n = parseInt(String(raw), 10)'
    const own = 'function getEnvNumber(key: string, d: number): number { return d }'
    expect(
      strayNumericParsers([
        ['a.ts', inline],
        ['b.ts', own],
      ]),
    ).toEqual(['a.ts', 'b.ts'])
    expect(strayNumericParsers([['c.ts', 'getEnvPositiveInt(import.meta.env, "VITE_X", 1)']])).toEqual([])
  })
})
