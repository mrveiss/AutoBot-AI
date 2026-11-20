// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * The destination type labels are proper nouns, kept as literals on purpose (#21796): a product or
 * protocol name reads the same in every locale. A label that is prose must become an i18n key instead.
 */
import { describe, it, expect } from 'vitest'
import { destinationTypes } from '../logForwardingForm'

const PRODUCT_NAMES: Record<string, string> = {
  syslog: 'Syslog',
  webhook: 'Webhook',
  file: 'File',
  elasticsearch: 'Elasticsearch',
  loki: 'Loki',
  seq: 'Seq',
}

describe('destinationTypes', () => {
  it('is exactly the served destination kinds, each labelled by its product name', () => {
    expect(Object.fromEntries(destinationTypes.map((d) => [d.value, d.label]))).toEqual(PRODUCT_NAMES)
  })

  it('has one capitalised single word per label, so no prose hides in the literal list', () => {
    for (const { label } of destinationTypes) {
      expect(label).toMatch(/^[A-Z][A-Za-z]+$/)
    }
  })

  it('rejects a prose label (detector control)', () => {
    expect('Send logs to a file').not.toMatch(/^[A-Z][A-Za-z]+$/)
  })
})
