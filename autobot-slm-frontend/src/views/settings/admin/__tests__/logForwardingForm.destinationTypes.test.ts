// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * The destination type labels are proper nouns, kept as literals on purpose (#21796): a product or
 * protocol name reads the same in every locale. A label that is prose must become an i18n key instead.
 */
import { describe, it, expect } from 'vitest'
import en from '@/locales/en.json'
import { destinationTypes } from '../logForwardingForm'

const PRODUCT_NAMES: Record<string, string> = {
  syslog: 'Syslog',
  webhook: 'Webhook',
  elasticsearch: 'Elasticsearch',
  loki: 'Loki',
  seq: 'Seq',
}

describe('destinationTypes', () => {
  it('is exactly the served destination kinds; product names are literals, "File" is an i18n key', () => {
    const literals = Object.fromEntries(destinationTypes.filter((d) => d.label).map((d) => [d.value, d.label]))
    expect(literals).toEqual(PRODUCT_NAMES)
    expect(destinationTypes.map((d) => d.value).sort()).toEqual([...Object.keys(PRODUCT_NAMES), 'file'].sort())
  })

  it('routes the plain word through a key that exists in English', () => {
    const file = destinationTypes.find((d) => d.value === 'file')
    expect(file?.label).toBeUndefined()
    expect((en as { codeSyncView: { file: string } }).codeSyncView.file).toBe('File')
    expect(file?.labelKey).toBe('codeSyncView.file')
  })

  it('has one capitalised single word per label, so no prose hides in the literal list', () => {
    for (const { label } of destinationTypes.filter((d) => d.label)) {
      expect(label).toMatch(/^[A-Z][A-Za-z]+$/)
    }
  })

  it('rejects a prose label (detector control)', () => {
    expect('Send logs to a file').not.toMatch(/^[A-Z][A-Za-z]+$/)
  })
})
