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
 */

import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import type { UploadResponse } from '@/types/knowledgeBase'

export function useKnowledgeFiles() {
  /**
   * Upload knowledge base file
   */
  const uploadKnowledgeFile = async (formData: FormData): Promise<UploadResponse> => {
    const data = await apiClient.post<Record<string, unknown>>(
      `${getApiBase()}/knowledge_base/upload`,
      formData
    )
    return data as unknown as UploadResponse
  }

  return {
    uploadKnowledgeFile,
  }
}
