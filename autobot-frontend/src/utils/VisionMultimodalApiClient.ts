// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Vision & Multimodal API Client
 *
 * Provides type-safe access to the Vision and Multimodal API endpoints.
 * Issue #582: GUI integration for Vision & Multimodal Interface
 * Issue #9985: vision methods migrated to the canonical ApiClient and the
 *   shared `@/types/vision` types (no hand-rolled fetch, no duplicate
 *   response-type declarations for the migrated surface).
 */

import { useApiClient } from '@/plugins/api';
import { createLogger } from '@/utils/debugUtils';
import { getApiBase } from '@/config/ssot-config';
import type { ApiResponse } from '@/types/api';
import type {
  VisionStatusResponse,
  ScreenAnalysisResponse,
} from '@/types/vision';

const logger = createLogger('VisionMultimodalApiClient');

// ==================================================================================
// VISION API TYPES
// ==================================================================================

// VisionStatusResponse and ScreenAnalysisResponse are the canonical, backend-
// verified shapes (#9890 / #9986) — imported above and re-exported below for
// any caller that still imports them from this module.

export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface UIElement {
  element_id: string;
  element_type: string;
  bbox: BoundingBox;
  center_point: [number, number];
  confidence: number;
  text_content: string;
  attributes: Record<string, unknown>;
  possible_interactions: string[];
}

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

export interface ElementDetectionResponse {
  total_detected: number;
  filtered_count: number;
  elements: UIElement[];
  filter_applied: {
    element_type: string | null;
    min_confidence: number;
  };
}

export interface OCRResponse {
  region_specified: boolean;
  region?: BoundingBox;
  text_regions: TextRegion[];
  total_text_regions: number;
}

export interface AutomationOpportunitiesResponse {
  opportunities: AutomationOpportunity[];
  total_opportunities: number;
  context: Record<string, unknown>;
  confidence: number;
}

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

export interface VisionHealthResponse {
  status: string;
  analyzer_ready: boolean;
  capabilities: string[];
  element_types_supported: string[];
  interaction_types_supported: string[];
}

export interface LayoutResponse {
  layout_structure: Record<string, unknown>;
  dominant_colors: ColorInfo[];
  timestamp: number;
}

// Re-export the canonical shared vision types so existing importers of this
// module keep resolving (#9985 dedup — single source of truth in @/types/vision).
export type { VisionStatusResponse, ScreenAnalysisResponse } from '@/types/vision';

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

export interface MultiModalResponse {
  success: boolean;
  result_id: string;
  modality: string;
  processing_time: number;
  confidence: number;
  result_data: Record<string, unknown>;
  device_used?: string;
  error_message?: string;
}

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

export interface CrossModalSearchResponse {
  query: string;
  query_modality: string;
  results: Record<string, SearchResult[]>;
  total_found: number;
  processing_time: number;
}

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

// ==================================================================================
// API CLIENT
// ==================================================================================

/**
 * Vision & Multimodal API Client
 *
 * Communicates with /api/vision and /api/multimodal endpoints via the canonical
 * ApiClient (auth injection, retry, timeout, 401 handling). The ApiResponse<T>
 * envelope is preserved so existing callers keep their { success, data, error }
 * contract.
 */
class VisionMultimodalApiClient {
  private get api() {
    return useApiClient();
  }

  private toErrorMessage(error: unknown): string {
    return error instanceof Error ? error.message : 'Unknown error occurred';
  }

  /** GET via the canonical ApiClient, wrapped in the ApiResponse envelope. */
  private async get<T>(endpoint: string): Promise<ApiResponse<T>> {
    try {
      const data = await this.api.get<T>(endpoint);
      return { success: true, data };
    } catch (error) {
      logger.error('API GET error:', error);
      return { success: false, error: this.toErrorMessage(error) };
    }
  }

