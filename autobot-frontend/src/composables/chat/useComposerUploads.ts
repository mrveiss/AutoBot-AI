// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The composer's attachments: pick, validate, upload in parallel, retry, cancel, remove (#18243,
 * moved unchanged in behaviour out of ChatInput.vue). Transport and bearer are
 * `utils/conversationFileUpload.ts`; only the server ids ever reach a send (#20195).
 */
import { computed, ref, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import { useToast } from '@autobot/ui'
import { useChatStore } from '@/stores/useChatStore'
import { useChatController } from '@/models/controllers'
import { formatFileSize } from '@/utils/formatHelpers'
import { createLogger } from '@/utils/debugUtils'
import {
  postConversationUpload, describeUploadError, ensureUploadSession, uploadEtaSeconds,
  type ConversationUploadResponse,
} from '@/utils/conversationFileUpload'
import { useUploadCancel, isUploadCancelled } from '@/composables/useUploadCancel'

const logger = createLogger('useComposerUploads')

export const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10MB
const COMPLETE_ROW_LINGER_MS = 2000

export type UploadPhase = 'preparing' | 'uploading' | 'complete' | 'failed' | 'retrying'

export interface UploadItem {
  id: string
  filename: string
  progress: number
  phase: UploadPhase
  current: number
  total: number
  eta?: number
  error?: string
  file?: File
  fileId?: string
  uploadId?: string
}

export function useComposerUploads() {
  const { t } = useI18n()
  const { showToast } = useToast()
  const store = useChatStore()
  const controller = useChatController()

  const attachedFiles = ref<File[]>([])
  const uploadProgress = ref<UploadItem[]>([])
  const pendingUploads = ref(0) // selections and retries not yet settled
  const hasPendingUploads = computed(() => pendingUploads.value > 0)
  const uploadedIds = new WeakMap<File, string>() // File -> server file id (#20195)

  const dropCancelled = (upload: UploadItem): void => {
    uploadProgress.value = uploadProgress.value.filter((u) => u.id !== upload.id)
    showToast(t('chat.input.uploadCancelled', { name: upload.filename }), 'info')
  }
  const { begin, settle, isCancellable, cancel: cancelUpload } = useUploadCancel<UploadItem>(dropCancelled)

  /** The server ids of the attached files: what a send carries, never the File objects. */
  const serverFileIds = (files: File[]): string[] => files.flatMap((f) => uploadedIds.get(f) ?? [])

  const reportProgress = (upload: UploadItem, startTime: number) => (loaded: number, total: number): void => {
    upload.current = loaded
    upload.total = total
    upload.progress = (loaded / total) * 100
    upload.eta = uploadEtaSeconds(loaded, total, Date.now() - startTime)
    upload.phase = 'uploading'
  }

  function markComplete(upload: UploadItem, file: File, response: ConversationUploadResponse): void {
    settle(upload)
    Object.assign(upload, { phase: 'complete', progress: 100 })
    upload.fileId = response.file_info?.file_id
    if (upload.fileId) uploadedIds.set(file, upload.fileId)
    upload.uploadId = response.upload_id
    setTimeout(() => {
      const index = uploadProgress.value.findIndex((u) => u.id === upload.id)
      if (index !== -1) uploadProgress.value.splice(index, 1)
    }, COMPLETE_ROW_LINGER_MS)
  }

  async function uploadFile(upload: UploadItem, file: File): Promise<void> {
    upload.phase = 'uploading'
    const signal = begin(upload)
    try {
      const sessionId = await ensureUploadSession(store, controller)
      markComplete(upload, file, await postConversationUpload(sessionId, file, reportProgress(upload, Date.now()), signal))
    } catch (error) {
      if (!settle(upload, error)) {
        Object.assign(upload, { error: describeUploadError(error, t), phase: 'failed', progress: 0 })
      }
      throw error
    }
  }

  /** A file past the size limit is refused with a toast and never enters the list. */
  function acceptFile(file: File): boolean {
    if (file.size <= MAX_FILE_SIZE) return true
    showToast(t('chat.input.fileTooLarge', { name: file.name, max: formatFileSize(MAX_FILE_SIZE) }), 'warning')
    return false
  }

  function trackUpload(file: File): UploadItem {
    const upload = reactive<UploadItem>({
      id: crypto.randomUUID(), filename: file.name, progress: 0, phase: 'preparing', current: 0, total: file.size, file,
    })
    uploadProgress.value.push(upload)
    return upload
  }

  function settleResults(results: PromiseSettledResult<File>[], uploads: UploadItem[]): void {
    results.forEach((result, index) => {
      if (result.status === 'fulfilled') attachedFiles.value.push(result.value)
      else if (!isUploadCancelled(result.reason)) {
        Object.assign(uploads[index], { error: describeUploadError(result.reason, t), phase: 'failed' })
      }
    })
  }

  /** The hidden file input's change handler: all files upload in parallel (no N+1 sequential uploads). */
  async function handleFileSelect(event: Event): Promise<void> {
    const target = event.target as HTMLInputElement
    const files = Array.from(target.files || []).filter(acceptFile)
    const uploads = files.map(trackUpload)
    pendingUploads.value++
    try {
      const results = await Promise.allSettled(uploads.map(async (upload, i) => {
        await uploadFile(upload, files[i])
        return files[i]
      }))
      settleResults(results, uploads)
    } finally {
      pendingUploads.value--
    }
    target.value = ''
  }

  async function retryUpload(uploadId: string): Promise<void> {
    const upload = uploadProgress.value.find((u) => u.id === uploadId)
    if (!upload || !upload.file) {
      logger.error('Cannot retry upload: Upload or file not found')
      return
    }
    const file = upload.file
    Object.assign(upload, { error: undefined, progress: 0, current: 0, phase: 'retrying' })
    pendingUploads.value++
    try {
      await uploadFile(upload, file)
      if (!attachedFiles.value.includes(file)) attachedFiles.value.push(file) // by identity: two files may share a name
    } catch (error) {
      if (isUploadCancelled(error)) return
      Object.assign(upload, { error: describeUploadError(error, t), phase: 'failed' })
    } finally {
      pendingUploads.value--
    }
  }

  const removeFile = (index: number): void => { attachedFiles.value.splice(index, 1) }
  const clearAllFiles = (): void => { attachedFiles.value = [] }

  return {
    attachedFiles, uploadProgress, hasPendingUploads, isCancellable, cancelUpload,
    serverFileIds, handleFileSelect, retryUpload, removeFile, clearAllFiles,
  }
}
