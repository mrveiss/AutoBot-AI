// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #20133: a user cancel aborts the in-flight upload, is announced once, and is never an error row.
import { describe, it, expect, vi } from 'vitest'
import { ConversationUploadError } from '@/utils/conversationFileUpload'
import { isUploadCancelled, useUploadCancel } from '@/composables/useUploadCancel'

const item = (id = 'u1') => ({ id, error: undefined as string | undefined })

describe('useUploadCancel (#20133)', () => {
  it('is cancellable only while in flight and not failed', () => {
    const { begin, settle, isCancellable } = useUploadCancel(vi.fn())
    const u = item()
    expect(isCancellable(u)).toBe(false)
    begin(u)
    expect(isCancellable(u)).toBe(true)
    settle(u)
    expect(isCancellable(u)).toBe(false)
    begin(u)
    u.error = 'x'
    expect(isCancellable(u)).toBe(false)
  })

  it('cancel aborts that upload only', () => {
    const { begin, cancel } = useUploadCancel(vi.fn())
    const a = begin(item('a'))
    const b = begin(item('b'))
    cancel('a')
    expect(a.aborted).toBe(true)
    expect(b.aborted).toBe(false)
  })

  it('settling a cancelled rejection reports the cancel; any other error does not', () => {
    const onCancelled = vi.fn()
    const { begin, settle } = useUploadCancel(onCancelled)
    const u = item()
    begin(u)
    expect(settle(u, new ConversationUploadError('network'))).toBe(false)
    expect(onCancelled).not.toHaveBeenCalled()
    begin(u)
    expect(settle(u, new ConversationUploadError('cancelled'))).toBe(true)
    expect(onCancelled).toHaveBeenCalledWith(u)
  })

  it('isUploadCancelled recognises only the cancelled code', () => {
    expect(isUploadCancelled(new ConversationUploadError('cancelled'))).toBe(true)
    expect(isUploadCancelled(new ConversationUploadError('http', 500))).toBe(false)
    expect(isUploadCancelled(new Error('cancelled'))).toBe(false)
  })
})
