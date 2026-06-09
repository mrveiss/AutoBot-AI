// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
// GH#9015 — image generation composable
import apiClient from '@/utils/ApiClient'
import { ref } from 'vue'

export interface GenerateImageParams {
  prompt: string
  provider?: 'dalle' | 'flux' | 'stable_diffusion'
  size?: string
  quality?: 'standard' | 'hd'
  n?: number
  negative_prompt?: string
}

export interface GeneratedImage {
  url: string
  revised_prompt?: string | null
}

export interface ImageGenerationResult {
  success: boolean
  images: GeneratedImage[]
  provider: string
  model: string
  prompt: string
  size: string
  error?: string | null
}

export interface ProviderStatus {
  name: string
  available: boolean
  reason?: string | null
}

export function useImageGeneration() {
  const generating = ref(false)
  const error = ref<string | null>(null)
  const providers = ref<ProviderStatus[]>([])

  async function generateImage(params: GenerateImageParams): Promise<ImageGenerationResult | null> {
    generating.value = true
    error.value = null
    try {
      const result = await apiClient.post<ImageGenerationResult>(
        '/image-generation/generate',
        params,
      )
      if (!result.success) {
        error.value = result.error ?? 'Image generation failed'
      }
      return result
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      error.value = msg
      return null
    } finally {
      generating.value = false
    }
  }

  async function fetchProviders(): Promise<void> {
    try {
      const data = await apiClient.get<{ providers: ProviderStatus[] }>('/image-generation/providers')
      providers.value = data.providers ?? []
    } catch {
      providers.value = []
    }
  }

  return { generating, error, providers, generateImage, fetchProviders }
}
