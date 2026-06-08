// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { describe, it, expect } from 'vitest'
import { normalizeUrl } from '../../utils/urlUtils'

describe('normalizeUrl (#5575)', () => {
  it('prefixes localhost with http://', () => {
    expect(normalizeUrl('localhost')).toBe('http://localhost')
  })

  it('prefixes localhost:PORT with http://', () => {
    expect(normalizeUrl('localhost:3000')).toBe('http://localhost:3000')
  })

  it('prefixes a domain/path with https://', () => {
    expect(normalizeUrl('example.com/path')).toBe('https://example.com/path')
  })

  it('leaves an http:// URL unchanged', () => {
    expect(normalizeUrl('http://already-has-protocol')).toBe('http://already-has-protocol')
  })

  it('leaves an https:// URL unchanged', () => {
    expect(normalizeUrl('https://already-has-protocol')).toBe('https://already-has-protocol')
  })

  it('routes a bare word through DuckDuckGo search', () => {
    expect(normalizeUrl('google')).toBe('https://duckduckgo.com/?q=google')
  })

  it('URL-encodes spaces in a bare-word search query', () => {
    expect(normalizeUrl('hello world')).toBe('https://duckduckgo.com/?q=hello%20world')
  })
})
