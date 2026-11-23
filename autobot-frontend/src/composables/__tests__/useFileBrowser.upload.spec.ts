// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #22015: one request per file, field `file`, and the server's reason for a refusal reaches the caller.
import { beforeEach, describe, expect, it, vi } from 'vitest'

const fetchWithAuth = vi.hoisted(() => vi.fn())
vi.mock('@/utils/fetchWithAuth', () => ({ fetchWithAuth }))
vi.mock('@/utils/ApiClient', () => ({ default: {} }))
vi.mock('@/config/ssot-config', () => ({ getApiBase: () => '/api' }))
vi.mock('@/i18n', () => ({ default: { global: { t: (key: string) => key } } }))

import { useFileBrowser, UPLOAD_FORM_FIELDS } from '../file-browser/useFileBrowser'

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const selection = (...names: string[]) => names.map((n) => new File(['x'], n)) as unknown as FileList

describe('useFileBrowser.uploadFiles', () => {
  beforeEach(() => fetchWithAuth.mockReset())

  it('sends each file as its own request with the route field names', async () => {
    fetchWithAuth.mockResolvedValue(json(200, { success: true }))
    const outcome = await useFileBrowser().uploadFiles(selection('a.txt', 'b.txt'), 'docs')
    expect(fetchWithAuth).toHaveBeenCalledTimes(2)
    const form = fetchWithAuth.mock.calls[0][1].body as FormData
    expect([...form.keys()].sort()).toEqual(Object.values(UPLOAD_FORM_FIELDS).sort())
    expect(form.get('path')).toBe('docs')
    expect(form.get('overwrite')).toBe('false')
    expect(outcome).toEqual({ uploaded: ['a.txt', 'b.txt'], failed: [] })
  })

  it.each([
    [413, 'File too large. Maximum size: 50MB'],
    [400, 'File type not allowed: run.exe'],
  ])('reports the server reason for a %i and keeps uploading the rest', async (status, detail) => {
    fetchWithAuth.mockResolvedValueOnce(json(status, { detail })).mockResolvedValueOnce(json(200, {}))
    const outcome = await useFileBrowser().uploadFiles(selection('bad.bin', 'ok.txt'), 'docs')
    expect(outcome).toEqual({ uploaded: ['ok.txt'], failed: [{ name: 'bad.bin', reason: detail }] })
  })

  it('maps a 409 to the translated already-exists text, not the overwrite=true API text', async () => {
    fetchWithAuth.mockResolvedValue(json(409, { detail: 'File already exists. Use overwrite=true to replace it.' }))
    const outcome = await useFileBrowser().uploadFiles(selection('a.txt'), 'docs')
    expect(outcome?.failed).toEqual([{ name: 'a.txt', reason: 'fileBrowser.browser.uploadAlreadyExists' }])
  })

  it('falls back to the translated hint when the body carries no reason', async () => {
    fetchWithAuth.mockResolvedValue(new Response('<html>bad gateway</html>', { status: 502 }))
    const outcome = await useFileBrowser().uploadFiles(selection('a.txt'), 'docs')
    expect(outcome?.failed).toEqual([{ name: 'a.txt', reason: 'fileBrowser.browser.uploadFailedHint' }])
  })
})
