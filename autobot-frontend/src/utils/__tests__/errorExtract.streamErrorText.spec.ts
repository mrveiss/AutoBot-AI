// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/** #16845 — a budget refusal is shown through its i18n key, not as the raw backend string. */
import { beforeAll, describe, it, expect } from 'vitest'
import i18n from '@/i18n'
import { streamErrorText } from '../errorExtract'

describe('streamErrorText', () => {
  beforeAll(async () => {
    const en = await import('@/i18n/locales/en.json')
    i18n.global.setLocaleMessage('en', en.default)
  })

  it('renders the translation a refusal names, with its params', () => {
    const text = streamErrorText({
      content: 'english fallback',
      metadata: { i18n_key: 'chat.errors.budgetExhausted', i18n_params: { scope: 'user', period: 'day', limit: '5.00' } },
    })
    expect(text).toContain('day spending limit')
    expect(text).toContain('$5.00')
    expect(text).not.toContain('english fallback')
  })

  it('keeps the raw error for events that name no key', () => {
    expect(streamErrorText({ content: 'boom' })).toBe('Error: boom')
    expect(streamErrorText({})).toBe('Error: Unknown error')
  })
})
