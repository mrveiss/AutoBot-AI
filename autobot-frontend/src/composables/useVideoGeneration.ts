// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
// GH#9016 — async video generation composable (submit + poll)
import apiClient from '@/utils/ApiClient'
import { ref } from 'vue'

export interface GenerateVideoParams {
  prompt: string
  provider?: 'runway' | 'sora' | 'kling'
  duration?: number
  resolution?: string
  aspect_ratio?: '16:9' | '9:16' | '1:1'
}

export interface VideoJobResponse {
  success: boolean
  job_id: string
  provider: string
  status: string
  error?: string | null
}

export interface VideoStatusResponse {
  success: boolean
  job_id: string
  status: string
  progress: number
  video_url?: string | null
  provider: string
  prompt: string
  error?: string | null
}

export interface VideoProviderStatus {
  name: string
  available: boolean
  reason?: string | null
}

// Poll cadence is env-tunable on the backend; the UI default is conservative.
const DEFAULT_POLL_MS = Number(import.meta.env.VITE_VIDEO_POLL_MS ?? 4000)
const DEFAULT_MAX_POLLS = Number(import.meta.env.VITE_VIDEO_MAX_POLLS ?? 150)

export function useVideoGeneration() {
  const generating = ref(false)
  const progress = ref(0)
  const status = ref<string>('idle')
  const videoUrl = ref<string | null>(null)
  const error = ref<string | null>(null)
  const providers = ref<VideoProviderStatus[]>([])

  async function submit(params: GenerateVideoParams): Promise<VideoJobResponse | null> {
    try {
      const result = await apiClient.post<VideoJobResponse>('/video-generation/generate', params)
      if (!result.success) {
        error.value = result.error ?? 'Video generation failed'
      }
      return result
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : String(err)
      return null
    }
  }

  async function pollStatus(jobId: string): Promise<VideoStatusResponse | null> {
    try {
      return await apiClient.get<VideoStatusResponse>(`/video-generation/status/${jobId}`)
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : String(err)
      return null
    }
  }

  const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

  /** Submit a job and poll until it succeeds, fails, or the ceiling is hit. */
  async function generateVideo(params: GenerateVideoParams): Promise<string | null> {
    generating.value = true
    error.value = null
    progress.value = 0
    videoUrl.value = null
    status.value = 'pending'

    try {
      const job = await submit(params)
      if (!job || !job.success) {
        status.value = 'failed'
        return null
      }
      for (let i = 0; i < DEFAULT_MAX_POLLS; i++) {
        const s = await pollStatus(job.job_id)
        if (!s) {
          status.value = 'failed'
          return null
        }
        status.value = s.status
        progress.value = s.progress ?? 0
        if (s.status === 'succeeded' && s.video_url) {
          videoUrl.value = s.video_url
          progress.value = 1
          return s.video_url
        }
        if (s.status === 'failed') {
          error.value = s.error ?? 'Video generation failed'
          return null
        }
        await sleep(DEFAULT_POLL_MS)
      }
      error.value = 'Video generation timed out'
      status.value = 'failed'
      return null
    } finally {
      generating.value = false
    }
  }

  async function fetchProviders(): Promise<void> {
    try {
      const data = await apiClient.get<{ providers: VideoProviderStatus[] }>('/video-generation/providers')
      providers.value = data.providers ?? []
    } catch {
      providers.value = []
    }
  }

  return {
    generating,
    progress,
    status,
    videoUrl,
    error,
    providers,
    submit,
    pollStatus,
    generateVideo,
    fetchProviders,
  }
}
