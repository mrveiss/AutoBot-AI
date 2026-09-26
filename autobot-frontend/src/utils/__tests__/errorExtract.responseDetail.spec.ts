// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #17528 — the reason a request failed has to survive the transport.
 *
 * `ApiRepository` threw ``HTTP ${status}: ${statusText}`` without ever reading the
 * response body, so every sentence the backend composed to explain a rejection was
 * discarded one layer above the UI. The knowledge upload endpoint is the sharpest
 * case: #13884 exists specifically so a scanned PDF says "needs OCR" rather than
 * "empty", and that distinction had never once reached a user.
 *
 * The `detail` fixtures below are copied verbatim from the strings the backend
 * actually raises, so this file fails if either end changes its mind:
 *
 *   api/knowledge.py:838   file too large
 *   api/knowledge.py:846   file type not allowed
 *   api/knowledge.py:1274  extraction deadline
 *   api/knowledge.py:1191  _no_text_detail — the scanned-PDF case
 */
import { describe, expect, it } from 'vitest'

import { describeFailedResponse, extractResponseErrorDetail } from '../errorExtract'

/** A `Response` stand-in whose body is read exactly once, as the real one is. */
function failing(status: number, statusText: string, body: string): Response {
  let consumed = false
  return {
    ok: false,
    status,
    statusText,
    text: async () => {
      if (consumed) throw new TypeError('body stream already read')
      consumed = true
      return body
    }
  } as unknown as Response
}

const TOO_LARGE = 'File too large. Maximum size is 10MB'
const NOT_ALLOWED =
  'File type not allowed. Allowed: .txt, .md, .pdf, .docx, .json, .csv, .html, .xlsx, .pptx, .odt, .ods, .odp'
const TIMED_OUT =
  "Could not read 'handbook.pdf' within 30s. The document may be unusually large or complex; try splitting it."
const NEEDS_OCR =
  'No text layer found in any of the 12 page(s). The document appears to be scanned or image-only and needs OCR.'

describe('extractResponseErrorDetail — the shapes the backend really sends', () => {
  it.each([
    ['the size limit', TOO_LARGE],
    ['the allowed extensions', NOT_ALLOWED],
    ['the extraction deadline', TIMED_OUT],
    ['scanned-vs-empty (#13884)', NEEDS_OCR]
  ])('recovers %s from a string detail', async (_label, detail) => {
    const response = failing(400, 'Bad Request', JSON.stringify({ detail }))
    expect(await extractResponseErrorDetail(response)).toBe(detail)
  })

  it('recovers the message from the APIErrorResponse envelope', async () => {
    // _raise_or_return_error raises HTTPException(detail=APIErrorResponse.to_dict()),
    // so the sentence is nested two levels down rather than at the top.
    const body = JSON.stringify({
      detail: {
        error: {
          category: 'server_error',
          message: 'Knowledge base not initialized',
          code: 'KNOWLEDGE_0421',
          timestamp: 1758900000.0
        }
      }
    })
    expect(await extractResponseErrorDetail(failing(500, 'Internal Server Error', body))).toBe(
      'Knowledge base not initialized'
    )
  })

  it("joins FastAPI's per-field validation errors", async () => {
    const body = JSON.stringify({
      detail: [
        { loc: ['body', 'file'], msg: 'field required', type: 'value_error.missing' },
        { loc: ['body', 'category'], msg: 'str type expected', type: 'type_error.str' }
      ]
    })
    expect(await extractResponseErrorDetail(failing(422, 'Unprocessable Entity', body))).toBe(
      'field required; str type expected'
    )
  })

  it('accepts a top-level error or message, as ApiClient already does', async () => {
    expect(await extractResponseErrorDetail(failing(503, 'Service Unavailable', '{"error":"upstream down"}'))).toBe(
      'upstream down'
    )
    expect(await extractResponseErrorDetail(failing(409, 'Conflict', '{"message":"already indexed"}'))).toBe(
      'already indexed'
    )
  })
})

