// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #21771 — ANSI stripping and link placeholders, built without literal control characters in regexes
import { describe, it, expect } from 'vitest'
import { formatChatMessageHtml } from './chatMessageFormat'

const ESC = String.fromCharCode(27)
const BEL = String.fromCharCode(7)

describe('formatChatMessageHtml ANSI handling', () => {
  it('strips colour and cursor sequences', () => {
    const html = formatChatMessageHtml(`${ESC}[31mred${ESC}[0m and ${ESC}[?25hshown`)
    expect(html).toContain('red and shown')
    expect(html).not.toContain(ESC)
  })

  it('strips OSC sequences ended by BEL or by ST', () => {
    expect(formatChatMessageHtml(`${ESC}]0;title${BEL}after`)).toContain('after')
    expect(formatChatMessageHtml(`${ESC}]0;title${BEL}after`)).not.toContain('title')
    const st = formatChatMessageHtml(`${ESC}]8;;http://x${ESC}\\link`)
    expect(st).toContain('link')
    expect(st).not.toContain('http://x')
  })

  it('keeps a lone escape that starts no sequence out of the output markup', () => {
    expect(formatChatMessageHtml(`a${ESC}zb`)).toContain('b')
  })

  it('removes a forged link placeholder from the input instead of resolving it', () => {
    const html = formatChatMessageHtml('x \uFDD00\uFDD0 y')
    expect(html).not.toContain('\uFDD0')
    expect(html).toContain('x')
  })
})
