// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The two copies of the URL log-redactor must agree (#15002).
 *
 * `@autobot/terminal` is a standalone package consumed by both GUIs, so it
 * carries its own `redactUrlForLogging` rather than importing the frontend's.
 * A copy that falls behind does not fail -- it simply stops redacting, and the
 * credential reaches a log in whichever package was not updated, with every
 * other test still green. This runs both copies over one case table and names
 * both files and the input whenever they disagree.
 *
 * Equality alone would pass if both copies stopped redacting in the same way,
 * so the table's credential cases are also checked for the secret itself.
 */

import { describe, it, expect } from 'vitest'
import { redactUrlForLogging as frontendCopy } from '@/utils/redactUrlForLogging'
import { redactUrlForLogging as pluginCopy } from '@autobot/terminal/src/utils'

const FRONTEND_FILE = 'autobot-frontend/src/utils/redactUrlForLogging.ts'
const PLUGIN_FILE = 'autobot-plugins/terminal/src/utils.ts'

type Redactor = (rawUrl: string) => string

/** Inputs carrying a credential, with the secret value that must not survive. */
const CREDENTIAL_CASES: ReadonlyArray<readonly [string, string]> = [
  ['wss://backend.example/api/ws?token=S3CR3T', 'S3CR3T'],
  ['wss://backend.example/api/ws?session=abc&token=S3CR3T&tab=2', 'S3CR3T'],
  ['https://backend.example/cb?access_token=AT1&id_token=IT1&refresh_token=RT1', 'AT1'],
  ['https://backend.example/x?api_key=AK1&apikey=AK2&secret=SK1&password=PW1', 'PW1'],
  ['https://backend.example/x?auth=AU1&authorization=AZ1', 'AZ1'],
  ['https://backend.example/x?TOKEN=UPPER1&Access_Token=MIXED1', 'MIXED1'],
  ['wss://backend.example/api/ws?x=1#token=FRAGMENT1', 'FRAGMENT1'],
  ["'http://backend.example/ws?token=LEAKED1' is not allowed.", 'LEAKED1'],
  ['not a url ?token=MALFORMED1', 'MALFORMED1'],
]

/** Inputs with no credential: other parameters must come through untouched. */
const CLEAN_CASES: readonly string[] = [
  'https://backend.example/api/health?page=2&sort=name',
  'https://backend.example/api/health',
  'not a url at all',
  '',
]

const ALL_CASES = [...CREDENTIAL_CASES.map(([url]) => url), ...CLEAN_CASES]

/** The inputs on which two redactors disagree. */
function diverging(a: Redactor, b: Redactor, cases: readonly string[]): string[] {
  return cases.filter((url) => a(url) !== b(url))
}

describe('the two redactUrlForLogging copies agree (#15002)', () => {
  it.each(ALL_CASES)('agree on %j', (url) => {
    expect(pluginCopy(url), `${PLUGIN_FILE} and ${FRONTEND_FILE} diverge on input ${JSON.stringify(url)}`).toBe(
      frontendCopy(url),
    )
  })

  it.each(CREDENTIAL_CASES)('redact the credential in %j', (url, secret) => {
    expect(frontendCopy(url), `${FRONTEND_FILE} leaked ${secret}`).not.toContain(secret)
    expect(pluginCopy(url), `${PLUGIN_FILE} leaked ${secret}`).not.toContain(secret)
  })

  it('never throw on a malformed URL -- the Invalid URL log branch is where the string may not parse', () => {
    for (const url of ['not a url ?token=MALFORMED1', 'http://[::1', '%%%']) {
      expect(() => frontendCopy(url), FRONTEND_FILE).not.toThrow()
      expect(() => pluginCopy(url), PLUGIN_FILE).not.toThrow()
    }
  })

  it.each(CLEAN_CASES)('leave %j untouched when it carries no credential', (url) => {
    // A redactor that dropped the whole query string would pass a naive
    // "no token present" check; this pins that the other parameters survive.
    expect(frontendCopy(url)).toBe(url)
    expect(pluginCopy(url)).toBe(url)
  })
})

describe('the drift check fails when one copy changes (#15002, contrast)', () => {
  it('reports the input a narrowed copy stops redacting', () => {
    // A copy that has lost `authorization` from its parameter list -- the shape
    // of drift the issue describes, one side updated and the other not.
    const narrowed: Redactor = (url) => frontendCopy(url.replace(/authorization=/i, 'authorisation=')).replace(
      /authorisation=/i,
      'authorization=',
    )
    const reported = diverging(frontendCopy, narrowed, ALL_CASES)
    expect(reported).toEqual(['https://backend.example/x?auth=AU1&authorization=AZ1'])
  })

  it('reports nothing for two identical copies', () => {
    expect(diverging(frontendCopy, frontendCopy, ALL_CASES)).toEqual([])
  })
})
