// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'

import en from '@/i18n/locales/en.json'
import ar from '@/i18n/locales/ar.json'
import de from '@/i18n/locales/de.json'
import es from '@/i18n/locales/es.json'
import fa from '@/i18n/locales/fa.json'
import fr from '@/i18n/locales/fr.json'
import he from '@/i18n/locales/he.json'
import lv from '@/i18n/locales/lv.json'
import pl from '@/i18n/locales/pl.json'
import pt from '@/i18n/locales/pt.json'
import ur from '@/i18n/locales/ur.json'

const showToast = vi.fn()
vi.mock('@/composables/useToast', () => ({ useToast: () => ({ showToast }) }))
vi.mock('@/i18n', () => ({
  default: {
    global: {
      t: (key: string, params: Record<string, unknown>) => `${key}|${params.filename}|${params.limit}`,
    },
  },
}))

import { ATTACHMENT_NOTICE_CODES, attachmentNoticeText, showAttachmentNotice } from '../attachmentNotice'

describe('attachment notices (#20195)', () => {
  beforeEach(() => showToast.mockClear())

  it('renders the named code with the file name and limit', () => {
    expect(attachmentNoticeText({ code: 'truncated', filename: 'big.txt' })).toBe('chat.attachmentNotice.truncated|big.txt|')
    expect(attachmentNoticeText({ code: 'too_many', limit: 5 })).toBe('chat.attachmentNotice.too_many||5')
  })

  it('an unknown or missing code is the generic unreadable text, never nothing', () => {
    expect(attachmentNoticeText({ code: 'from_a_newer_backend' })).toContain('chat.attachmentNotice.unreadable')
    expect(attachmentNoticeText(undefined)).toContain('chat.attachmentNotice.unreadable')
  })

  it('shows a warning toast', () => {
    showAttachmentNotice({ code: 'image', filename: 'pic.png' })
    expect(showToast).toHaveBeenCalledWith('chat.attachmentNotice.image|pic.png|', 'warning')
  })

  it('every code has text in all 11 locales', () => {
    const locales = { en, ar, de, es, fa, fr, he, lv, pl, pt, ur } as Record<string, any>
    for (const [name, tree] of Object.entries(locales)) {
      for (const code of ATTACHMENT_NOTICE_CODES) {
        expect(tree.chat.attachmentNotice[code], `${name}:${code}`).toBeTruthy()
      }
    }
  })
})