  /** POST via the canonical ApiClient, wrapped in the ApiResponse envelope. */
  private async post<T>(endpoint: string, body?: unknown): Promise<ApiResponse<T>> {
    try {
      const data = await this.api.post<T>(endpoint, body);
      return { success: true, data };
    } catch (error) {
      logger.error('API POST error:', error);
      return { success: false, error: this.toErrorMessage(error) };
    }
  }

  // ==================================================================================
  // VISION API ENDPOINTS
  // ==================================================================================

  /**
   * Health check for computer vision service
   * GET /api/vision/health
   */
  async getVisionHealth(): Promise<ApiResponse<VisionHealthResponse>> {
    return this.get<VisionHealthResponse>(`${getApiBase()}/vision/health`);
  }

  /**
   * Get vision service status
   * GET /api/vision/status
   */
  async getVisionStatus(): Promise<ApiResponse<VisionStatusResponse>> {
    return this.get<VisionStatusResponse>(`${getApiBase()}/vision/status`);
  }

  /**
   * Perform comprehensive screen analysis
   * POST /api/vision/analyze
   */
  async analyzeScreen(
    request: ScreenAnalysisRequest = {}
  ): Promise<ApiResponse<ScreenAnalysisResponse>> {
    return this.post<ScreenAnalysisResponse>(`${getApiBase()}/vision/analyze`, request);
  }

  /**
   * Detect UI elements on screen
   * POST /api/vision/elements
   */
  async detectElements(
    request: ElementDetectionRequest = {}
  ): Promise<ApiResponse<ElementDetectionResponse>> {
    return this.post<ElementDetectionResponse>(`${getApiBase()}/vision/elements`, request);
  }

  /**
   * Extract text using OCR
   * POST /api/vision/ocr
   */
  async extractText(request: OCRRequest = {}): Promise<ApiResponse<OCRResponse>> {
    return this.post<OCRResponse>(`${getApiBase()}/vision/ocr`, request);
  }

  /**
   * Get automation opportunities
   * GET /api/vision/automation-opportunities
   */
  async getAutomationOpportunities(
    sessionId?: string
  ): Promise<ApiResponse<AutomationOpportunitiesResponse>> {
    const params = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : '';
    return this.get<AutomationOpportunitiesResponse>(
      `${getApiBase()}/vision/automation-opportunities${params}`
    );
  }

  /**
   * Get supported element types
   * GET /api/vision/element-types
   */
  async getElementTypes(): Promise<ApiResponse<{
    element_types: ElementTypeInfo[];
    total_types: number;
  }>> {
    return this.get(`${getApiBase()}/vision/element-types`);
  }

  /**
   * Get supported interaction types
   * GET /api/vision/interaction-types
   */
  async getInteractionTypes(): Promise<ApiResponse<{
    interaction_types: InteractionTypeInfo[];
    total_types: number;
  }>> {
    return this.get(`${getApiBase()}/vision/interaction-types`);
  }

  /**
   * Get layout analysis
   * GET /api/vision/layout
   */
  async getLayoutAnalysis(sessionId?: string): Promise<ApiResponse<LayoutResponse>> {
    const params = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : '';
    return this.get<LayoutResponse>(`${getApiBase()}/vision/layout${params}`);
  }

  // ==================================================================================
  // MULTIMODAL API ENDPOINTS
  // ==================================================================================

  /**
   * Health check for multimodal API
   * GET /api/multimodal/health
   */
  async getMultimodalHealth(): Promise<ApiResponse<MultimodalHealthResponse>> {
    return this.get<MultimodalHealthResponse>(`${getApiBase()}/multimodal/health`);
  }

  /**
   * Get multimodal processing statistics
   * GET /api/multimodal/stats
   */
  async getMultimodalStats(): Promise<ApiResponse<MultimodalStats>> {
    return this.get<MultimodalStats>(`${getApiBase()}/multimodal/stats`);
  }

