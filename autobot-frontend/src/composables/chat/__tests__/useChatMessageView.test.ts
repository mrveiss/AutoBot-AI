// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// Message-row presentation helpers (#18243, step 5a batch 2): parity with the code that lived in ChatMessages.vue.
import { describe, it, expect } from 'vitest'
import {
  getContentClass, getMessageTypeBadge, getMessageWrapperClass, getSenderIcon, getSenderName, messageTypeOf,
} from '../useChatMessageView'
import type { ChatMessage } from '@/stores/useChatStore'

const msg = (over: Record<string, unknown> = {}) =>
  ({ id: 'm1', sender: 'assistant', content: 'hi', timestamp: '2026-01-01T00:00:00Z', ...over }) as unknown as ChatMessage
const t = (key: string) => key

describe('getMessageWrapperClass', () => {
  it('always carries the sender class', () => {
    expect(getMessageWrapperClass(msg({ sender: 'user' }))).toBe('message user-message')
  })

  it('adds type-* for a typed message and reads metadata.display_type as the fallback', () => {
    expect(getMessageWrapperClass(msg({ type: 'thought' }))).toContain('type-thought')
    expect(getMessageWrapperClass(msg({ metadata: { display_type: 'debug' } }))).toContain('type-debug')
  })

  it.each(['response', 'message', 'default', 'llm_response', 'llm_response_chunk'])(
    'never adds a type class for the streaming type %s (#680)',
    (type) => expect(getMessageWrapperClass(msg({ type }))).toBe('message assistant-message'),
  )

  it('marks error and sending status', () => {
    expect(getMessageWrapperClass(msg({ status: 'error' }))).toContain(' error')
    expect(getMessageWrapperClass(msg({ status: 'sending' }))).toContain(' sending')
  })
})

describe('getContentClass', () => {
  it.each([['user', 'user-content'], ['assistant', 'assistant-content'], ['system', 'system-content']])(
    '%s message gets %s',
    (sender, cls) => expect(getContentClass(msg({ sender }))).toBe('message-content ' + cls),
  )
  it('has no sender class for other senders', () => {
    expect(getContentClass(msg({ sender: 'error' }))).toBe('message-content')
  })
})

describe('getSenderIcon', () => {
  it('lets the message type win over the sender', () => {
    expect(getSenderIcon('assistant', 'thought')).toBe('brain')
    expect(getSenderIcon('user', 'terminal_output')).toBe('terminal')
  })
  it('falls back to the sender icon, then to comment', () => {
    expect(getSenderIcon('assistant')).toBe('robot')
    expect(getSenderIcon('assistant', 'unknown_type')).toBe('robot')
    expect(getSenderIcon('nobody')).toBe('comment')
  })
})

describe('getSenderName and getMessageTypeBadge', () => {
  it('translates known senders and echoes an unknown one', () => {
    expect(getSenderName('user', t)).toBe('chat.messages.senderYou')
    expect(getSenderName('assistant', t)).toBe('chat.messages.aiAssistant')
    expect(getSenderName('robot-x', t)).toBe('robot-x')
  })

  it('badges only the five typed kinds (#1310)', () => {
    expect(getMessageTypeBadge(msg({ type: 'debug' }), t)).toEqual({ label: 'chat.messages.badgeDebug', icon: 'bug', type: 'debug' })
    expect(getMessageTypeBadge(msg({ type: 'planning' }), t)?.icon).toBe('list')
    expect(getMessageTypeBadge(msg({ type: 'overseer_plan' }), t)).toBeNull()
    expect(getMessageTypeBadge(msg(), t)).toBeNull()
  })

  it('messageTypeOf prefers the top-level type', () => {
    expect(messageTypeOf(msg({ type: 'a', metadata: { display_type: 'b' } }))).toBe('a')
    expect(messageTypeOf(msg())).toBeUndefined()
  })
})
