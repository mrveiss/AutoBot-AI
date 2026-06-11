// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Vision Automation Composable
 * Issue #9890 — Wire vision automation panel to /api/vision endpoints
 */

import { ref } from 'vue'
import { useApiClient } from '@/plugins/api'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'
import type {
  VisionUIElement,
  VisionDetectElementsResponse,
  VisionTextRegion,
  VisionOCRResponse,
  VisionAutomationOpportunity,
  VisionAutomationOpportunitiesResponse,
  VisionStatusFeatures,
  VisionStatusResponse,
  ScreenAnalysisResponse,
} from '@/types/vision'

export type {
  VisionUIElement,
  VisionDetectElementsResponse,
  VisionTextRegion,
  VisionOCRResponse,
  VisionAutomationOpportunity,
  VisionAutomationOpportunitiesResponse,
  VisionStatusFeatures,
  VisionStatusResponse,
  ScreenAnalysisResponse,
}

const logger = createLogger('useVisionAutomation')

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function useVisionAutomation() {
  const api = useApiClient()

  const isLoading = ref(false)
  const error = ref<string | null>(null)

  const status = ref<VisionStatusResponse | null>(null)
  const screenAnalysis = ref<ScreenAnalysisResponse | null>(null)
  const detectedElements = ref<VisionDetectElementsResponse | null>(null)
  const ocrResult = ref<VisionOCRResponse | null>(null)
  const opportunities = ref<VisionAutomationOpportunitiesResponse | null>(null)

  const base = () => `${getApiBase()}/vision`

  async function fetchStatus(): Promise<void> {
    error.value = null
    try {
      const data = await api.get<VisionStatusResponse>(`${base()}/status`)
      status.value = data
      logger.debug('Vision status:', data)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch vision status'
      logger.error('fetchStatus error:', err)
      error.value = msg
    }
  }

  async function analyzeScreen(sessionId?: string): Promise<void> {
    error.value = null
    isLoading.value = true
    try {
      const payload = { include_multimodal: true, session_id: sessionId ?? null }
      const data = await api.post<ScreenAnalysisResponse>(`${base()}/analyze`, payload)
      screenAnalysis.value = data
      logger.debug('Screen analysis result:', data)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Screen analysis failed'
      logger.error('analyzeScreen error:', err)
      error.value = msg
    } finally {
      isLoading.value = false
    }
  }

  async function detectElements(
    elementType?: string,
    minConfidence = 0.5,
    sessionId?: string,
  ): Promise<void> {
    error.value = null
    isLoading.value = true
    try {
      const payload = {
        element_type: elementType ?? null,
        min_confidence: minConfidence,
        session_id: sessionId ?? null,
      }
      const data = await api.post<VisionDetectElementsResponse>(`${base()}/elements`, payload)
      detectedElements.value = data
      logger.debug('Detected elements:', data)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Element detection failed'
      logger.error('detectElements error:', err)
      error.value = msg
    } finally {
      isLoading.value = false
    }
  }

  async function extractOCR(sessionId?: string): Promise<void> {
    error.value = null
    isLoading.value = true
    try {
      const payload = { session_id: sessionId ?? null }
      const data = await api.post<VisionOCRResponse>(`${base()}/ocr`, payload)
      ocrResult.value = data
      logger.debug('OCR result:', data)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'OCR extraction failed'
      logger.error('extractOCR error:', err)
      error.value = msg
    } finally {
      isLoading.value = false
    }
  }

  async function fetchOpportunities(sessionId?: string): Promise<void> {
    error.value = null
    isLoading.value = true
    try {
      const params = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ''
      const data = await api.get<VisionAutomationOpportunitiesResponse>(
        `${base()}/automation-opportunities${params}`,
      )
      opportunities.value = data
      logger.debug('Automation opportunities:', data)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch automation opportunities'
      logger.error('fetchOpportunities error:', err)
      error.value = msg
    } finally {
      isLoading.value = false
    }
  }

  return {
    isLoading,
    error,
    status,
    screenAnalysis,
    detectedElements,
    ocrResult,
    opportunities,
    fetchStatus,
    analyzeScreen,
    detectElements,
    extractOCR,
    fetchOpportunities,
  }
}
