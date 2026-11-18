// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The last analyses of this visit to the Vision screen (#20644), newest first.
 *
 * Moved from the SLM's Vision tool, which kept the last 10. It lives in memory only: images do not
 * leave the browser for a history store, and the list is gone when the screen closes. Each entry
 * holds an object URL for its preview; it is revoked when the entry falls off the end or the
 * screen's scope ends, so previews do not leak.
 */
import { onScopeDispose, ref } from 'vue'
import type { MultiModalResponse, ProcessingIntent } from '@/types/visionMultimodal'

/** How many analyses the history keeps (the SLM tool's limit). */
export const IMAGE_ANALYSIS_HISTORY_LIMIT = 10

export interface ImageAnalysisEntry {
  id: string
  at: Date
  file: File
  previewUrl: string
  intent: ProcessingIntent
  question?: string
  result: MultiModalResponse
}

export type NewImageAnalysis = Omit<ImageAnalysisEntry, 'id' | 'at' | 'previewUrl'>

export function useImageAnalysisHistory(limit = IMAGE_ANALYSIS_HISTORY_LIMIT) {
  const entries = ref<ImageAnalysisEntry[]>([])
  let counter = 0

  function add(analysis: NewImageAnalysis): ImageAnalysisEntry {
    counter += 1
    const entry = { ...analysis, id: `analysis-${counter}`, at: new Date(), previewUrl: URL.createObjectURL(analysis.file) }
    const kept = [entry, ...entries.value]
    kept.slice(limit).forEach((dropped) => URL.revokeObjectURL(dropped.previewUrl))
    entries.value = kept.slice(0, limit)
    return entry
  }

  function clear(): void {
    entries.value.forEach((entry) => URL.revokeObjectURL(entry.previewUrl))
    entries.value = []
  }

  onScopeDispose(clear)

  return { entries, add, clear }
}
