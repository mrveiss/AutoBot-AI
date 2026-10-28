// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest'
import { HttpError, extractErrorInfo, httpErrorFrom, isHttpClientError, isHttpError, parseJsonBody } from '../httpError'

describe('HttpError', () => {
  it('keeps the message every existing check reads, and adds status and details', () => {
    const e = new HttpError(404, 'Not found', { detail: 'No such node' })
    expect(e).toBeInstanceOf(Error)
    expect(e.message).toBe('HTTP 404: Not found')
    expect(e.message.includes('HTTP 4')).toBe(true)
    expect(e.status).toBe(404)
    expect(e.details).toEqual({ detail: 'No such node' })
    expect(e.detail).toBe('No such node')
  })

  it('reads a structured detail as JSON and a missing one as null', () => {
    expect(new HttpError(422, 'x', { detail: [{ loc: ['body'], msg: 'bad' }] }).detail).toBe('[{"loc":["body"],"msg":"bad"}]')
    expect(new HttpError(500, 'x').detail).toBeNull()
  })

  it('narrows only real HttpErrors', () => {
    expect(isHttpError(new HttpError(500, 'x'))).toBe(true)
    expect(isHttpError(new Error('HTTP 500: x'))).toBe(false)
    expect(isHttpError(null)).toBe(false)
  })
})

const res = (status: number, body: string | null, type = 'application/json', statusText = '') =>
  new Response(body, { status, statusText, headers: type ? { 'content-type': type } : {} })

describe('HttpError message without a status text', () => {
  it('renders a bare status for an empty message', () => {
    expect(new HttpError(502, '').message).toBe('HTTP 502')
  })
  it('renders a bare status for an undefined message', () => {
    expect(new HttpError(502, undefined).message).toBe('HTTP 502')
  })
})

describe('isHttpClientError', () => {
  it('is true for 4xx HttpErrors only', () => {
    expect(isHttpClientError(new HttpError(404, 'x'))).toBe(true)
    expect(isHttpClientError(new HttpError(500, 'x'))).toBe(false)
    expect(isHttpClientError(new Error('HTTP 404: x'))).toBe(false)
  })
})

describe('extractErrorInfo / httpErrorFrom', () => {
  it('takes error, then message, then detail from a JSON body', async () => {
    expect((await extractErrorInfo(res(400, '{"error":"e","detail":"d"}'))).message).toBe('e')
    expect((await extractErrorInfo(res(400, '{"message":"m"}'))).message).toBe('m')
    expect((await extractErrorInfo(res(422, '{"detail":[{"msg":"bad"}]}'))).message).toBe('[{"msg":"bad"}]')
    expect((await extractErrorInfo(res(400, '{"other":1}'))).message).toBe('{"other":1}')
  })

  it('falls back to statusText with no details when the body is not JSON', async () => {
    expect(await extractErrorInfo(res(502, 'gateway down', 'text/plain', 'Bad Gateway'))).toEqual({
      status: 502,
      message: 'Bad Gateway',
      details: null,
    })
  })

  it('builds the HttpError a client throws', async () => {
    const e = await httpErrorFrom(res(404, '{"detail":"No such node"}'))
    expect(e.message).toBe('HTTP 404: No such node')
    expect(e.status).toBe(404)
    expect(e.detail).toBe('No such node')
  })
})

describe('parseJsonBody', () => {
  it('reads JSON, and a 204 or non-JSON body as {}', async () => {
    expect(await parseJsonBody(res(200, '{"a":1}'))).toEqual({ a: 1 })
    expect(await parseJsonBody(res(204, null, ''))).toEqual({})
    expect(await parseJsonBody(res(200, 'ok', 'text/plain'))).toEqual({})
  })
})
