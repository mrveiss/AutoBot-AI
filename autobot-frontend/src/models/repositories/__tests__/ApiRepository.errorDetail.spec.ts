// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #17528 — an upload the backend refuses must say why it refused.
 *
 * `ApiRepository.request` used to throw the status line alone, so the four sentences
 * `POST /knowledge_base/upload` composes to explain a rejection died in transport and
 * `KnowledgeUpload.vue:302` rendered "HTTP 400: Bad Request" for all of them.
 *
 * These exercise the whole path a real upload takes — `KnowledgeRepository.addFileToKnowledge`
 * -> `ApiRepository.post` -> `request` -> throw — rather than the helper alone, because the
 * helper was never the part that was missing.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { KnowledgeRepository } from '../KnowledgeRepository'

vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/api'
}))

const fetchWithAuth = vi.fn()
vi.mock('@/utils/fetchWithAuth', () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuth(...args)
}))

/** What the server sends back when it rejects an upload. */
function rejection(status: number, statusText: string, detail: unknown): Response {
  return {
    ok: false,
    status,
    statusText,
    headers: new Headers({ 'content-type': 'application/json' }),
    text: async () => JSON.stringify({ detail })
  } as unknown as Response
}

const A_FILE = () => new File(['irrelevant'], 'handbook.pdf', { type: 'application/pdf' })

describe('a rejected knowledge upload reports the backend reason (#17528)', () => {
  let repo: KnowledgeRepository

  beforeEach(() => {
    fetchWithAuth.mockReset()
    repo = new KnowledgeRepository()
  })

  it.each([
    [400, 'Bad Request', 'File too large. Maximum size is 10MB'],
    [
      400,
      'Bad Request',
      'File type not allowed. Allowed: .txt, .md, .pdf, .docx, .json, .csv, .html, .xlsx, .pptx, .odt, .ods, .odp'
    ],
    [
      422,
      'Unprocessable Entity',
      "Could not read 'handbook.pdf' within 30s. The document may be unusually large or complex; try splitting it."
    ],
    [
      400,
      'Bad Request',
      'No text layer found in any of the 12 page(s). The document appears to be scanned or image-only and needs OCR.'
    ]
  ])('surfaces the %i detail to the caller', async (status, statusText, detail) => {
    fetchWithAuth.mockResolvedValue(rejection(status, statusText, detail))

    await expect(repo.addFileToKnowledge(A_FILE())).rejects.toThrow(detail)
  })

  it('puts the reason after the status line, not instead of it', async () => {
    const detail = 'File too large. Maximum size is 10MB'
    fetchWithAuth.mockResolvedValue(rejection(400, 'Bad Request', detail))

    await expect(repo.addFileToKnowledge(A_FILE())).rejects.toThrow(
      `HTTP 400: Bad Request — ${detail}`
    )
  })

  it('still throws the bare status line when the body explains nothing', async () => {
    fetchWithAuth.mockResolvedValue({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      headers: new Headers(),
      text: async () => ''
    } as unknown as Response)

    await expect(repo.addFileToKnowledge(A_FILE())).rejects.toThrow('HTTP 500: Internal Server Error')
  })

  it('leaves a successful upload untouched', async () => {
    fetchWithAuth.mockResolvedValue({
      ok: true,
      status: 200,
      statusText: 'OK',
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ success: true, document_id: 'fact-1', title: 'handbook.pdf', word_count: 4200 })
    } as unknown as Response)

    await expect(repo.addFileToKnowledge(A_FILE())).resolves.toMatchObject({
      success: true,
      document_id: 'fact-1',
      word_count: 4200
    })
  })
})
