// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// BatchJobsView (#20644): the Batch Processing screen moved from the SLM. Loading, a failed load and
// an empty list are three different screens; Retry runs the job again; a failed action is shown.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { computed, ref } from 'vue'
import en from '@/i18n/locales/en.json'

const { fake, confirmMock } = vi.hoisted(() => ({ fake: {} as Record<string, unknown>, confirmMock: vi.fn() }))

vi.mock('@/composables/useBatchProcessing', () => ({ useBatchProcessingState: () => fake }))
vi.mock('@/composables/useConfirmDialog', () => ({ useConfirmDialog: () => ({ confirm: confirmMock }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }),
}))
// The kit barrel pulls reka-ui; the screen's own behaviour is under test, so the kit is stubbed.
vi.mock('@autobot/ui', () => ({
  httpErrorText: (err: unknown, fallback: string) => (err instanceof Error && err.message ? err.message : fallback),
  formatDateTime: () => 'when',
  formatDuration: () => 'how long',
  PageHeader: { template: '<header><slot name="actions" /></header>' },
  BaseButton: { props: ['disabled', 'loading'], emits: ['click'], template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>' },
  BaseCard: { props: ['title', 'subtitle'], template: '<section><h3>{{ title }}</h3><slot name="actions" /><slot /></section>' },
  BaseBadge: { props: ['label'], template: '<span>{{ label }}</span>' },
  BaseAlert: { props: ['message'], template: '<p role="alert">{{ message }}</p>' },
  BaseSelectMenu: { props: ['modelValue', 'options', 'label'], template: '<select />' },
  BaseSpinner: { props: ['label'], template: '<span>{{ label }}</span>' },
  BaseModal: { props: ['modelValue', 'title'], template: '<div v-if="modelValue"><slot /><slot name="actions" /></div>' },
  BaseInput: { props: ['modelValue', 'label'], template: '<input />' },
  EmptyState: { props: ['title', 'description'], template: '<div><p>{{ title }}</p><p>{{ description }}</p><slot name="actions" /></div>' },
}))

import BatchJobsView from '../BatchJobsView.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

const job = (job_id: string, status: string) => ({
  job_id, name: `Job ${job_id}`, job_type: 'backup', status, progress: 40, parameters: {}, created_at: '2026-11-16T00:00:00Z',
})

function setState(view: string, jobs: unknown[] = [], error: unknown = null) {
  Object.assign(fake, {
    jobs: ref(jobs), jobsView: ref(view), error: ref(error), loading: ref(view === 'loading'),
    filter: ref({ status: undefined }), statusCounts: ref({ failed: 1, running: 2 }),
    pendingCount: computed(() => 0), runningCount: computed(() => 2), completedCount: computed(() => 0), failedCount: computed(() => 1),
    loadJobs: vi.fn(), setFilter: vi.fn(), startPolling: vi.fn(), stopPolling: vi.fn(),
    createJob: vi.fn(), runJob: vi.fn().mockResolvedValue({}), deleteJob: vi.fn().mockResolvedValue({}),
  })
}

const mountView = () => mount(BatchJobsView, { global: { plugins: [i18n] } })

describe('BatchJobsView (#20644)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows a loading state, not an empty list, before the first answer', () => {
    setState('loading')
    const text = mountView().text()
    expect(text).toContain('Loading batch jobs…')
    expect(text).not.toContain('No batch jobs yet')
  })

  it('shows a failed load as an error with the reason and a way to try again', async () => {
    setState('error', [], new Error('Redis service unavailable'))
    const wrapper = mountView()
    expect(wrapper.text()).toContain('Batch jobs could not be loaded')
    expect(wrapper.text()).toContain('Redis service unavailable')
    expect(wrapper.text()).not.toContain('No batch jobs yet')
    const retry = wrapper.findAll('button').find((b) => b.text() === 'Try again')!
    await retry.trigger('click')
    expect(fake.loadJobs).toHaveBeenCalled()
  })

  it('shows the empty state only for a successful empty answer', () => {
    setState('empty')
    expect(mountView().text()).toContain('No batch jobs yet')
  })

  it('lists the jobs with their counts and starts polling on mount', async () => {
    setState('ready', [job('a', 'running'), job('b', 'failed')])
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('Job a')
    expect(wrapper.text()).toContain('Job b')
    expect(wrapper.get('[data-testid="batch-counts"]').text()).toContain('3')
    expect(fake.startPolling).toHaveBeenCalled()
  })

  it('Retry on a failed job runs it again', async () => {
    setState('ready', [job('b', 'failed')])
    const wrapper = mountView()
    await wrapper.findAll('button').find((b) => b.text() === 'Retry')!.trigger('click')
    await flushPromises()
    expect(fake.runJob).toHaveBeenCalledWith('b')
  })

  it('a failed action is shown, not swallowed', async () => {
    setState('ready', [job('b', 'failed')])
    ;(fake.runJob as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('Job b not found'))
    const wrapper = mountView()
    await wrapper.findAll('button').find((b) => b.text() === 'Retry')!.trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="batch-action-error"]').text()).toBe('Job b not found')
  })

  it('removes a job only after the user confirms', async () => {
    setState('ready', [job('c', 'completed')])
    confirmMock.mockResolvedValueOnce(false).mockResolvedValueOnce(true)
    const wrapper = mountView()
    const remove = wrapper.findAll('button').find((b) => b.text() === 'Remove')!
    await remove.trigger('click')
    await flushPromises()
    expect(fake.deleteJob).not.toHaveBeenCalled()
    await remove.trigger('click')
    await flushPromises()
    expect(fake.deleteJob).toHaveBeenCalledWith('c')
  })
})
