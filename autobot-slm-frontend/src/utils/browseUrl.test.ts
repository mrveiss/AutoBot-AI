// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest'
import { parseBrowseUrl } from '@/utils/browseUrl'

describe('parseBrowseUrl (#22142)', () => {
  it.each(['', '   ', '/', 'example.test', 'javascript:alert(1)', 'ftp://host.test/', 'file:///etc/hosts', 'https://'])(
    'rejects %j',
    (raw) => {
      expect(parseBrowseUrl(raw)).toBeNull()
    },
  )

  it('accepts http and https with a host, trimmed', () => {
    expect(parseBrowseUrl(' https://example.test/a?b=1 ')).toBe('https://example.test/a?b=1')
    expect(parseBrowseUrl('http://localhost:8080')).toBe('http://localhost:8080/')
  })
})
