// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #20254: the panel shows the log's position and keeps polling through the SLM's restart.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en.json'
import slmApiClient from '@/utils/ApiClient'
import UpdateProgressPanel from './UpdateProgressPanel.vue'

vi.mock('@/utils/ApiClient', () => ({ default: { get: vi.fn() } }))

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const get = vi.mocked(slmApiClient.get)
const running = {
  state: 'running',
  play: 'second',
  task: 'install deps',
  last_line_at: '2026-10-31T10:29:55+00:00',
  elapsed_seconds: 1800,
}

function mountPanel(active = true) {
  return mount(UpdateProgressPanel, { props: { active, since: 'T' }, global: { plugins: [i18n] } })
}

describe('UpdateProgressPanel', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    get.mockReset()
  })
  afterEach(() => vi.useRealTimers())

  it('shows the play, task, elapsed time and that a pause is not a failure', async () => {
    get.mockResolvedValue(running)
    const text = (await (async () => {
      const w = mountPanel()
      await flushPromises()
      return w
    })()).text()
    expect(text).toContain('install deps')
    expect(text).toContain('second')
    expect(text).toContain('30 min')
    expect(text).toContain('does not mean it failed')
    expect(get).toHaveBeenCalledWith('/code-sync/update-all/progress?since=T')
  })

  it.each([
    ['quiet', 'still running'],
    ['exited_without_recap', 'stopped without finishing'],
    ['unknown', 'Could not tell'],
    ['waiting', 'Waiting for the update'],
  ])('states %s', async (state, words) => {
    get.mockResolvedValue({ ...running, state })
    const w = mountPanel()
    await flushPromises()
    expect(w.get('[data-testid="update-progress-state"]').text()).toContain(words)
  })

  it('keeps polling through a failed request, as the SLM restarts', async () => {
    get.mockRejectedValueOnce(new Error('502')).mockResolvedValue(running)
    const w = mountPanel()
    await flushPromises()
    expect(w.find('[data-testid="update-progress"]').exists()).toBe(false)
    await vi.advanceTimersByTimeAsync(5000)
    await flushPromises()
    expect(w.text()).toContain('install deps')
  })

  it('does not poll while inactive, and stops when the run ends', async () => {
    mountPanel(false)
    await flushPromises()
    expect(get).not.toHaveBeenCalled()
    get.mockResolvedValue(running)
    const w = mountPanel()
    await flushPromises()
    await w.setProps({ active: false })
    get.mockClear()
    await vi.advanceTimersByTimeAsync(20000)
    expect(get).not.toHaveBeenCalled()
  })
})
