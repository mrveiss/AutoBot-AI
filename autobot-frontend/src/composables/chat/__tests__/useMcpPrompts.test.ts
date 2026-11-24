// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Behaviour parity for the MCP prompt picker's state, moved out of McpPromptPicker.vue (#18243): every
 * bridge is listed, a required parameter blocks the insert, and a rendered prompt becomes draft text.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/plugins/api', () => ({ useApiClient: () => api }))

import { MCP_BRIDGES, promptDraftText, useMcpPrompts } from '../useMcpPrompts'

beforeEach(() => {
  api.get.mockReset()
  api.post.mockReset()
})

describe('promptDraftText', () => {
  it('joins the non-empty messages with a blank line', () => {
    const text = promptDraftText({
      messages: [
        { role: 'user', content: { type: 'text', text: 'first' } },
        { role: 'user', content: '   ' },
        { role: 'user', content: 'second' },
      ],
    })
    expect(text).toBe('first\n\nsecond')
  })

  it('reads an array content as its strings and texts, newline separated', () => {
    expect(promptDraftText({ messages: [{ role: 'user', content: ['a', { text: 'b' }] }] })).toBe('a\nb')
  })
})

describe('useMcpPrompts', () => {
  it('loads the prompts of every bridge, and an unreachable bridge is empty rather than fatal', async () => {
    api.get.mockImplementation(async (url: string) => {
      if (url.includes('/knowledge/')) throw new Error('down')
      return { prompts: [{ name: url }] }
    })
    const m = useMcpPrompts()
    await m.loadPrompts()
    expect(api.get).toHaveBeenCalledTimes(MCP_BRIDGES.length)
    expect(m.promptsByBridge.value.git).toHaveLength(1)
    expect(m.promptsByBridge.value.knowledge).toEqual([])
    expect(m.loading.value).toBe(false)
    expect(m.error.value).toBeNull()
  })

  it('selecting a prompt starts its form empty', () => {
    const m = useMcpPrompts()
    m.selectPrompt({ name: 'p', arguments: [{ name: 'path', required: true }, { name: 'ref' }] })
    expect(m.formValues.value).toEqual({ path: '', ref: '' })
  })

  it('refuses to render while a required parameter is blank, naming it', async () => {
    const m = useMcpPrompts()
    m.selectPrompt({ name: 'p', arguments: [{ name: 'path', required: true }] })
    expect(await m.renderSelected()).toBeNull()
    expect(m.formError.value).toEqual({ key: 'chat.mcpPrompts.requiredParam', params: { name: 'path' } })
    expect(api.post).not.toHaveBeenCalled()
  })

  it('renders through the active bridge with the filled arguments', async () => {
    api.post.mockResolvedValue({ messages: [{ role: 'user', content: 'Review src/a.ts' }] })
    const m = useMcpPrompts()
    m.activeBridge.value = 'filesystem'
    m.selectPrompt({ name: 'review', arguments: [{ name: 'path', required: true }] })
    m.formValues.value.path = 'src/a.ts'
    expect(await m.renderSelected()).toBe('Review src/a.ts')
    expect(api.post).toHaveBeenCalledWith('/api/filesystem/mcp/prompts/get', { name: 'review', arguments: { path: 'src/a.ts' } })
    expect(m.insertLoading.value).toBe(false)
  })

  it('reports a failed render as a locale key and keeps the form', async () => {
    api.post.mockRejectedValue(new Error('500'))
    const m = useMcpPrompts()
    m.selectPrompt({ name: 'p' })
    expect(await m.renderSelected()).toBeNull()
    expect(m.formError.value).toEqual({ key: 'chat.mcpPrompts.insertFailed' })
    expect(m.selectedPrompt.value?.name).toBe('p')
  })

  it('reset leaves the form', () => {
    const m = useMcpPrompts()
    m.selectPrompt({ name: 'p' })
    m.reset()
    expect(m.selectedPrompt.value).toBeNull()
  })
})
