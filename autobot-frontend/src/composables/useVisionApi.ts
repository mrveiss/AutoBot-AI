// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Vision & Multimodal calls (#582, #12363 slice 4).
 *
 * The typed `apiClient.call` for the /api/vision and /api/multimodal routes the GUI uses, in place of
 * the retired VisionMultimodalApiClient. Every function resolves to the reply and THROWS on a non-2xx
 * (an `HttpError`); callers keep their own try/catch.
 *
 * The contract marks request fields the backend defaults (`include_multimodal`, `min_confidence`) as
 * required, so the local request types (all fields optional) are narrowed with one assertion each (#20867).
 */

import type { components } from '@/types/generated/api'
import type {
  CrossModalSearchRequest,
  ElementDetectionRequest,
  EmbeddingRequest,
  OCRRequest,
  ProcessingIntent,
  ScreenAnalysisRequest,
  TextProcessingRequest,
} from '@/types/visionMultimodal'
import apiClient from '@/utils/ApiClient'

type Schemas = components['schemas']

/** Health probe: one attempt, and a 401 does not end the session (a diagnostic, not a user action). */
export function getVisionHealth() {
  return apiClient.call('get', '/api/vision/health', { maxRetries: 1, keepSessionOn401: true })
}

export function getAutomationOpportunities(sessionId?: string) {
  return apiClient.call('get', '/api/vision/automation-opportunities', {
    query: sessionId ? { session_id: sessionId } : undefined,
  })
}

export function getElementTypes() {
  return apiClient.call('get', '/api/vision/element-types')
}

export function getInteractionTypes() {
  return apiClient.call('get', '/api/vision/interaction-types')
}

export function detectElements(request: ElementDetectionRequest = {}) {
  return apiClient.call('post', '/api/vision/elements', { body: request as Schemas['ElementDetectionRequest'] })
}

export function analyzeScreen(request: ScreenAnalysisRequest = {}) {
  return apiClient.call('post', '/api/vision/analyze', { body: request as Schemas['ScreenAnalysisRequest'] })
}

/** Upload one image; the multipart fields are `file`, `intent` and (visual Q&A only) `question`. */
export function processImage(file: File, intent: ProcessingIntent = 'analysis', question?: string) {
  const form = new FormData()
  form.append('file', file)
  form.append('intent', intent)
  if (question) form.append('question', question)
  return apiClient.call('post', '/api/multimodal/process/image', { body: form })
}

export function getVisionStatus() {
  return apiClient.call('get', '/api/vision/status')
}

export function extractText(request: OCRRequest = {}) {
  return apiClient.call('post', '/api/vision/ocr', { body: request as Schemas['OCRRequest'] })
}

export function getLayoutAnalysis(sessionId?: string) {
  return apiClient.call('get', '/api/vision/layout', { query: sessionId ? { session_id: sessionId } : undefined })
}

export function getMultimodalStats() {
  return apiClient.call('get', '/api/multimodal/stats')
}

/** Upload one audio file; the multipart fields are `file` and `intent`. */
export function processAudio(file: File, intent: ProcessingIntent = 'voice_command') {
  const form = new FormData()
  form.append('file', file)
  form.append('intent', intent)
  return apiClient.call('post', '/api/multimodal/process/audio', { body: form })
}

export function processText(request: TextProcessingRequest) {
  return apiClient.call('post', '/api/multimodal/process/text', { body: request as Schemas['TextProcessingRequest'] })
}

export function generateEmbedding(request: EmbeddingRequest) {
  return apiClient.call('post', '/api/multimodal/embeddings/generate', { body: request as Schemas['EmbeddingRequest'] })
}

export function crossModalSearch(request: CrossModalSearchRequest) {
  return apiClient.call('post', '/api/multimodal/search/cross-modal', { body: request as Schemas['CrossModalSearchRequest'] })
}

/** Combine text, an image and audio; each part is optional, the multipart fields are `text`, `image_file`, `audio_file`, `intent`. */
export function combineModalities(text?: string, imageFile?: File, audioFile?: File, intent: ProcessingIntent = 'decision_making') {
  const form = new FormData()
  if (text) form.append('text', text)
  if (imageFile) form.append('image_file', imageFile)
  if (audioFile) form.append('audio_file', audioFile)
  form.append('intent', intent)
  return apiClient.call('post', '/api/multimodal/fusion/combine', { body: form })
}

export function getPerformanceStats() {
  return apiClient.call('get', '/api/multimodal/performance/stats')
}

export function getPerformanceSummary() {
  return apiClient.call('get', '/api/multimodal/performance/summary')
}

export function optimizePerformance() {
  return apiClient.call('post', '/api/multimodal/performance/optimize')
}

export function updateBatchSize(modality: string, batchSize: number) {
  return apiClient.call('post', '/api/multimodal/performance/batch-size', { query: { modality, batch_size: batchSize } })
}

export function useVisionApi() {
  return {
    getVisionHealth, getVisionStatus, getAutomationOpportunities, getElementTypes, getInteractionTypes, getLayoutAnalysis,
    detectElements, analyzeScreen, extractText, processImage, processAudio, processText, generateEmbedding, crossModalSearch,
    combineModalities, getMultimodalStats, getPerformanceStats, getPerformanceSummary, optimizePerformance, updateBatchSize,
  }
}
