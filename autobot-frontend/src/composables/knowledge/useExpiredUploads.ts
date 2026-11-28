// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #20905: an admin lists abandoned chunked uploads (#19713) and frees one.
 * Freeing is a person's decision and is audited server-side before anything is removed.
 */
import { ref } from 'vue'
import apiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useExpiredUploads')

export interface ExpiredUpload {
  upload_id: string
  filename: string
  total_size: number
  received: number
  state: string
}

export function useExpiredUploads() {
  const uploads = ref<ExpiredUpload[]>([])
  const loaded = ref(false)
  const loadFailed = ref(false)

  async function load(): Promise<void> {
    loadFailed.value = false
    try {
      const reply: { expired: ExpiredUpload[] } = await apiClient.get('/api/knowledge_base/uploads/expired')
      uploads.value = reply.expired
    } catch (err) {
      loadFailed.value = true
      logger.error('Could not list abandoned uploads', err)
    } finally {
      loaded.value = true
    }
  }

  /** Free one abandoned upload; throws the client's error when the server refuses, after reloading the list
   *  so a row another admin freed (404) or that is no longer removable (409) does not linger. */
  async function remove(uploadId: string): Promise<void> {
    try {
      await apiClient.delete(`/api/knowledge_base/uploads/expired/${encodeURIComponent(uploadId)}`)
    } catch (err) {
      await load()
      throw err
    }
    uploads.value = uploads.value.filter((u) => u.upload_id !== uploadId)
  }

  return { uploads, loaded, loadFailed, load, remove }
}
