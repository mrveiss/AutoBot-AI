// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * The case table the retired drift test ran over two copies (#15002), now run
 * over the one copy both apps and `@autobot/terminal` import (#18550).
 *
 * A redactor that stops redacting fails no other test, so every credential
 * case also asserts the secret itself is gone, not merely that output changed.
 */
import { describe, it, expect } from 'vitest'
import { redactUrlForLogging } from '../redactUrlForLogging'

/** Inputs carrying a credential, with the value that must not survive. */
const CREDENTIAL_CASES: ReadonlyArray<readonly [string, string]> = [
  ['wss://backend.example/api/ws?token=S3CR3T', 'S3CR3T'],
  ['wss://backend.example/api/ws?session=abc&token=S3CR3T&tab=2', 'S3CR3T'],
  ['https://backend.example/cb?access_token=AT1&id_token=IT1&refresh_token=RT1', 'RT1'],
  ['https://backend.example/x?api_key=AK1&apikey=AK2&secret=SK1&password=PW1', 'PW1'],
  ['https://backend.example/x?auth=AU1&authorization=AZ1', 'AZ1'],
  ['https://backend.example/x?TOKEN=UPPER1&Access_Token=MIXED1', 'MIXED1'],
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

describe('redactUrlForLogging case table (#18550)', () => {
  it.each(CREDENTIAL_CASES)('redacts the credential in %j', (url, secret) => {
    expect(redactUrlForLogging(url)).not.toContain(secret)
  })

  it.each(CLEAN_CASES)('leaves %j untouched when it carries no credential', (url) => {
    expect(redactUrlForLogging(url)).toBe(url)
  })

  it('never throws on a malformed URL', () => {
    for (const url of ['not a url ?token=MALFORMED1', 'http://[::1', '%%%']) {
      expect(() => redactUrlForLogging(url)).not.toThrow()
    }
  })
})
