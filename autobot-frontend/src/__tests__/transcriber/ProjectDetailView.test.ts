// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { h } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import ProjectDetailView from '@/views/transcriber/ProjectDetailView.vue'

// --- API mock ---------------------------------------------------------------
const getProject = vi.fn()
const listRecordings = vi.fn()
const getRecording = vi.fn()
const deleteRecording = vi.fn()

vi.mock('@/composables/transcriber/useTranscriberApi', () => ({
  useTranscriberApi: () => ({ getProject, listRecordings, getRecording, deleteRecording }),
}))

// --- router mock ------------------------------------------------------------
const push = vi.fn()
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: '1' } }),
  useRouter: () => ({ push }),
}))

// Stub child components — ProcessingProgress opens an EventSource (SSE),
// UploadModal teleports; we only assert wiring here.
const UploadModalStub = {
  name: 'UploadModal',
  props: ['projectId', 'open'],
  emits: ['close', 'uploaded'],
  setup() {
    return () => h('div', { class: 'upload-modal-stub' })
  },
}
const ProcessingProgressStub = {
  name: 'ProcessingProgress',
  props: ['recordingId'],
  emits: ['complete', 'error'],
  setup() {
    return () => h('div', { class: 'processing-progress-stub' })
  },
}

function recording(id: number, status: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    project_id: 1,
    filename: `rec-${id}.mp3`,
    duration: 65,
    status,
    speaker_count: 0,
    process_seconds: null,
    engine_used: null,
    language_detected: null,
    uploaded_at: '2026-01-02T00:00:00Z',
    failure_stage: null,
    failure_reason: null,
    ...extra,
  }
}

function mountView() {
  return mount(ProjectDetailView, {
    global: {
      plugins: [createPinia()],
      stubs: { UploadModal: UploadModalStub, ProcessingProgress: ProcessingProgressStub },
    },
  })
}

describe('ProjectDetailView.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    getProject.mockResolvedValue({ id: 1, name: 'Interviews', description: 'Q3', created_at: '', user_id: 'u1' })
    listRecordings.mockResolvedValue([recording(10, 'complete'), recording(11, 'processing')])
    getRecording.mockResolvedValue(recording(11, 'complete'))
    deleteRecording.mockResolvedValue(undefined)
    push.mockClear()
  })

  it('loads the project and its recordings', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(getProject).toHaveBeenCalledWith(1)
    expect(listRecordings).toHaveBeenCalledWith(1)
    expect(wrapper.text()).toContain('Interviews')
    expect(wrapper.findAll('.recording-card')).toHaveLength(2)
  })

  it('renders ProcessingProgress only for in-progress recordings', async () => {
    const wrapper = mountView()
    await flushPromises()

    // recording 11 is "processing" → one progress bar.
    expect(wrapper.findAllComponents(ProcessingProgressStub)).toHaveLength(1)
  })

  it('formats duration as m:ss', async () => {
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('1:05')
  })

  it('navigates to the transcript for a complete recording', async () => {
    const wrapper = mountView()
    await flushPromises()

    // The first card (recording 10, complete) has an enabled "View transcript".
    const viewBtn = wrapper.findAll('.recording-card')[0].find('.recording-actions .btn')
    expect(viewBtn.attributes('disabled')).toBeUndefined()
    await viewBtn.trigger('click')

    expect(push).toHaveBeenCalledWith({
      name: 'transcriber-transcript',
      params: { projectId: '1', recordingId: '10' },
    })
  })

  it('disables "View transcript" while a recording is still processing', async () => {
    const wrapper = mountView()
    await flushPromises()

    const processingBtn = wrapper.findAll('.recording-card')[1].find('.recording-actions .btn')
    expect(processingBtn.attributes('disabled')).toBeDefined()
  })

  it('prepends an uploaded recording to the list', async () => {
    const wrapper = mountView()
    await flushPromises()

    await wrapper.findComponent(UploadModalStub).vm.$emit('uploaded', recording(99, 'pending'))
    await flushPromises()

    const cards = wrapper.findAll('.recording-card')
    expect(cards).toHaveLength(3)
    expect(cards[0].text()).toContain('rec-99.mp3')
  })

  it('refreshes a recording when processing completes', async () => {
    const wrapper = mountView()
    await flushPromises()

    await wrapper.findComponent(ProcessingProgressStub).vm.$emit('complete')
    await flushPromises()

    expect(getRecording).toHaveBeenCalledWith(11)
  })
})
