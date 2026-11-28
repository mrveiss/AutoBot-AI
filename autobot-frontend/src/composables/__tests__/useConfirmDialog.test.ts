// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * #20756: the dialog is a module singleton with one resolver, so an overlapping confirm()
 * must settle the confirmation it replaces rather than orphan its promise.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { useConfirmDialog, _resetForTests } from '../useConfirmDialog'

const opts = (title: string) => ({ title, message: title })

beforeEach(() => _resetForTests())

describe('useConfirmDialog', () => {
  it('resolves the awaiting caller with the answer and closes the dialog', async () => {
    const { confirm, _resolve, dialogVisible } = useConfirmDialog()
    const answer = confirm(opts('one'))
    expect(dialogVisible.value).toBe(true)
    _resolve(true)
    await expect(answer).resolves.toBe(true)
    expect(dialogVisible.value).toBe(false)
  })

  it('settles the replaced confirmation with false when a second confirm overlaps it (#20756)', async () => {
    const { confirm, _resolve, dialogOptions } = useConfirmDialog()
    const first = confirm(opts('first'))
    const second = confirm(opts('second'))
    expect(dialogOptions.value?.title).toBe('second')
    await expect(first).resolves.toBe(false)
    _resolve(true)
    await expect(second).resolves.toBe(true)
  })

  it('a dismissed overlapping dialog still settles both promises (#20756)', async () => {
    const { confirm, _resolve } = useConfirmDialog()
    const first = confirm(opts('first'))
    const second = confirm(opts('second'))
    _resolve(false)
    await expect(Promise.all([first, second])).resolves.toEqual([false, false])
  })
})
