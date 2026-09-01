// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The client-side rules agree with the API's, and say which field is wrong (#14105).
 *
 * The requirement is "the same validation the API enforces … surfaced as field
 * errors rather than a raw 422". Two ways to fail that: reject something the API
 * accepts (the user cannot enter valid data), or accept something the API
 * rejects (the 422 comes back anyway and nothing was gained). Both directions
 * are covered, and the bounds are asserted against the numbers transcribed from
 * `llc/api/contacts.py` rather than against the constants themselves — reading
 * a constant back to itself proves nothing.
 */

import { describe, it, expect } from 'vitest'

import en from '@/i18n/locales/en.json'

import { contactErrorList, isValidContact, validateContact } from '../contactValidation'

const valid = { full_name: 'Ada Lovelace', role_title: 'Analyst', email: 'ada@example.com', phone: '+44 (20) 7946-0000' }

describe('#14105: contact validation mirrors the API', () => {
  it('accepts a contact the API would accept', () => {
    expect(validateContact(valid)).toEqual({})
    expect(isValidContact(valid)).toBe(true)
  })

  it('requires a non-blank full name, as ContactCreate does', () => {
    expect(validateContact({ ...valid, full_name: '   ' }).full_name).toBeDefined()
  })

  it.each([
    ['full_name', 256, 'full_name'],
    ['email', 321, 'email'],
    ['role_title', 256, 'role_title'],
  ])('rejects %s beyond the API bound', (field, length, errorKey) => {
    const suffix = field === 'email' ? '@example.com' : ''
    const value = 'a'.repeat(length - suffix.length) + suffix

    expect(validateContact({ ...valid, [field]: value })[errorKey as 'full_name']).toBeDefined()
  })

  it.each([
    ['letters', 'not a phone'],
    ['a slash', '+44/20/7946'],
    ['an at sign', '+44 20 7946@'],
    ['too short', '12'],
  ])('rejects a phone with %s', (_label, phone) => {
    expect(validateContact({ ...valid, phone }).phone).toBeDefined()
  })

  it.each([
    ['a leading plus', '+442079460000'],
    ['parentheses and dashes', '(020) 7946-0000'],
    ['spaces and dots', '020 7946.0000'],
  ])('accepts a phone with %s, which the API pattern allows', (_label, phone) => {
    expect(validateContact({ ...valid, phone }).phone).toBeUndefined()
  })

  it('treats an empty optional field as absent, not invalid', () => {
    // The API declares these Optional; requiring them here would reject a
    // contact the backend accepts, which is the other way to fail parity.
    expect(validateContact({ full_name: 'Ada', role_title: '', email: '', phone: '' })).toEqual({})
  })

  it('reports the offending field, not a generic failure', () => {
    const errors = validateContact({ ...valid, phone: 'nope', full_name: '' })

    expect(Object.keys(errors).sort()).toEqual(['full_name', 'phone'])
  })

  it('names the too-long phone rather than calling it malformed', () => {
    const errors = validateContact({ ...valid, phone: '1'.repeat(65) })

    expect(errors.phone).toContain('phoneTooLong')
  })

  it('every message key resolves in en.json', () => {
    const keys = Object.values(
      validateContact({ full_name: '', role_title: 'r'.repeat(256), email: 'e'.repeat(321), phone: 'bad' }),
    )
    expect(keys.length).toBeGreaterThanOrEqual(4)

    for (const key of keys) {
      const value = key.split('.').reduce<unknown>((n, seg) => (n as Record<string, unknown>)?.[seg], en)
      expect(typeof value, `${key} does not resolve`).toBe('string')
      expect(value).not.toBe('')
    }
  })
})

describe('#14105: the delete confirmation says what it destroys', () => {
  it('states permanence and that the details are erased', () => {
    const text: string = en.llc.orgPeople.deleteConfirm

    // The route erases the row; the user is entitled to know that before
    // confirming, which "Delete this contact?" did not tell them.
    expect(text.toLowerCase()).toContain('permanently')
    expect(text.toLowerCase()).toMatch(/erased|recover/)
  })
})

describe('#14105: contactErrorList renders without a cast', () => {
  it('yields concrete message strings, not string | undefined', () => {
    const list = contactErrorList({ full_name: '', role_title: '', email: '', phone: 'bad' })

    expect(list).toHaveLength(2)
    for (const entry of list) {
      expect(typeof entry.field).toBe('string')
      expect(typeof entry.messageKey).toBe('string')
    }
  })

  it('is empty for a valid draft', () => {
    expect(contactErrorList(valid)).toEqual([])
  })

  it('carries the same fields the record form reports', () => {
    const draft = { ...valid, phone: 'bad', full_name: '' }

    expect(contactErrorList(draft).map((e) => e.field).sort()).toEqual(Object.keys(validateContact(draft)).sort())
  })
})
