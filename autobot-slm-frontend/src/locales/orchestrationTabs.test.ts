// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #17487: the tab id, route and key are all "infrastructure", so the label must name the
 * infrastructure tab, not "Overview" (the key name is the only hint a translator gets).
 */

import { describe, it, expect } from 'vitest'

const bundles = import.meta.glob('./*.json', { eager: true, import: 'default' }) as Record<
  string,
  { orchestrationView: Record<string, string> }
>

describe('orchestrationView.tabInfrastructure (#17487)', () => {
  it('reads "Infrastructure" in English', () => {
    expect(bundles['./en.json'].orchestrationView.tabInfrastructure).toBe('Infrastructure')
  })

  it.each(Object.keys(bundles))('%s changed with it: no locale still carries the old "Overview" wording', (file) => {
    const v = bundles[file].orchestrationView.tabInfrastructure
    expect(v).toBeTruthy()
    // The old values were the "Overview" translations; the English-key sibling tabs never held one.
    expect(v).not.toBe('Overview')
  })
})
