// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { h } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import TranscriptView from '@/views/transcriber/TranscriptView.vue'

// --- API mock ---------------------------------------------------------------
const getRecording = vi.fn()
const getTranscript = vi.fn()
const getWaveform = vi.fn()
const audioChunksUrl = vi.fn()

// mockReset:true wipes factories — re-apply implementations in beforeEach.
vi.mock('@/composables/transcriber/useTranscriberApi', () => ({
  useTranscriberApi: () => ({
    getRecording,
    getTranscript,
    getWaveform,
    audioChunksUrl,
    updateSegment: vi.fn(),
    updateSpeaker: vi.fn(),
  }),
}))

// Stub the route so recordingId resolves to 7.
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { recordingId: '7' } }),
}))

// Stub WaveformPlayer (it dynamically imports wavesurfer.js in jsdom).
const seekTo = vi.fn()
const WaveformPlayerStub = {
  name: 'WaveformPlayer',
  props: ['audioUrl', 'peaks'],
  emits: ['seek'],
  setup(_props: unknown, { expose }: { expose: (e: Record<string, unknown>) => void }) {
    expose({ seekTo })
    return () => h('div', { class: 'waveform-player-stub' })
  },
}

const SegmentTableStub = {
  name: 'SegmentTable',
  props: ['segments', 'speakers', 'currentTime'],
  emits: ['seek'],
  template: '<div class="segment-table-stub" :data-current-time="currentTime" />',
}

function mountView() {
  return mount(TranscriptView, {
    global: {
      plugins: [createPinia()],
      stubs: {
        WaveformPlayer: WaveformPlayerStub,
        SegmentTable: SegmentTableStub,
      },
    },
  })
}

const SEGMENTS = [
  { id: 1, recording_id: 7, speaker_id: 1, start_time: 0, end_time: 5, text: 'Hello', original_text: 'Hello', is_edited: false, is_overlap: false },
  { id: 2, recording_id: 7, speaker_id: 2, start_time: 5, end_time: 10, text: 'World', original_text: 'World', is_edited: false, is_overlap: false },
]
const SPEAKERS = [
  { id: 1, recording_id: 7, label: 'A', display_name: 'Alice', language: null },
  { id: 2, recording_id: 7, label: 'B', display_name: 'Bob', language: null },
]

function completeRecording() {
  return { id: 7, project_id: 1, filename: 'a.mp3', duration: 10, status: 'complete', speaker_count: 2, process_seconds: 3, engine_used: 'whisper', language_detected: 'en', uploaded_at: '', failure_stage: null, failure_reason: null }
}

describe('TranscriptView.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    // Re-apply mock implementations (mockReset wipes them).
    audioChunksUrl.mockReturnValue('http://backend/api/transcriber/recordings/7/audio/chunks')
    getWaveform.mockResolvedValue({ recording_id: 7, duration: 10, peaks: [0.1, 0.5, 0.9], width: 800, segments: [] })
    getTranscript.mockResolvedValue({ recording: completeRecording(), speakers: SPEAKERS, segments: SEGMENTS })
    getRecording.mockResolvedValue(completeRecording())
    seekTo.mockClear()
  })

  it('renders WaveformPlayer and SegmentTable when recording is complete with segments', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(getRecording).toHaveBeenCalledWith(7)
    expect(getTranscript).toHaveBeenCalledWith(7)
    expect(wrapper.findComponent(WaveformPlayerStub).exists()).toBe(true)
    const table = wrapper.findComponent(SegmentTableStub)
    expect(table.exists()).toBe(true)
    expect(table.props('segments')).toHaveLength(2)
    expect(table.props('speakers')).toHaveLength(2)
  })

  it('passes the streamed audio chunks URL to WaveformPlayer', async () => {
    const wrapper = mountView()
    await flushPromises()
    expect(audioChunksUrl).toHaveBeenCalledWith(7)
    expect(wrapper.findComponent(WaveformPlayerStub).props('audioUrl')).toBe(
      'http://backend/api/transcriber/recordings/7/audio/chunks'
    )
  })

  it('shows in-progress state and does not fetch the transcript while processing', async () => {
    getRecording.mockResolvedValue({ ...completeRecording(), status: 'processing' })
    const wrapper = mountView()
    await flushPromises()

    expect(getTranscript).not.toHaveBeenCalled()
    expect(wrapper.find('.transcript-progress').exists()).toBe(true)
    expect(wrapper.text()).toContain('Transcription in progress')
    expect(wrapper.findComponent(SegmentTableStub).exists()).toBe(false)
  })

  it('updates currentTime passed to SegmentTable when the player reports progress', async () => {
    const wrapper = mountView()
    await flushPromises()

    await wrapper.findComponent(WaveformPlayerStub).vm.$emit('seek', 6)
    await flushPromises()

    expect(wrapper.findComponent(SegmentTableStub).props('currentTime')).toBe(6)
  })

  it('seeks the player when a segment requests a seek', async () => {
    const wrapper = mountView()
    await flushPromises()

    await wrapper.findComponent(SegmentTableStub).vm.$emit('seek', 5)
    await flushPromises()

    expect(seekTo).toHaveBeenCalledWith(5)
    expect(wrapper.findComponent(SegmentTableStub).props('currentTime')).toBe(5)
  })
})
