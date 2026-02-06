// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Vision & Multimodal API Client
 *
 * Provides type-safe access to the Vision and Multimodal API endpoints.
 * Issue #582: GUI integration for Vision & Multimodal Interface
 */

import appConfig from '@/config/AppConfig.js';
import { NetworkConstants } from '@/constants/network';
import { createLogger } from '@/utils/debugUtils';
import type { ApiResponse } from '@/types/api';

const logger = createLogger('VisionMultimodalApiClient');

// ==================================================================================
// VISION API TYPES
// ==================================================================================

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

export interface ScreenAnalysisResponse {
  timestamp: number;
  ui_elements: UIElement[];
  text_regions: TextRegion[];
  dominant_colors: ColorInfo[];
  layout_structure: Record<string, unknown>;
  automation_opportunities: AutomationOpportunity[];
  context_analysis: Record<string, unknown>;
  confidence_score: number;
  multimodal_analysis?: Record<string, unknown>[];
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

export interface VisionStatusResponse {
  service: string;
  status: string;
  features: {
    screen_analysis: boolean;
    element_detection: boolean;
    ocr_extraction: boolean;
    template_matching: boolean;
    multimodal_processing: boolean;
  };
  supported_element_types: number;
  supported_interaction_types: number;
  error?: string;
}

export interface LayoutResponse {
  layout_structure: Record<string, unknown>;
  dominant_colors: ColorInfo[];
  timestamp: number;
}

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
 * Communicates with /api/vision and /api/multimodal endpoints
 */
class VisionMultimodalApiClient {
  private baseUrl: string = '';
  private baseUrlPromise: Promise<string> | null = null;

  constructor() {
    this.initializeBaseUrl();
  }

  private async initializeBaseUrl(): Promise<void> {
    try {
      this.baseUrl = await appConfig.getApiUrl('');
    } catch (_error) {
      logger.warn('AppConfig initialization failed, using NetworkConstants fallback');
      this.baseUrl = `http://${NetworkConstants.MAIN_MACHINE_IP}:${NetworkConstants.BACKEND_PORT}`;
    }
  }

