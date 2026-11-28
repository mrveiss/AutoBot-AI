// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// The sidebar wrapper's width comes from its classes (#18243): no CSS rule may force a width or min-width
// over them, or the 260px width and the collapsed w-12 never take effect.
import { describe, it, expect } from 'vitest'
import source from '../ChatInterface.vue?raw'

const rule = (selector: string): string => {
  const start = source.indexOf(`${selector} {`)
  return start < 0 ? '' : source.slice(start, source.indexOf('}', start))
}

describe('ChatInterface sidebar wrapper', () => {
  it('forces only height and flex-shrink, never a width or min-width', () => {
    const body = rule('.sidebar-loading-view')
    expect(body).toContain('height: 100% !important')
    expect(body).toContain('flex-shrink: 0 !important')
    expect(body).not.toMatch(/(^|[^-])(min-|max-)?width\s*:/m)
  })

  it('takes w-12 when collapsed and the 260px width when open', () => {
    expect(source).toMatch(/store\.sidebarCollapsed \? 'w-12' : 'w-\[16\.25rem\]'/)
  })
})
