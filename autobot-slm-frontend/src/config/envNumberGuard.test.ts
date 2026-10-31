// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Guard (#19614): numeric `VITE_*` parsing lives in `config/ssot-config.ts`
 * only. A file that reads a `VITE_*` variable and also parses a number is a
 * second parser, which is how the SLM came to have three that disagreed on 0
 * and negatives. Vite built-ins (`BASE_URL`, `DEV`) are not configuration.
 */

import { readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, it, expect } from 'vitest'

const SRC = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const OWNER = join('config', 'ssot-config.ts')
const ENV_READ = /import\.meta\.env\??\.VITE_|import\.meta\.env\??\[/
const NUMERIC_PARSE = /\bparseInt\(|\bparseFloat\(|\bNumber\(/

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) return sourceFiles(full)
    return /\.(ts|vue)$/.test(name) && !/\.(test|spec)\.ts$/.test(name) ? [full] : []
  })
}

/** Files other than the owner that read a VITE_* variable and parse a number. */
function strayNumericParsers(files: Array<[string, string]>): string[] {
  return files
    .filter(([rel, text]) => rel !== OWNER && ENV_READ.test(text) && NUMERIC_PARSE.test(text))
    .map(([rel]) => rel)
}

describe('no numeric VITE_* parse outside ssot-config.ts (#19614)', () => {
  it('finds no second parser in src', () => {
    const files = sourceFiles(SRC).map((f): [string, string] => [
      relative(SRC, f),
      readFileSync(f, 'utf-8'),
    ])
    expect(files.length).toBeGreaterThan(100)
    expect(strayNumericParsers(files)).toEqual([])
  })

  it('control: flags the shape the three old parsers had', () => {
    const old = 'const raw = import.meta.env.VITE_X\nconst n = parseInt(String(raw), 10)'
    const rel = join('utils', 'x.ts')
    expect(strayNumericParsers([[rel, old]])).toEqual([rel])
    expect(strayNumericParsers([[OWNER, old]])).toEqual([])
  })
})
