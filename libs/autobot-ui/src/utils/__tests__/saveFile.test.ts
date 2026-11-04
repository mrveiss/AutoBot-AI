// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { saveBlob, saveTextFile, saveUrl } from '../saveFile'

let clicked: Array<{ href: string; download: string; attached: boolean }>

beforeEach(() => {
  clicked = []
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    clicked.push({ href: this.href, download: this.download, attached: document.body.contains(this) })
  })
  URL.createObjectURL = vi.fn(() => 'blob:mock-1')
  URL.revokeObjectURL = vi.fn()
})

afterEach(() => vi.restoreAllMocks())

describe('saveFile (#20770)', () => {
  it('saves a blob through an attached anchor, then removes the anchor and revokes the URL', () => {
    const blob = new Blob(['x'], { type: 'text/csv' })
    saveBlob(blob, 'report.csv')
    expect(URL.createObjectURL).toHaveBeenCalledWith(blob)
    expect(clicked).toEqual([{ href: 'blob:mock-1', download: 'report.csv', attached: true }])
    expect(document.querySelectorAll('a').length).toBe(0)
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:mock-1')
  })

  it('saves text with the MIME type given, text/plain by default', () => {
    saveTextFile('{"a":1}', 'data.json', 'application/json')
    saveTextFile('log line', 'session.log')
    const blobs = vi.mocked(URL.createObjectURL).mock.calls.map(([b]) => b as Blob)
    expect(blobs.map((b) => b.type)).toEqual(['application/json', 'text/plain'])
    expect(clicked.map((c) => c.download)).toEqual(['data.json', 'session.log'])
  })

  it('saves a URL it did not create without revoking it', () => {
    saveUrl('data:image/png;base64,AAAA', 'timeline.png')
    expect(clicked).toEqual([{ href: 'data:image/png;base64,AAAA', download: 'timeline.png', attached: true }])
    expect(URL.revokeObjectURL).not.toHaveBeenCalled()
  })

  it('still removes the anchor and revokes the URL when the click throws', () => {
    vi.mocked(HTMLAnchorElement.prototype.click).mockImplementation(() => {
      throw new Error('blocked')
    })
    expect(() => saveBlob(new Blob(['x']), 'x.txt')).toThrow('blocked')
    expect(document.querySelectorAll('a').length).toBe(0)
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:mock-1')
  })
})