  /**
   * Process an image file
   * POST /api/multimodal/process/image
   */
  async processImage(
    file: File,
    intent: ProcessingIntent = 'analysis',
    question?: string
  ): Promise<ApiResponse<MultiModalResponse>> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('intent', intent);
    if (question) {
      formData.append('question', question);
    }

    return this.post<MultiModalResponse>(`${getApiBase()}/multimodal/process/image`, formData);
  }

  /**
   * Process an audio file
   * POST /api/multimodal/process/audio
   */
  async processAudio(
    file: File,
    intent: ProcessingIntent = 'voice_command'
  ): Promise<ApiResponse<MultiModalResponse>> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('intent', intent);

    return this.post<MultiModalResponse>(`${getApiBase()}/multimodal/process/audio`, formData);
  }

  /**
   * Process text
   * POST /api/multimodal/process/text
   */
  async processText(
    request: TextProcessingRequest
  ): Promise<ApiResponse<MultiModalResponse>> {
    return this.post<MultiModalResponse>(`${getApiBase()}/multimodal/process/text`, request);
  }

  /**
   * Generate embeddings
   * POST /api/multimodal/embeddings/generate
   */
  async generateEmbedding(
    request: EmbeddingRequest
  ): Promise<ApiResponse<EmbeddingResponse>> {
    return this.post<EmbeddingResponse>(`${getApiBase()}/multimodal/embeddings/generate`, request);
  }

  /**
   * Cross-modal similarity search
   * POST /api/multimodal/search/cross-modal
   */
  async crossModalSearch(
    request: CrossModalSearchRequest
  ): Promise<ApiResponse<CrossModalSearchResponse>> {
    return this.post<CrossModalSearchResponse>(`${getApiBase()}/multimodal/search/cross-modal`, request);
  }

  /**
   * Combine multiple modalities
   * POST /api/multimodal/fusion/combine
   */
  async combineModalities(
    text?: string,
    imageFile?: File,
    audioFile?: File,
    intent: ProcessingIntent = 'decision_making'
  ): Promise<ApiResponse<FusionResponse>> {
    const formData = new FormData();

    if (text) {
      formData.append('text', text);
    }
    if (imageFile) {
      formData.append('image_file', imageFile);
    }
    if (audioFile) {
      formData.append('audio_file', audioFile);
    }
    formData.append('intent', intent);

    return this.post<FusionResponse>(`${getApiBase()}/multimodal/fusion/combine`, formData);
  }

  /**
   * Get performance statistics
   * GET /api/multimodal/performance/stats
   */
  async getPerformanceStats(): Promise<ApiResponse<PerformanceStats>> {
    return this.get<PerformanceStats>(`${getApiBase()}/multimodal/performance/stats`);
  }

  /**
   * Get performance summary
   * GET /api/multimodal/performance/summary
   */
  async getPerformanceSummary(): Promise<ApiResponse<PerformanceSummary>> {
    return this.get<PerformanceSummary>(`${getApiBase()}/multimodal/performance/summary`);
  }

  /**
   * Trigger performance optimization
   * POST /api/multimodal/performance/optimize
   */
  async optimizePerformance(): Promise<ApiResponse<{
    success: boolean;
    timestamp: number;
    optimization_result: Record<string, unknown>;
    message: string;
  }>> {
    return this.post(`${getApiBase()}/multimodal/performance/optimize`);
  }

  /**
   * Update batch size for a modality
   * POST /api/multimodal/performance/batch-size
   */
  async updateBatchSize(
    modality: string,
    batchSize: number
  ): Promise<ApiResponse<{
    success: boolean;
    timestamp: number;
    modality: string;
    old_batch_size: number;
    new_batch_size: number;
    message: string;
  }>> {
    const params = new URLSearchParams({
      modality,
      batch_size: batchSize.toString(),
    });
    return this.post(`${getApiBase()}/multimodal/performance/batch-size?${params}`);
  }
}

// Export singleton instance
export const visionMultimodalApiClient = new VisionMultimodalApiClient();
export default visionMultimodalApiClient;
