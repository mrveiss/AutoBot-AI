// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #22349: the pure upload helpers of useFileBrowserMutations.
import { describe, it, expect, vi } from 'vitest'
import { uploadFailureText, logUploaded } from '../file-browser/useFileBrowserMutations'

describe('uploadFailureText', () => {
  it('names each refused file with its reason', () => {
    const outcome = { uploaded: [], failed: [{ name: 'a', reason: 'big' }, { name: 'b', reason: 'bad' }] }
    expect(uploadFailureText(outcome as never, 'hint')).toBe('a: big; b: bad')
  })
  it('falls back to the hint when there is no outcome, and is empty when nothing failed', () => {
    expect(uploadFailureText(undefined as never, 'hint')).toBe('hint')
    expect(uploadFailureText({ uploaded: ['a'], failed: [] } as never, 'hint')).toBe('')
  })
})

describe('logUploaded', () => {
  it('logs only the stored files with their count and total size', () => {
    const log = vi.fn()
    const list = [new File(['xx'], 'a'), new File(['yyy'], 'b')] as unknown as FileList
    logUploaded({ uploaded: ['a'], failed: [] } as never, list, '/p', log)
    expect(log).toHaveBeenCalledWith('upload', '/p', { fileNames: 'a', fileCount: 1, totalSize: 2 })
  })
})
