// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import { describe, it, expect } from 'vitest'
import { errorText } from './errorText'

describe('errorText (#19068)', () => {
  it('returns an Error message', () => expect(errorText(new Error('boom'))).toBe('boom'))
  it('returns a string as it is', () => expect(errorText('gateway timeout')).toBe('gateway timeout'))
  it('renders an object as JSON, never [object Object]', () => {
    expect(errorText({ code: 502 })).toBe('{"code":502}')
    expect(errorText({ code: 502 })).not.toContain('[object Object]')
  })
  it.each([
    ['an Error with an empty message', new Error('')],
    ['null', null],
    ['undefined', undefined],
    ['an empty string', ''],
    ['an empty object', {}],
  ])('%s gives the passed fallback, not empty text', (_label, value) => {
    expect(errorText(value, 'translated fallback')).toBe('translated fallback')
  })
  it('defaults the fallback to the shared translated key', () => {
    expect(errorText(undefined)).toBe('Unknown error')
  })
  it('survives a circular object', () => {
    const a: Record<string, unknown> = {}
    a.self = a
    expect(errorText(a, 'fb')).toBe('fb')
  })
})
