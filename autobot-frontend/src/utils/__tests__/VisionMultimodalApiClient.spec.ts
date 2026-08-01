// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * VisionMultimodalApiClient tests (#12152)
 *
 * Verifies the client routes every request through the shared apiClient
 * singleton (so it inherits expiry-aware auth + 401 auto-logout + retry)
 * instead of its own fetchWithAuth/base-URL plumbing, and that the
 * multi-field FormData composition used by combineModalities is preserved.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'

vi.mock('@/utils/ApiClient', () => ({
  default: {
    rawRequest: vi.fn(),
  },
}))

vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/api',
}))

import apiClient from '@/utils/ApiClient'
import { visionMultimodalApiClient } from '../VisionMultimodalApiClient'

function mockResponse(body: unknown, ok = true, status = 200) {
  return {
    ok,
    status,
    json: vi.fn().mockResolvedValue(body),
  }
}

describe('VisionMultimodalApiClient', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('JSON requests route through apiClient.rawRequest', () => {
    it('getVisionHealth issues a GET against apiClient.rawRequest', async () => {
      vi.mocked(apiClient.rawRequest).mockResolvedValue(
        mockResponse({ status: 'ok', analyzer_ready: true, capabilities: [], element_types_supported: [], interaction_types_supported: [] })
      )

      const result = await visionMultimodalApiClient.getVisionHealth()

      expect(apiClient.rawRequest).toHaveBeenCalledWith('/api/vision/health', {})
      expect(result.success).toBe(true)
      expect(result.data).toMatchObject({ status: 'ok' })
    })

    it('analyzeScreen sends the raw request object as body (apiClient stringifies it)', async () => {
      vi.mocked(apiClient.rawRequest).mockResolvedValue(mockResponse({ timestamp: 1 }))

      await visionMultimodalApiClient.analyzeScreen({ session_id: 'abc' })

      expect(apiClient.rawRequest).toHaveBeenCalledWith('/api/vision/analyze', {
        method: 'POST',
        body: { session_id: 'abc' },
      })
    })

    it('translates a non-ok response into ApiResponse.success = false with the backend error', async () => {
      vi.mocked(apiClient.rawRequest).mockResolvedValue(
        mockResponse({ detail: 'analyzer offline' }, false, 503)
      )

      const result = await visionMultimodalApiClient.getVisionStatus()

      expect(result).toEqual({ success: false, error: 'analyzer offline' })
    })

    it('translates a thrown/network error into ApiResponse.success = false', async () => {
      vi.mocked(apiClient.rawRequest).mockRejectedValue(new Error('Request timeout after 30000ms'))

      const result = await visionMultimodalApiClient.getVisionHealth()

      expect(result).toEqual({ success: false, error: 'Request timeout after 30000ms' })
    })
  })

  describe('multi-field FormData composition (combineModalities)', () => {
    it('composes text + image + audio + intent into one FormData and posts it via apiClient.rawRequest', async () => {
      vi.mocked(apiClient.rawRequest).mockResolvedValue(mockResponse({ success: true, fusion_result: {} }))

      const imageFile = new File(['img'], 'shot.png', { type: 'image/png' })
      const audioFile = new File(['aud'], 'clip.wav', { type: 'audio/wav' })

      await visionMultimodalApiClient.combineModalities('describe this', imageFile, audioFile, 'analysis')

      expect(apiClient.rawRequest).toHaveBeenCalledTimes(1)
      const [endpoint, options] = vi.mocked(apiClient.rawRequest).mock.calls[0]
      expect(endpoint).toBe('/api/multimodal/fusion/combine')
      expect(options.method).toBe('POST')

      const formData = options.body as FormData
      expect(formData).toBeInstanceOf(FormData)
      expect(formData.get('text')).toBe('describe this')
      expect(formData.get('image_file')).toBe(imageFile)
      expect(formData.get('audio_file')).toBe(audioFile)
      expect(formData.get('intent')).toBe('analysis')
    })

    it('omits absent optional fields (text/image/audio) but always sends intent', async () => {
      vi.mocked(apiClient.rawRequest).mockResolvedValue(mockResponse({ success: true, fusion_result: {} }))

      await visionMultimodalApiClient.combineModalities(undefined, undefined, undefined, 'decision_making')

      const [, options] = vi.mocked(apiClient.rawRequest).mock.calls[0]
      const formData = options.body as FormData
      expect(formData.get('text')).toBeNull()
      expect(formData.get('image_file')).toBeNull()
      expect(formData.get('audio_file')).toBeNull()
      expect(formData.get('intent')).toBe('decision_making')
    })

    it('processImage posts a single-field FormData (file + intent + optional question)', async () => {
      vi.mocked(apiClient.rawRequest).mockResolvedValue(mockResponse({ success: true, result_id: 'r1' }))

      const file = new File(['img'], 'shot.png', { type: 'image/png' })
      await visionMultimodalApiClient.processImage(file, 'visual_qa', 'what is this?')

      const [endpoint, options] = vi.mocked(apiClient.rawRequest).mock.calls[0]
      expect(endpoint).toBe('/api/multimodal/process/image')
      const formData = options.body as FormData
      expect(formData.get('file')).toBe(file)
      expect(formData.get('intent')).toBe('visual_qa')
      expect(formData.get('question')).toBe('what is this?')
    })
  })
})