  private async ensureBaseUrl(): Promise<string> {
    if (this.baseUrl) {
      return this.baseUrl;
    }

    if (!this.baseUrlPromise) {
      this.baseUrlPromise = this.initializeBaseUrl().then(() => this.baseUrl);
    }

    return await this.baseUrlPromise;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<ApiResponse<T>> {
    const baseUrl = await this.ensureBaseUrl();
    const url = `${baseUrl}${endpoint}`;

    const defaultHeaders: Record<string, string> = {
      'Content-Type': 'application/json',
    };

    try {
      const response = await fetch(url, {
        ...options,
        headers: { ...defaultHeaders, ...options.headers },
      });

      const data = await response.json();

      if (!response.ok) {
        logger.error(`API request failed with status ${response.status}`, data);
        return {
          success: false,
          error: data.detail || data.message || `Request failed with status ${response.status}`,
        };
      }

      return { success: true, data };
    } catch (error) {
      logger.error('API request error:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error occurred',
      };
    }
  }

  private async requestFormData<T>(
    endpoint: string,
    formData: FormData
  ): Promise<ApiResponse<T>> {
    const baseUrl = await this.ensureBaseUrl();
    const url = `${baseUrl}${endpoint}`;

    try {
      const response = await fetch(url, {
        method: 'POST',
        body: formData,
        // Don't set Content-Type - browser will set it with boundary for multipart
      });

      const data = await response.json();

      if (!response.ok) {
        logger.error(`Form data request failed with status ${response.status}`, data);
        return {
          success: false,
          error: data.detail || data.message || `Request failed with status ${response.status}`,
        };
      }

      return { success: true, data };
    } catch (error) {
      logger.error('Form data request error:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error occurred',
      };
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
    return this.request<VisionHealthResponse>('/api/vision/health');
  }

  /**
   * Get vision service status
   * GET /api/vision/status
   */
  async getVisionStatus(): Promise<ApiResponse<VisionStatusResponse>> {
    return this.request<VisionStatusResponse>('/api/vision/status');
  }

  /**
   * Perform comprehensive screen analysis
   * POST /api/vision/analyze
   */
  async analyzeScreen(
    request: ScreenAnalysisRequest = {}
  ): Promise<ApiResponse<ScreenAnalysisResponse>> {
    return this.request<ScreenAnalysisResponse>('/api/vision/analyze', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  /**
   * Detect UI elements on screen
   * POST /api/vision/elements
   */
  async detectElements(
    request: ElementDetectionRequest = {}
  ): Promise<ApiResponse<ElementDetectionResponse>> {
    return this.request<ElementDetectionResponse>('/api/vision/elements', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  /**
   * Extract text using OCR
   * POST /api/vision/ocr
   */
  async extractText(request: OCRRequest = {}): Promise<ApiResponse<OCRResponse>> {
    return this.request<OCRResponse>('/api/vision/ocr', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  /**
   * Get automation opportunities
   * GET /api/vision/automation-opportunities
   */
  async getAutomationOpportunities(
    sessionId?: string
  ): Promise<ApiResponse<AutomationOpportunitiesResponse>> {
    const params = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : '';
    return this.request<AutomationOpportunitiesResponse>(
      `/api/vision/automation-opportunities${params}`
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
    return this.request('/api/vision/element-types');
  }

  /**
   * Get supported interaction types
   * GET /api/vision/interaction-types
   */
  async getInteractionTypes(): Promise<ApiResponse<{
    interaction_types: InteractionTypeInfo[];
    total_types: number;
  }>> {
    return this.request('/api/vision/interaction-types');
  }

  /**
   * Get layout analysis
   * GET /api/vision/layout
   */
  async getLayoutAnalysis(sessionId?: string): Promise<ApiResponse<LayoutResponse>> {
    const params = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : '';
    return this.request<LayoutResponse>(`/api/vision/layout${params}`);
  }

  // ==================================================================================
  // MULTIMODAL API ENDPOINTS
  // ==================================================================================

  /**
   * Health check for multimodal API
   * GET /api/multimodal/health
   */
  async getMultimodalHealth(): Promise<ApiResponse<MultimodalHealthResponse>> {
    return this.request<MultimodalHealthResponse>('/api/multimodal/health');
  }

  /**
   * Get multimodal processing statistics
   * GET /api/multimodal/stats
   */
  async getMultimodalStats(): Promise<ApiResponse<MultimodalStats>> {
    return this.request<MultimodalStats>('/api/multimodal/stats');
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

    return this.requestFormData<MultiModalResponse>('/api/multimodal/process/image', formData);
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

    return this.requestFormData<MultiModalResponse>('/api/multimodal/process/audio', formData);
  }

  /**
   * Process text
   * POST /api/multimodal/process/text
   */
  async processText(
    request: TextProcessingRequest
  ): Promise<ApiResponse<MultiModalResponse>> {
    return this.request<MultiModalResponse>('/api/multimodal/process/text', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  /**
   * Generate embeddings
   * POST /api/multimodal/embeddings/generate
   */
  async generateEmbedding(
    request: EmbeddingRequest
  ): Promise<ApiResponse<EmbeddingResponse>> {
    return this.request<EmbeddingResponse>('/api/multimodal/embeddings/generate', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  /**
   * Cross-modal similarity search
   * POST /api/multimodal/search/cross-modal
   */
  async crossModalSearch(
    request: CrossModalSearchRequest
  ): Promise<ApiResponse<CrossModalSearchResponse>> {
    return this.request<CrossModalSearchResponse>('/api/multimodal/search/cross-modal', {
      method: 'POST',
      body: JSON.stringify(request),
    });
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

    return this.requestFormData<FusionResponse>('/api/multimodal/fusion/combine', formData);
  }

  /**
   * Get performance statistics
   * GET /api/multimodal/performance/stats
   */
  async getPerformanceStats(): Promise<ApiResponse<PerformanceStats>> {
    return this.request<PerformanceStats>('/api/multimodal/performance/stats');
  }

  /**
   * Get performance summary
   * GET /api/multimodal/performance/summary
   */
  async getPerformanceSummary(): Promise<ApiResponse<PerformanceSummary>> {
    return this.request<PerformanceSummary>('/api/multimodal/performance/summary');
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
    return this.request('/api/multimodal/performance/optimize', {
      method: 'POST',
    });
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
    return this.request(`/api/multimodal/performance/batch-size?${params}`, {
      method: 'POST',
    });
  }
}

// Export singleton instance
export const visionMultimodalApiClient = new VisionMultimodalApiClient();
export default visionMultimodalApiClient;
