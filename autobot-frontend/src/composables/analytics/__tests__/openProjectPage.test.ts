// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * The project page's open sequence stops at the first await the page did not survive (#21474).
 *
 * A source switch remounts the page while the previous page may still be opening. Each case
 * holds one awaited step open, leaves the page there, and checks that nothing after it ran.
 * Pre-fix (the inline `onMounted`): every later step ran regardless.
 */
import { describe, it, expect, vi } from 'vitest'
import { openProjectPage, type ProjectPageOpenSteps } from '../openProjectPage'

interface Held {
  wait: Promise<void>
  release: () => void
}
const held = (): Held => {
  let release!: () => void
  const wait = new Promise<void>((resolve) => { release = resolve })
  return { wait, release }
}

function steps(open: { value: boolean }, overrides: Partial<ProjectPageOpenSteps> = {}): ProjectPageOpenSteps {
  return {
    sourceId: 'source-a',
    pageOpen: () => open.value,
    leave: vi.fn(),
    beforeSourceLoad: vi.fn(),
    loadSourceById: vi.fn(async () => true),
    checkCurrentIndexingJob: vi.fn(async () => {}),
    loadPageResults: vi.fn(),
    ...overrides,
  }
}

describe('openProjectPage (#21474)', () => {
  it('an open page reads the source, checks the job, then reads the stored results', async () => {
    const s = steps({ value: true })
    await openProjectPage(s)
    expect(s.beforeSourceLoad).toHaveBeenCalledTimes(1)
    expect(s.loadSourceById).toHaveBeenCalledWith('source-a', s.pageOpen)
    expect(s.checkCurrentIndexingJob).toHaveBeenCalledTimes(1)
    expect(s.loadPageResults).toHaveBeenCalledTimes(1)
    expect(s.leave).not.toHaveBeenCalled()
  })

  it('left while the source was being read: no job check, no results, no redirect', async () => {
    const open = { value: true }
    const source = held()
    const s = steps(open, { loadSourceById: vi.fn(async () => { await source.wait; return false }) })

    const opening = openProjectPage(s)
    open.value = false
    source.release()
    await opening

    expect(s.checkCurrentIndexingJob).not.toHaveBeenCalled()
    expect(s.loadPageResults).not.toHaveBeenCalled()
    expect(s.leave).not.toHaveBeenCalled()
  })

  it('left while the indexing job was being checked: no results read', async () => {
    const open = { value: true }
    const job = held()
    const s = steps(open, { checkCurrentIndexingJob: vi.fn(() => job.wait) })

    const opening = openProjectPage(s)
    await vi.waitFor(() => expect(s.checkCurrentIndexingJob).toHaveBeenCalled())
    open.value = false
    job.release()
    await opening

    expect(s.loadPageResults).not.toHaveBeenCalled()
  })

  it('no source in the route, or a source that cannot be read on an open page, returns to the landing', async () => {
    const none = steps({ value: true }, { sourceId: undefined })
    await openProjectPage(none)
    expect(none.leave).toHaveBeenCalledTimes(1)
    expect(none.loadSourceById).not.toHaveBeenCalled()

    const unreadable = steps({ value: true }, { loadSourceById: vi.fn(async () => false) })
    await openProjectPage(unreadable)
    expect(unreadable.leave).toHaveBeenCalledTimes(1)
    expect(unreadable.checkCurrentIndexingJob).not.toHaveBeenCalled()
  })
})
