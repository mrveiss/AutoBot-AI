// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest'
import cases from '../replyRedundancyCases.json'
import { isRedundantNarration, withoutRepeatedNarration } from '../replyRedundancy'
import { visibleMessages } from '../internalMessage'

describe('the shared case table with the backend (#21880)', () => {
  it.each(cases)('$name', ({ narration, answer, redundant }) => {
    expect(isRedundantNarration(narration, answer)).toBe(redundant)
  })
})

const narration = (text: string) => ({ sender: 'assistant', text, metadata: {} })
const respond = (text: string) => ({ sender: 'assistant', text, metadata: { message_type: 'respond_tool' } })
const user = (text: string) => ({ sender: 'user', text, metadata: {} })

describe('withoutRepeatedNarration', () => {
  it('replaces a repeated narration with the answer, live as on reload', () => {
    const list = [user('weather?'), narration('Riga is 4 degrees.'), respond('Riga is **4 degrees**.')]
    expect(withoutRepeatedNarration(list)).toEqual([list[0], list[2]])
  })

  it('keeps narration that says more than the answer', () => {
    const list = [user('q'), narration('Two sources. Riga is 4 degrees.'), respond('Riga is 4 degrees.')]
    expect(withoutRepeatedNarration(list)).toHaveLength(3)
  })

  it('does not reach into an earlier turn', () => {
    const list = [user('a'), narration('Riga is 4 degrees.'), user('b'), respond('Riga is 4 degrees.')]
    expect(withoutRepeatedNarration(list)).toHaveLength(4)
  })

  it('is applied by visibleMessages together with the internal-marker filter', () => {
    const marker = { sender: 'assistant', text: '', metadata: { internal: true } }
    const list = [user('q'), marker, narration('Hi there'), respond('Hi there')]
    expect(visibleMessages(list)).toEqual([list[0], list[3]])
  })
})

describe('a tool call is no words (#21880)', () => {
  const call = `<TOOL_CALL name="respond" params='{"text":"Riga is 4 degrees."}'>Task complete</TOOL_CALL>`
  it('drops narration that is the answer plus the respond call, live as on reload', () => {
    const out = withoutRepeatedNarration([user('weather?'), narration(`Riga is 4 degrees. ${call}`), respond('Riga is 4 degrees.')])
    expect(out.map((m) => m.sender)).toEqual(['user', 'assistant'])
    expect(out[1].metadata).toEqual({ message_type: 'respond_tool' })
  })
})
