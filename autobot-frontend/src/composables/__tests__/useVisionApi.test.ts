// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useVisionApi (#12363 slice 4): the typed vision/multimodal calls that replace VisionMultimodalApiClient.
 * They hit the contract path, send the documented query and body, and the health probe opts out of the
 * default retry and 401 session end.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const call = vi.fn()
vi.mock('@/utils/ApiClient', () => ({ default: { call: (...args: unknown[]) => call(...args) } }))

import {
  analyzeScreen,
  detectElements,
  getAutomationOpportunities,
  getVisionHealth,
  combineModalities,
  processAudio,
  processImage,
  processText,
  updateBatchSize,
} from '../useVisionApi'

describe('useVisionApi', () => {
  beforeEach(() => {
    call.mockReset().mockResolvedValue({})
  })

  it('probes health once and keeps the session on a 401', async () => {
    await getVisionHealth()
    expect(call).toHaveBeenCalledWith('get', '/api/vision/health', { maxRetries: 1, keepSessionOn401: true })
  })

  it('passes the session id as a query parameter only when given', async () => {
    await getAutomationOpportunities()
    await getAutomationOpportunities('s1')
    expect(call).toHaveBeenNthCalledWith(1, 'get', '/api/vision/automation-opportunities', { query: undefined })
    expect(call).toHaveBeenNthCalledWith(2, 'get', '/api/vision/automation-opportunities', { query: { session_id: 's1' } })
  })

  it('posts the detect and analyze bodies', async () => {
    await detectElements({ element_type: 'button', min_confidence: 0.4 })
    await analyzeScreen({ include_multimodal: true })
    expect(call).toHaveBeenCalledWith('post', '/api/vision/elements', { body: { element_type: 'button', min_confidence: 0.4 } })
    expect(call).toHaveBeenCalledWith('post', '/api/vision/analyze', { body: { include_multimodal: true } })
  })

  it('uploads an image as multipart with the intent and an optional question', async () => {
    const file = new File(['x'], 'a.png', { type: 'image/png' })
    await processImage(file, 'visual_qa', 'what is this?')
    await processImage(file)
    const first = call.mock.calls[0][2].body as FormData
    const second = call.mock.calls[1][2].body as FormData
    expect(call.mock.calls[0][1]).toBe('/api/multimodal/process/image')
    expect(first.get('intent')).toBe('visual_qa')
    expect(first.get('question')).toBe('what is this?')
    expect((first.get('file') as File).name).toBe('a.png')
    expect(second.get('intent')).toBe('analysis')
    expect(second.has('question')).toBe(false)
  })

  it('uploads audio, fuses parts and posts text, and sends the batch size as query parameters', async () => {
    const audio = new File(['a'], 'a.wav')
    await processAudio(audio)
    await combineModalities('hello', undefined, audio)
    await processText({ text: 'hi', intent: 'analysis' })
    await updateBatchSize('image', 8)
    const audioForm = call.mock.calls[0][2].body as FormData
    const fusion = call.mock.calls[1][2].body as FormData
    expect(audioForm.get('intent')).toBe('voice_command')
    expect(fusion.get('text')).toBe('hello')
    expect(fusion.has('image_file')).toBe(false)
    expect((fusion.get('audio_file') as File).name).toBe('a.wav')
    expect(fusion.get('intent')).toBe('decision_making')
    expect(call).toHaveBeenCalledWith('post', '/api/multimodal/process/text', { body: { text: 'hi', intent: 'analysis' } })
    expect(call).toHaveBeenCalledWith('post', '/api/multimodal/performance/batch-size', { query: { modality: 'image', batch_size: 8 } })
  })
})
