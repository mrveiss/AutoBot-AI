// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// TOOL_CALL detection (disabled as a watcher, kept reachable): the session id may sit on a recent chunk.
import { describe, it, expect, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { findTerminalSessionId, useToolCallDetection } from '../useToolCallDetection'
import type { ChatMessage } from '@/stores/useChatStore'

const msg = (id: string, over: Record<string, unknown> = {}) =>
  ({ id, sender: 'assistant', content: '', timestamp: 't', ...over }) as unknown as ChatMessage

describe('findTerminalSessionId', () => {
  it('uses the message own id first, then the latest recent assistant chunk that has one', () => {
    expect(findTerminalSessionId(msg('1', { metadata: { terminal_session_id: 'own' } }), [])).toBe('own')
    const recent = [msg('a', { metadata: { terminal_session_id: 'old' } }), msg('b', { metadata: { terminal_session_id: 'new' } }), msg('c')]
    expect(findTerminalSessionId(msg('x'), recent)).toBe('new')
  })

  it('is null when nothing carries one', () => {
    expect(findTerminalSessionId(msg('x'), [msg('a')])).toBeNull()
  })
})

describe('useToolCallDetection', () => {
  it('emits one call per marker with host defaulting to main', () => {
    setActivePinia(createPinia())
    const emit = vi.fn()
    const { detectToolCalls } = useToolCallDetection(emit)
    const content = '<TOOL_CALL name="execute_command" params=\'{"command":"ls"}\'>list files</TOOL_CALL>'
    detectToolCalls(msg('1', { content, metadata: { terminal_session_id: 's1' } }))
    expect(emit).toHaveBeenCalledWith({
      command: 'ls', host: 'main', purpose: 'list files', params: { command: 'ls' }, terminal_session_id: 's1',
    })
  })
})
