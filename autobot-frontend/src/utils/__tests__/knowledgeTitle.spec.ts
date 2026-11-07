// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest'
import { createI18n } from 'vue-i18n'
import { formatManPageTitle } from '../formatHelpers'

// Control locale: strings distinct from en.json so a hard-coded fallback cannot pass.
const i18n = createI18n({
  legacy: false,
  locale: 'ctl',
  messages: {
    ctl: {
      knowledge: {
        manSection: {
          format: 'CMD={name} SEC={section} NAME={sectionName}',
          formatUnnamed: 'CMD={name} SEC={section}',
          '1': 'ctl-user',
          '5': 'ctl-formats',
          '8': 'ctl-admin',
        },
      },
    },
  },
})
const t = (k: string, p?: Record<string, unknown>) => i18n.global.t(k, p ?? {}) as string

describe('formatManPageTitle (#21037)', () => {
  it('renders a man-page fact with its section name', () => {
    expect(formatManPageTitle('gettext(1)', 'man_page', t)).toBe('CMD=gettext SEC=1 NAME=ctl-user')
  })
  it('strips the "man " prefix the backend writes', () => {
    expect(formatManPageTitle('man passwd(5)', 'man_page', t)).toBe('CMD=passwd SEC=5 NAME=ctl-formats')
  })
  it('tells two sections of one command apart', () => {
    expect(formatManPageTitle('passwd(1)', 'man_page', t)).not.toBe(formatManPageTitle('passwd(5)', 'man_page', t))
  })
  it('gives an unknown section no name', () => {
    expect(formatManPageTitle('foo(42)', 'man_page', t)).toBe('CMD=foo SEC=42')
  })
  it('leaves a non-man fact titled f(x) unchanged', () => {
    expect(formatManPageTitle('f(x)', 'document', t)).toBe('f(x)')
  })
  it('leaves a non-man fact shaped like a man title unchanged', () => {
    expect(formatManPageTitle('gettext(1)', 'document', t)).toBe('gettext(1)')
    expect(formatManPageTitle('gettext(1)', undefined, t)).toBe('gettext(1)')
  })
  it('leaves a man-page fact that is not name(N) unchanged', () => {
    expect(formatManPageTitle('man ls', 'manual_page', t)).toBe('man ls')
  })
  it('changes only the display: the stored record is untouched', () => {
    const fact = Object.freeze({ title: 'gettext(1)', type: 'man_page' })
    formatManPageTitle(fact.title, fact.type, t)
    expect(fact.title).toBe('gettext(1)')
  })
})
