// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Vision API types — canonical frontend representations of backend Pydantic schemas.
 * Issue #9890: extracted from useVisionAutomation.ts composable.
 *
 * NOTE: VisionMultimodalApiClient.ts has a parallel set of types for the same
 * endpoints; its migration to import from here is tracked separately.
 */

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
