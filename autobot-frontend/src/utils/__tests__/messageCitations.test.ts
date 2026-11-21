// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest'
import type { ChatMessage } from '@/types/api'
import { messageCitations, proofIsPartial, toSource, unprovenValues } from '../messageCitations'

const message = (extra: Record<string, unknown>) => ({ id: 'm', sender: 'assistant', content: '', ...extra }) as ChatMessage

describe('messageCitations (#21976)', () => {
  it('reads a legacy stored knowledge-base source as knowledge_base', () => {
    const s = toSource({ title: 'T', path: 'kb/a.md', score: 0.5, chunk_id: 'c1' })
    expect(s).toMatchObject({ type: 'knowledge_base', title: 'T', chunk_id: 'c1' })
  })

  it('keeps every field of a unified tool source, and its step id', () => {
    const src = { type: 'web_search', title: 'x', step_id: 's1', url: 'https://a.example', metadata: { tool: 'web_search' } }
    expect(messageCitations(message({ sources: [src] }))[0]).toMatchObject(src)
  })

  it('a reloaded answer and the live one give the same list', () => {
    const src = { type: 'system_state', title: 'execute_command: uname -r', step_id: 's2', metadata: { tool: 'execute_command' } }
    const stored = messageCitations(message({ sources: [src] }))
    const live = messageCitations(message({ metadata: { citations: [src] } }))
    expect(live).toEqual(stored)
  })

  it('shows the training label when it is the honest source', () => {
    const src = { type: 'llm_training', title: 'AI Training Data', model: 'm' }
    expect(messageCitations(message({ metadata: { citations: [src] } }))[0].type).toBe('llm_training')
  })

  it('reads the unproven values of the proof block', () => {
    expect(unprovenValues(message({ metadata: { proof: { checked: 2, found: {}, unproven: ['5.18.33.2'] } } }))).toEqual(['5.18.33.2'])
    expect(unprovenValues(message({ metadata: {} }))).toEqual([])
  })
})

describe('proofIsPartial (#21976)', () => {
  it('reads the proof truncation flag', () => {
    expect(proofIsPartial(message({ metadata: { proof: { checked: 1, found: {}, unproven: [], truncated: true } } }))).toBe(true)
    expect(proofIsPartial(message({ metadata: { proof: { checked: 1, found: {}, unproven: [], truncated: false } } }))).toBe(false)
    expect(proofIsPartial(message({ metadata: {} }))).toBe(false)
  })
})