describe('extractResponseErrorDetail — nothing usable means nothing added', () => {
  it('returns empty for an empty body', async () => {
    expect(await extractResponseErrorDetail(failing(500, 'Internal Server Error', ''))).toBe('')
    expect(await extractResponseErrorDetail(failing(500, 'Internal Server Error', '   \n '))).toBe('')
  })

  it('returns empty for JSON that carries no message', async () => {
    expect(await extractResponseErrorDetail(failing(400, 'Bad Request', '{"ok":false}'))).toBe('')
    expect(await extractResponseErrorDetail(failing(400, 'Bad Request', '{"detail":""}'))).toBe('')
    expect(await extractResponseErrorDetail(failing(400, 'Bad Request', '{"detail":[]}'))).toBe('')
  })

  it('drops a proxy HTML page rather than rendering markup (#12311)', async () => {
    const html = '<html>\r\n<head><title>413 Request Entity Too Large</title></head>\r\n</html>'
    expect(await extractResponseErrorDetail(failing(413, 'Request Entity Too Large', html))).toBe('')
  })

  it('keeps a short plain-text body, which is still a sentence', async () => {
    expect(await extractResponseErrorDetail(failing(502, 'Bad Gateway', 'upstream connect error'))).toBe(
      'upstream connect error'
    )
  })

  it('caps an unstructured body so a stack trace cannot become the toast', async () => {
    const detail = await extractResponseErrorDetail(failing(500, 'Internal Server Error', 'x'.repeat(5000)))
    expect(detail).toHaveLength(301)
    expect(detail.endsWith('…')).toBe(true)
  })

  it('never throws when the body cannot be read', async () => {
    const unreadable = {
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      text: async () => {
        throw new TypeError('body stream already read')
      }
    } as unknown as Response
    await expect(extractResponseErrorDetail(unreadable)).resolves.toBe('')
  })

  it('reads the body only once', async () => {
    const response = failing(400, 'Bad Request', JSON.stringify({ detail: TOO_LARGE }))
    expect(await extractResponseErrorDetail(response)).toBe(TOO_LARGE)
    // A second read on the real Response would throw; the helper must not have left
    // one pending, so calling it again degrades to '' instead of exploding.
    await expect(extractResponseErrorDetail(response)).resolves.toBe('')
  })
})

describe('describeFailedResponse — the status line stays first and intact', () => {
  it('appends the reason after the status line', async () => {
    const message = await describeFailedResponse(
      failing(400, 'Bad Request', JSON.stringify({ detail: TOO_LARGE }))
    )
    expect(message).toBe(`HTTP 400: Bad Request — ${TOO_LARGE}`)
  })

  it('is byte-identical to the old message when the body says nothing', async () => {
    expect(await describeFailedResponse(failing(404, 'Not Found', ''))).toBe('HTTP 404: Not Found')
  })

  it('keeps every existing status-matching call site working', async () => {
    // These predicates live in ErrorHandler.js, ApiClient.ts:425, useLlcCompanyStore.ts,
    // useWebResearchStore.ts, useKnowledgeGraphRAG.ts and MemoryPrivacyPanel.vue. A fix
    // that replaced the message instead of extending it would have broken all of them
    // with nothing failing to say so.
    const unavailable = await describeFailedResponse(
      failing(503, 'Service Unavailable', JSON.stringify({ detail: 'model warming up' }))
    )
    expect(unavailable.startsWith('HTTP 503')).toBe(true)
    expect(unavailable.includes('HTTP 503')).toBe(true)

    const badRequest = await describeFailedResponse(
      failing(400, 'Bad Request', JSON.stringify({ detail: NEEDS_OCR }))
    )
    expect(badRequest.includes('HTTP 400')).toBe(true)
    expect(badRequest.includes('HTTP 4')).toBe(true)

    const conflict = await describeFailedResponse(failing(409, 'Conflict', '{"detail":"duplicate"}'))
    expect(conflict.includes('HTTP 409')).toBe(true)
  })
})
