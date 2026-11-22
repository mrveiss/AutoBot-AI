// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Vision & Multimodal types (#582, #12363).
 *
 * Replies the backend models are aliases of the generated contract; the rest are hand-typed because the
 * route has no `response_model` (EmbeddingResponse, FusionResponse, MultimodalHealthResponse: #20867).
 * Request bodies and UI shapes are local.
 */

import type { components } from '@/types/generated/api';

// ==================================================================================
// VISION API TYPES
// ==================================================================================

export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export type UIElement = components['schemas']['UIElementResponse'];

export interface TextRegion {
  text: string;
  bbox: BoundingBox;
  confidence: number;
  language?: string;
}

export interface ColorInfo {
  color: string;
  percentage: number;
  rgb: [number, number, number];
}

export interface AutomationOpportunity {
  element_id: string;
  element_type: string;
  action: string;
  description: string;
  confidence: number;
}

export interface ScreenAnalysisRequest {
  session_id?: string;
  include_multimodal?: boolean;
}

export interface ElementDetectionRequest {
  element_type?: string;
  min_confidence?: number;
  session_id?: string;
}

export interface OCRRequest {
  region?: BoundingBox;
  session_id?: string;
}

export type ScreenAnalysisResponse = components['schemas']['ScreenAnalysisResponse'];

export type ElementDetectionResponse = components['schemas']['VisionDetectElementsResponse'];

export type OCRResponse = components['schemas']['VisionOCRResponse'];

export type AutomationOpportunitiesResponse = components['schemas']['VisionAutomationOpportunitiesResponse'];

export interface ElementTypeInfo {
  value: string;
  name: string;
  description: string;
}

export interface InteractionTypeInfo {
  value: string;
  name: string;
  description: string;
}

export type VisionHealthResponse = components['schemas']['VisionHealthResponse'];

export type VisionStatusResponse = components['schemas']['VisionStatusResponse'];

export type LayoutResponse = components['schemas']['VisionLayoutResponse'];

// ==================================================================================
// MULTIMODAL API TYPES
// ==================================================================================

export type ProcessingIntent =
  | 'analysis'
  | 'visual_qa'
  | 'voice_command'
  | 'automation'
  | 'content_generation'
  | 'decision_making';

export type ModalityType = 'text' | 'image' | 'audio' | 'video' | 'combined';

export type MultiModalResponse = components['schemas']['MultiModalResponse'];

export interface TextProcessingRequest {
  text: string;
  intent?: ProcessingIntent;
  metadata?: Record<string, unknown>;
}

export interface EmbeddingRequest {
  content: string;
  modality: ModalityType;
  preferred_device?: 'gpu' | 'npu' | 'cpu';
}

export interface EmbeddingResponse {
  success: boolean;
  embedding?: number[];
  dimension?: number;
  modality: string;
  processing_time: number;
  device_used: string;
  error?: string;
}

export interface CrossModalSearchRequest {
  query: string;
  query_modality: ModalityType;
  target_modalities?: ModalityType[];
  limit?: number;
  similarity_threshold?: number;
}

export interface SearchResult {
  content: string;
  modality: string;
  metadata: Record<string, unknown>;
  score: number;
  doc_id: string;
  source_modality: string;
  fusion_confidence: number;
}

export type CrossModalSearchResponse = components['schemas']['CrossModalSearchResponse'];

export interface GPUStats {
  gpu_memory_allocated_mb: number;
  gpu_memory_reserved_mb: number;
  gpu_device_count: number;
  gpu_device_name: string | null;
}

export interface MultimodalStats {
  success: boolean;
  timestamp: number;
  processor_stats: Record<string, unknown>;
  gpu_available: boolean;
  gpu_stats: GPUStats;
  search_engine_status: Record<string, unknown>;
  vision_models_available: boolean;
  audio_models_available: boolean;
  model_availability: Record<string, unknown>;
  system_status: string;
  error?: string;
}

export interface FusionResponse {
  success: boolean;
  fusion_result: Record<string, unknown>;
  individual_results: Array<{
    modality: string;
    confidence: number;
    data: Record<string, unknown>;
  }>;
  processing_time: number;
  fusion_confidence: number;
  modalities_combined: number;
  error?: string;
}

export interface PerformanceStats {
  success: boolean;
  timestamp: number;
  performance_metrics: Record<string, unknown>;
  processor_stats: Record<string, unknown>;
  optimization_status: {
    auto_optimization_enabled: boolean;
    mixed_precision_enabled: boolean;
    device: string;
    batch_sizes: Record<string, number>;
  };
  error?: string;
}

export interface PerformanceSummary {
  success: boolean;
  timestamp: number;
  summary: Record<string, unknown>;
  error?: string;
}

export interface MultimodalHealthResponse {
  status: string;
  timestamp: number;
  gpu_available: boolean;
  processor_ready: boolean;
  performance_monitoring: boolean;
  mixed_precision_enabled: boolean;
}

// ==================================================================================
// UI COMPONENT TYPES
// ==================================================================================

/**
 * Gallery item type used by VisionMultimodalView and MediaGallery components
 */
export interface GalleryItem {
  id: string;
  type: 'image' | 'video' | 'screen';
  thumbnail: string;
  filename: string;
  timestamp: number;
  analysisResult?: Record<string, unknown>;
}
