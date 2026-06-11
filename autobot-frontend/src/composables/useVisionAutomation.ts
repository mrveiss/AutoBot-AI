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

const logger = createLogger('useVisionAutomation')

// ---------------------------------------------------------------------------
// Types — mirrored from backend Pydantic schemas
// ---------------------------------------------------------------------------

export interface VisionUIElement {
  element_id: string
  element_type: string
  bbox: Record<string, number>
  center_point: number[]
  confidence: number
  text_content: string | null
  possible_interactions: string[]
}

export interface VisionDetectElementsResponse {
  total_detected: number
  filtered_count: number
  elements: VisionUIElement[]
  filter_applied: Record<string, unknown>
}

export interface VisionTextRegion {
  [key: string]: unknown
}

export interface VisionOCRResponse {
  region_specified: boolean
  text_regions: VisionTextRegion[]
  total_text_regions: number
  region?: Record<string, number> | null
}

export interface VisionAutomationOpportunity {
  [key: string]: unknown
}

export interface VisionAutomationOpportunitiesResponse {
  opportunities: VisionAutomationOpportunity[]
  total_opportunities: number
  context: Record<string, unknown>
  confidence: number
}

export interface VisionStatusFeatures {
  screen_analysis: boolean
  element_detection: boolean
  ocr_extraction: boolean
  template_matching: boolean
  multimodal_processing: boolean
}

export interface VisionStatusResponse {
  service: string
  status: string
  features?: VisionStatusFeatures
  supported_element_types?: number
  supported_interaction_types?: number
  error?: string
}

export interface ScreenAnalysisResponse {
  timestamp: number
  ui_elements: VisionUIElement[]
  text_regions: Record<string, unknown>[]
  dominant_colors: Record<string, unknown>[]
  layout_structure: Record<string, unknown>
  automation_opportunities: Record<string, unknown>[]
  context_analysis: Record<string, unknown>
  confidence_score: number
  multimodal_analysis?: Record<string, unknown>[] | null
}

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
