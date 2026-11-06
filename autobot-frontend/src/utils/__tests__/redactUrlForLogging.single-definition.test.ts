// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * There is exactly ONE `redactUrlForLogging` definition (#18550).
 *
 * It used to exist twice -- here and in `@autobot/terminal` -- held together by
 * a drift test (#15002) that compared the two copies. That test could only
 * report a divergence after someone had already made one. This guard removes
 * the reason for it: the second copy itself fails the build, so there is
 * nothing left to compare. A copy that stops redacting fails no other test,
 * and the credential then reaches a log in whichever package was not updated.
 *
 * Reach floor: the sweep must have read the kit's own definition, so a moved
 * directory or narrowed glob cannot read as "no second copy".
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, relative, resolve } from 'node:path'

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../../../../')
const CANONICAL = 'libs/autobot-ui/src/utils/redactUrlForLogging.ts'

const TREES = [
  'autobot-frontend/src',
  'autobot-slm-frontend/src',
  'autobot-plugins',
  'libs/autobot-ui/src',
].map((dir) => resolve(REPO_ROOT, dir))

const SOURCE_EXT = /\.(ts|tsx|js|jsx|vue)$/
const EXCLUDED = /(node_modules|__tests__\/|\.test\.|\.spec\.)/

/** A definition, not a use: `function redactUrlForLogging`, or a `const`/`let` binding of that name. */
const DEFINES_REDACTOR = /(?:\bfunction\s+redactUrlForLogging\b|\b(?:const|let|var)\s+redactUrlForLogging\b)/

/** Strip comments so prose that names the function is not read as a definition. */
function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
}

export function definesRedactor(source: string): boolean {
  return DEFINES_REDACTOR.test(stripComments(source))
}

function sourceFiles(): string[] {
  return TREES.flatMap((dir) =>
    (readdirSync(dir, { recursive: true }) as string[])
      .filter((rel) => SOURCE_EXT.test(rel) && !EXCLUDED.test(rel))
      .map((rel) => relative(REPO_ROOT, resolve(dir, rel))),
  )
}

describe('one redactUrlForLogging definition (#18550)', () => {
  it('is defined only in the @autobot/ui kit', () => {
    const files = sourceFiles()
    expect(files, 'the sweep did not reach the kit definition').toContain(CANONICAL)

    const definers = files.filter((f) => definesRedactor(readFileSync(resolve(REPO_ROOT, f), 'utf-8')))
    expect(
      definers,
      `redactUrlForLogging must be defined once, in ${CANONICAL}; import it from '@autobot/ui' instead of copying it: ${definers.join(', ')}`,
    ).toEqual([CANONICAL])
  })

  // --- negative controls: the detector fires on a re-introduced copy ---

  it('flags a function declaration copy', () => {
    expect(definesRedactor('export function redactUrlForLogging(u: string) { return u }')).toBe(true)
  })

  it('flags an arrow-function copy', () => {
    expect(definesRedactor('export const redactUrlForLogging = (u: string) => u')).toBe(true)
  })

  it('does not flag an import, a re-export or prose', () => {
    expect(definesRedactor("import { redactUrlForLogging } from '@autobot/ui'")).toBe(false)
    expect(definesRedactor("export { redactUrlForLogging } from '@autobot/ui'")).toBe(false)
    expect(definesRedactor('// function redactUrlForLogging was copied here once')).toBe(false)
  })
})
