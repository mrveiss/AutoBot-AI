// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useAiAnalysis.test.ts — transcriber AI-analysis SSE streaming.
 *
 * The composable streams an SSE response and accumulates `content`. It must
 * issue the request through the `fetchWithAuth` bridge (#12363 Phase 2) so the
 * JWT is attached, while keeping the raw `Response.body` reader available for
 * incremental parsing (no retrying/JSON-parsing convenience method).
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'

const fetchWithAuthMock = vi.fn()
vi.mock('@/utils/fetchWithAuth', () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args),
}))
vi.mock('@/config/ssot-config', () => ({
  getBackendUrl: () => '',
}))

let useAiAnalysis: typeof import('../useAiAnalysis')['useAiAnalysis']

/** Build a Response-like object whose body streams the given SSE chunks. */
function sseResponse(chunks: string[]): Response {
  const encoder = new TextEncoder()
  let i = 0
  return {
    body: {
      getReader() {
        return {
          read() {
            if (i < chunks.length) {
              return Promise.resolve({ done: false, value: encoder.encode(chunks[i++]) })
            }
            return Promise.resolve({ done: true, value: undefined })
          },
        }
      },
    },
  } as unknown as Response
}

beforeEach(async () => {
  fetchWithAuthMock.mockReset()
  vi.resetModules()
  ;({ useAiAnalysis } = await import('../useAiAnalysis'))
})

describe('useAiAnalysis', () => {
  it('streams SSE content through the auth bridge and accumulates it', async () => {
    fetchWithAuthMock.mockResolvedValue(
      sseResponse([
        'data: {"content":"Hello "}\n',
        'data: {"content":"world"}\n',
        'data: [DONE]\n',
      ]),
    )

    const { ask, content, streaming, activeAction } = useAiAnalysis(42)
    await ask({ action: 'summarize' })

    expect(fetchWithAuthMock).toHaveBeenCalledWith(
      '/api/transcriber/recordings/42/ai/ask',
      expect.objectContaining({ method: 'POST' }),
    )
    const opts = fetchWithAuthMock.mock.calls[0][1] as RequestInit
    expect(JSON.parse(opts.body as string)).toEqual({ action: 'summarize', custom_question: null })
    expect(content.value).toBe('Hello world')
    expect(streaming.value).toBe(false)
    expect(activeAction.value).toBe('summarize')
  })

  it('passes the custom question only for the custom action', async () => {
    fetchWithAuthMock.mockResolvedValue(sseResponse(['data: [DONE]\n']))

    const { ask } = useAiAnalysis(7)
    await ask({ action: 'custom', customQuestion: 'What happened?' })

    const opts = fetchWithAuthMock.mock.calls[0][1] as RequestInit
    expect(JSON.parse(opts.body as string)).toEqual({
      action: 'custom',
      custom_question: 'What happened?',
    })
  })

  it('surfaces an SSE error frame into content', async () => {
    fetchWithAuthMock.mockResolvedValue(
      sseResponse(['data: {"error":"boom"}\n']),
    )

    const { ask, content, streaming } = useAiAnalysis(1)
    await ask({ action: 'key_facts' })

    expect(content.value).toBe('Error: boom')
    expect(streaming.value).toBe(false)
  })

  it('reports a friendly message when the fetch rejects', async () => {
    fetchWithAuthMock.mockRejectedValue(new Error('network down'))

    const { ask, content, streaming } = useAiAnalysis(1)
    await ask({ action: 'protocol' })

    expect(content.value).toBe('Analysis failed. Please try again.')
    expect(streaming.value).toBe(false)
  })
})
