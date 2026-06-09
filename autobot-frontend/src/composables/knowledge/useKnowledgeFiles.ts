// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useKnowledgeFiles Composable
 *
 * Knowledge base file upload.
 * Split from useKnowledgeBase (#5122). Dead try/catch wrapper removed (#5123):
 * ApiClient already logs retries + final failure and never returns null.
 *
 * Preserves the apiClient FormData pattern from PR #5116 — rawRequest strips
 * Content-Type so the browser sets the multipart boundary automatically, and
 * inherits the same auth/retry/error-handling as every other API call.
 *
 * Reactive refs layer (#5195, follow-up to #5149): the composable now owns
 * loading/error state via `ref`s and exposes a managed `upload` action. The
 * bare imperative function is still exported at module scope so non-reactive
 * consumers (and the `useKnowledgeBase` BC shim) keep working unchanged.
 */

import { ref, readonly, type Ref } from 'vue'
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import type { UploadResponse } from '@/types/knowledgeBase'

// ==================== Bare imperative API ====================

/**
 * Upload knowledge base file.
 */
export const uploadKnowledgeFile = async (formData: FormData): Promise<UploadResponse> => {
  const data = await apiClient.post<Record<string, unknown>>(
    `${getApiBase()}/knowledge_base/upload`,
    formData
  )
  return data as unknown as UploadResponse
}

// ==================== Reactive composable ====================

export interface UseKnowledgeFilesReturn {
  /** Latest upload response, or null if never uploaded / upload failed. */
  uploadResult: Readonly<Ref<UploadResponse | null>>
  /** True while an upload is in-flight. */
  isUploading: Readonly<Ref<boolean>>
  /** Last error raised by `upload`; cleared on the next call. */
  error: Readonly<Ref<Error | null>>
  /** Upload a file, update `uploadResult` + state refs, return the payload. */
  upload: (formData: FormData) => Promise<UploadResponse>
  // Imperative passthroughs — BC with pre-#5195 callers
  uploadKnowledgeFile: typeof uploadKnowledgeFile
}

export function useKnowledgeFiles(): UseKnowledgeFilesReturn {
  const uploadResult = ref<UploadResponse | null>(null)
  const isUploading = ref(false)
  const error = ref<Error | null>(null)

  const upload = async (formData: FormData): Promise<UploadResponse> => {
    isUploading.value = true
    error.value = null
    try {
      const data = await uploadKnowledgeFile(formData)
      uploadResult.value = data
      return data
    } catch (err) {
      error.value = err instanceof Error ? err : new Error(String(err))
      throw err
    } finally {
      isUploading.value = false
    }
  }

  return {
    uploadResult: readonly(uploadResult) as Readonly<Ref<UploadResponse | null>>,
    isUploading: readonly(isUploading),
    error: readonly(error),
    upload,
    uploadKnowledgeFile,
  }
}
