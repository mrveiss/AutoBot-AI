// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ProjectDetailView from '@/views/transcriber/ProjectDetailView.vue'

// --- API mock ---------------------------------------------------------------
const getProject = vi.fn()
const listRecordings = vi.fn()
const uploadRecording = vi.fn()
const deleteRecording = vi.fn()

// mockReset:true wipes factories — re-apply implementations in beforeEach.
vi.mock('@/composables/transcriber/useTranscriberApi', () => ({
  useTranscriberApi: () => ({ getProject, listRecordings, uploadRecording, deleteRecording }),
}))

const push = vi.fn()
// projectId resolves to 1 via the stubbed route.
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: '1' } }),
  useRouter: () => ({ push }),
}))

function recording(id: number, status: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    project_id: 1,
    filename: `rec-${id}.mp3`,
    duration: 65,
    status,
    speaker_count: 2,
    process_seconds: null,
    engine_used: null,
    language_detected: 'en',
    uploaded_at: '2026-06-18T00:00:00Z',
    failure_stage: null,
    failure_reason: null,
    ...extra,
  }
}

const RouterLinkStub = {
  name: 'RouterLink',
  props: ['to'],
  template: '<a class="router-link-stub"><slot /></a>',
}

function mountView() {
  return mount(ProjectDetailView, {
    global: { stubs: { RouterLink: RouterLinkStub } },
  })
}

describe('ProjectDetailView.vue', () => {
  beforeEach(() => {
    getProject.mockResolvedValue({
      id: 1,
      name: 'My Project',
      description: 'A description',
      created_at: '2026-06-18T00:00:00Z',
      user_id: 'u1',
    })
    listRecordings.mockResolvedValue([recording(10, 'complete')])
    uploadRecording.mockResolvedValue(recording(11, 'pending'))
    deleteRecording.mockResolvedValue(undefined)
    push.mockClear()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
  })

  it('loads the project header and recordings on mount', async () => {
    const wrapper = mountView()
    await flushPromises()
    expect(getProject).toHaveBeenCalledWith(1)
    expect(listRecordings).toHaveBeenCalledWith(1)
    expect(wrapper.find('.detail-title').text()).toBe('My Project')
    expect(wrapper.findAll('.recording-card')).toHaveLength(1)
  })

  it('shows the empty state when there are no recordings', async () => {
    listRecordings.mockResolvedValue([])
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.find('.recordings-list').exists()).toBe(false)
    expect(wrapper.text()).toContain('No recordings yet')
  })

  it('shows an error state when loading fails', async () => {
    getProject.mockRejectedValue(new Error('boom'))
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.find('.detail-error').exists()).toBe(true)
  })

  it('uploads a selected file and prepends the new recording', async () => {
    const wrapper = mountView()
    await flushPromises()

    const file = new File(['data'], 'audio.wav', { type: 'audio/wav' })
    const input = wrapper.find('.upload-input')
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change')
    await flushPromises()

    expect(uploadRecording).toHaveBeenCalledWith(1, file)
    expect(wrapper.findAll('.recording-card')).toHaveLength(2)
    expect(wrapper.findAll('.recording-filename')[0].text()).toBe('rec-11.mp3')
  })

  it('surfaces an upload error', async () => {
    uploadRecording.mockRejectedValue(new Error('nope'))
    const wrapper = mountView()
    await flushPromises()

    const file = new File(['data'], 'audio.wav', { type: 'audio/wav' })
    const input = wrapper.find('.upload-input')
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change')
    await flushPromises()

    expect(wrapper.find('.detail-error').exists()).toBe(true)
  })

  it('refreshes recordings via the Refresh button', async () => {
    const wrapper = mountView()
    await flushPromises()
    listRecordings.mockClear()
    const refresh = wrapper.findAll('.btn-secondary')
    await refresh[refresh.length - 1].trigger('click')
    await flushPromises()
    expect(listRecordings).toHaveBeenCalledWith(1)
  })

  it('navigates to the transcript view for a completed recording', async () => {
    const wrapper = mountView()
    await flushPromises()
    await wrapper.find('.recording-clickable').trigger('click')
    expect(push).toHaveBeenCalledWith({
      name: 'transcriber-transcript',
      params: { projectId: 1, recordingId: 10 },
    })
  })

  it('shows in-progress text and no transcript link while processing', async () => {
    listRecordings.mockResolvedValue([recording(20, 'processing')])
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.find('.recording-clickable').exists()).toBe(false)
    expect(wrapper.text()).toContain('Transcription in progress')
  })

  it('shows the failure reason for an errored recording', async () => {
    listRecordings.mockResolvedValue([
      recording(30, 'error', { failure_reason: 'Audio too short' }),
    ])
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.find('.recording-clickable').exists()).toBe(false)
    expect(wrapper.text()).toContain('Audio too short')
  })

  it('deletes a recording after confirmation', async () => {
    const wrapper = mountView()
    await flushPromises()
    await wrapper.find('.btn-danger').trigger('click')
    await flushPromises()
    expect(deleteRecording).toHaveBeenCalledWith(10)
    expect(wrapper.findAll('.recording-card')).toHaveLength(0)
  })
})
