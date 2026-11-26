// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #21628: the wrapper declared a `timeout` prop and never read it, so a chunk load that never settled
// waited forever. A load slower than `timeout` now fails into the retry loop, like a rejected load.

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import AsyncComponentWrapper from '../AsyncComponentWrapper.vue'

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

const Loaded = defineComponent({ name: 'Loaded', render: () => h('p', { 'data-testid': 'loaded' }, 'ready') })

const neverSettles = () => new Promise<never>(() => undefined)

function mountWith(loader: () => Promise<unknown>, extra: Record<string, unknown> = {}) {
  return mount(AsyncComponentWrapper, {
    props: { componentLoader: loader as never, componentName: 'Slow', timeout: 500, retryDelay: 10, ...extra },
    global: { stubs: { AsyncErrorFallback: true, BaseSpinner: true } },
  })
}

describe('AsyncComponentWrapper timeout (#21628)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('a load that never settles ends in the error state once the timeout passes', async () => {
    const wrapper = mountWith(neverSettles, { maxRetries: 1 })
    await vi.advanceTimersByTimeAsync(499)
    expect(wrapper.emitted('error')).toBeUndefined()

    await vi.advanceTimersByTimeAsync(2)

    const errors = wrapper.emitted('error') ?? []
    expect(errors).toHaveLength(1)
    expect((errors[0][0] as Error).message).toContain('timed out after 500ms')
  })

  it('a timed-out load goes through the retry loop up to maxRetries', async () => {
    const loader = vi.fn(neverSettles)
    const wrapper = mountWith(loader, { maxRetries: 2 })

    await vi.advanceTimersByTimeAsync(501)
    expect(wrapper.emitted('retry')).toEqual([[2]])
    expect(wrapper.emitted('error')).toBeUndefined()

    await vi.advanceTimersByTimeAsync(10_000)
    expect(loader).toHaveBeenCalledTimes(2)
    expect(wrapper.emitted('error')).toHaveLength(1)
  })

  it('a load that finishes before the timeout is unaffected and leaves no deadline timer', async () => {
    const wrapper = mountWith(() => Promise.resolve({ default: Loaded }), { maxRetries: 1 })
    await vi.advanceTimersByTimeAsync(0)

    expect(wrapper.emitted('loaded')).toHaveLength(1)
    await vi.advanceTimersByTimeAsync(5_000)
    expect(wrapper.emitted('error')).toBeUndefined()
    expect(wrapper.emitted('retry')).toBeUndefined()
  })
})
