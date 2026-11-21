// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/** #21581 -- a timeout is recognised by type (class or name), never by message text. */
import { describe, it, expect } from 'vitest'
import { RequestTimeoutError } from '@autobot/ui'
import { isRequestTimeout } from '../errorExtract'

describe('isRequestTimeout', () => {
  it('is true for the kit client RequestTimeoutError', () => {
    expect(isRequestTimeout(new RequestTimeoutError(5))).toBe(true)
  })

  it('is true for the DOMException AbortSignal.timeout() produces', () => {
    expect(isRequestTimeout(new DOMException('signal timed out', 'TimeoutError'))).toBe(true)
  })

  it('is true for any object named TimeoutError', () => {
    expect(isRequestTimeout({ name: 'TimeoutError' })).toBe(true)
  })

  it('is false for a plain Error whose message is timeout', () => {
    expect(isRequestTimeout(new Error('timeout'))).toBe(false)
  })

  it('is false for a plain Error carrying the client wording', () => {
    expect(isRequestTimeout(new Error('Request timeout after 5ms'))).toBe(false)
  })

  it('is false for an AbortError', () => {
    expect(isRequestTimeout(new DOMException('aborted', 'AbortError'))).toBe(false)
  })

  it('is false for null, undefined and a string', () => {
    expect(isRequestTimeout(null)).toBe(false)
    expect(isRequestTimeout(undefined)).toBe(false)
    expect(isRequestTimeout('Request timeout after 5ms')).toBe(false)
  })
})
