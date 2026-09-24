// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The coverage gate is shaped so vitest actually reads it (#17324).
 *
 * The gate spent its whole life inert: the four numbers were nested under a
 * `global` key, and vitest treats an unrecognised key under `thresholds` as a
 * GLOB pattern for per-file thresholds. "global" matched no file, so nothing
 * was enforced, and CI passed the coverage job at ~50% against a declared 70%
 * without a word. A gate that cannot fail is indistinguishable, in CI output
 * and in review, from a gate that passed.
 *
 * That is not a defect a coverage run can catch -- a silently-inert gate looks
 * exactly like a satisfied one -- so it is checked here, on the shape of the
 * config itself. The config is read as text rather than imported: importing it
 * pulls in the whole vite config and its plugins, and this assertion is about
 * what is written in the file, not about what vite resolves at runtime.
 */

import { describe, it, expect } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

// Resolved from the project root vitest itself runs in, not from
// `import.meta.url`: under the module runner that URL is not a file: URL.
const CONFIG_PATH = resolve(process.cwd(), 'vitest.config.ts')

/**
 * Every key `interface Thresholds` accepts. Anything else is a per-file glob,
 * which is a legitimate feature -- but a glob that matches no file enforces
 * nothing, and that is the failure this test exists to prevent.
 */
const THRESHOLD_KEYS = new Set(['100', 'perFile', 'autoUpdate', 'statements', 'functions', 'branches', 'lines'])

/** The floors that must stay present and numeric. */
const METRICS = ['statements', 'functions', 'branches', 'lines'] as const

function thresholdBlock(source: string): string {
  const start = source.indexOf('thresholds: {')
  expect(start, 'vitest.config.ts declares no `thresholds` block at all — the coverage gate is absent, not merely inert').toBeGreaterThan(-1)

  let depth = 0
  for (let i = source.indexOf('{', start); i < source.length; i++) {
    if (source[i] === '{') depth++
    else if (source[i] === '}') {
      depth--
      if (depth === 0) return source.slice(start, i + 1)
    }
  }
  throw new Error('the `thresholds` block is not brace-balanced')
}

/**
 * Top-level `key: value` pairs of the block, ignoring comments and nested
 * objects.
 *
 * Both tests below read THIS, never the block's raw text. A regex over the raw
 * text matches a metric that has been commented out just as happily as one
 * vitest enforces -- which would let the exact evasion these tests exist to
 * catch pass them both.
 */
function topLevelEntries(block: string): Map<string, string> {
  const body = block.slice(block.indexOf('{') + 1, block.lastIndexOf('}'))
  const entries = new Map<string, string>()
  let depth = 0
  for (const rawLine of body.split('\n')) {
    const line = rawLine.replace(/\/\/.*$/, '').trim()
    // A quoted key is captured whole: a per-file glob ('src/**') is not an
    // identifier, and silently skipping it would hide the very key shape that
    // makes a threshold block inert.
    if (depth === 0) {
      const match = line.match(/^(?:'([^']*)'|"([^"]*)"|([A-Za-z0-9_$]+))\s*:\s*(.*)$/)
      if (match) {
        const key = match[1] ?? match[2] ?? match[3]
        entries.set(key, (match[4] ?? '').trim().replace(/,$/, ''))
      }
    }
    depth += (line.match(/\{/g) || []).length - (line.match(/\}/g) || []).length
  }
  return entries
}

describe('the coverage threshold block (#17324)', () => {
  if (!existsSync(CONFIG_PATH)) {
    throw new Error(`cannot read the config this test exists to check: ${CONFIG_PATH}`)
  }
  const source = readFileSync(CONFIG_PATH, 'utf-8').replace(/\/\*[\s\S]*?\*\//g, '')
  const block = thresholdBlock(source)
  const entries = topLevelEntries(block)
  const keys = [...entries.keys()]

  it('uses only keys vitest reads as thresholds', () => {
    const globs = keys.filter(key => !THRESHOLD_KEYS.has(key))
    expect(
      globs,
      `these keys are not thresholds — vitest reads each as a glob pattern for per-file thresholds, ` +
        `and one that matches no file (as "global" did) silently enforces nothing: ${globs.join(', ')}`,
    ).toEqual([])
  })

  it('still pins every metric to a number', () => {
    for (const metric of METRICS) {
      const value = entries.get(metric)
      expect(
        value,
        `no floor pinned for ${metric} — an unpinned metric is ungated. ` +
          `Commenting one out leaves its text in the file but removes it from the ` +
          `object vitest reads, which is why this checks the parsed entries.`,
      ).toBeDefined()
      // `Number('')` is 0, not NaN, so a bare `statements:` would otherwise read
      // as a pinned floor of zero. Match the text, then rule on the value.
      expect(value, `${metric} floor is not a number: ${JSON.stringify(value)}`).toMatch(/^\d+(\.\d+)?$/)
      expect(
        Number(value),
        `${metric} floor is 0 — vitest enforces it and every run passes, which is ` +
          `an inert gate wearing a number rather than a floor`,
      ).toBeGreaterThan(0)
    }
  })
})
