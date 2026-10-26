// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest'
import { HttpError, isHttpError } from '../httpError'

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
