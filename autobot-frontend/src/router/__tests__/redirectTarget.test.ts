// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// GH#13996: the `?redirect=` allowlist. Widening it to `/automation` must not
// widen it to anything off-site.

import { describe, it, expect } from 'vitest'
import { safeRedirectTarget } from '../redirectTarget'

describe('safeRedirectTarget accepts in-app destinations (#13996)', () => {
  it.each([
    '/automation',
    '/automation/canvas',
    '/automation/browser-automation/sessions',
    '/automation?workflow=wf-1',
    '/automation#step-3',
    '/llc',
    '/llc/companies/c1/backlog',
  ])('accepts %s', (path) => {
    expect(safeRedirectTarget(path)).toBe(path)
  })
})

describe('safeRedirectTarget rejects everything else (#13996)', () => {
  it.each([
    ['an absolute http URL', 'https://evil.example/automation'],
    ['a protocol-relative URL', '//evil.example/automation'],
    ['a backslash-escaped host', '/\\evil.example'],
    ['a javascript: URL', 'javascript:alert(1)'],
    ['a data: URL', 'data:text/html,<script>x</script>'],
    ['a relative path', 'automation/canvas'],
    ['a prefix look-alike', '/automation-evil.example'],
    ['another prefix look-alike', '/llcx/companies'],
    ['a path outside the allowlist', '/settings'],
    ['a tab-obfuscated protocol-relative URL', '/\t/evil.example'],
    ['a newline-obfuscated URL', '/automation\n//evil.example'],
    ['an empty string', ''],
  ])('rejects %s', (_label, raw) => {
    expect(safeRedirectTarget(raw)).toBeNull()
  })

  it.each([
    ['undefined', undefined],
    ['null', null],
    ['a repeated query param', ['/automation', 'https://evil.example']],
  ])('rejects %s', (_label, raw) => {
    expect(safeRedirectTarget(raw)).toBeNull()
  })
})
