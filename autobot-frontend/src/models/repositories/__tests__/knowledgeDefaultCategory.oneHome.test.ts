// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * One home for the knowledge default fact category (#21921).
 *
 * `DEFAULT_FACT_CATEGORY` in `knowledgeFactMapping.ts` is the only place the string `General` may
 * be written as a value at a knowledge call site (the knowledge repository, controller and
 * components); every other site imports the constant. A planted control proves the detector can
 * fail, and a comment-only control proves it does not fire on prose.
 *
 * Limit: a LITERAL text match on code lines. A category assembled from pieces is invisible to it.
 */
import { describe, expect, it } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const SRC = join(__dirname, '..', '..', '..')
const HOME = 'models/repositories/knowledgeFactMapping.ts'
const KNOWLEDGE_SITE = /^(models\/(repositories|controllers)\/Knowledge[^/]*\.ts|components\/knowledge\/.*\.vue)$/
const GENERAL_LITERAL = /(['"`])General\1/
/** Floor on files scanned: a path change that matches nothing must not read as a clean tree. */
const MIN_SITES_SCANNED = 5

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) return sourceFiles(full)
    return /\.(ts|vue)$/.test(name) ? [full] : []
  })
}

function isCode(line: string): boolean {
  return !/^\s*(\*|\/\/|\/\*)/.test(line)
}

function writesGeneral(text: string): boolean {
  return text.split('\n').some((l) => isCode(l) && GENERAL_LITERAL.test(l))
}

function offenders(files: Record<string, string>): string[] {
  return Object.keys(files).filter((f) => f !== HOME && KNOWLEDGE_SITE.test(f) && writesGeneral(files[f]))
}

describe('the knowledge default fact category has one home', () => {
  it('no knowledge call site writes the General literal; each imports DEFAULT_FACT_CATEGORY', () => {
    const files: Record<string, string> = {}
    for (const full of sourceFiles(SRC)) {
      files[relative(SRC, full).split('\\').join('/')] = readFileSync(full, 'utf-8')
    }
    const sites = Object.keys(files).filter((f) => KNOWLEDGE_SITE.test(f))
    expect(sites.length).toBeGreaterThanOrEqual(MIN_SITES_SCANNED)
    expect(offenders(files)).toEqual([])
  })

  it('catches a planted literal at a knowledge call site', () => {
    const planted = { 'models/controllers/KnowledgeController.ts': "category: category || 'General',\n" }
    expect(offenders(planted)).toEqual(['models/controllers/KnowledgeController.ts'])
  })

  it('ignores prose, the home file, and files that are not knowledge call sites', () => {
    expect(
      offenders({
        'models/controllers/KnowledgeController.ts': " * the 'General' default lives in knowledgeFactMapping\n",
        [HOME]: "export const DEFAULT_FACT_CATEGORY = 'General'\n",
        'components/analytics/CodeGenerationDashboard.vue': "{ name: 'General' }\n",
      }),
    ).toEqual([])
  })
})
