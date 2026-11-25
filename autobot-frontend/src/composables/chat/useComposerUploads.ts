// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The composer's attachments: pick, validate, upload in parallel, retry, cancel, remove (#18243,
 * moved unchanged in behaviour out of ChatInput.vue). Transport and bearer are
 * `utils/conversationFileUpload.ts`; only the server ids ever reach a send (#20195). An upload belongs to the
 * chat it was sent to and keeps uploading when the person opens another: the finished file joins that chat's own
 * attachment list (restored on return, never shown in another chat), and a send carries only the ids uploaded
 * to the chat it goes to.
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
const NO_CHAT = '' // the attachment list of a composer with no chat open

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
  sessionId?: string // the chat this upload was sent to
}

export function useComposerUploads() {
  const { t } = useI18n()
  const { showToast } = useToast()
  const store = useChatStore()
  const controller = useChatController()

  const filesByChat = reactive<Record<string, File[]>>({}) // chat id -> its attached files
  const chatKey = (): string => store.currentSessionId ?? NO_CHAT
  /** The open chat's attached files; assigning replaces that chat's list only. */
  const attachedFiles = computed<File[]>({
    get: () => filesByChat[chatKey()] ?? [],
    set: (files) => { filesByChat[chatKey()] = files },
  })
  const uploadProgress = ref<UploadItem[]>([])
  const pendingUploads = ref(0) // selections and retries not yet settled
  const hasPendingUploads = computed(() => pendingUploads.value > 0)
  const uploadedIds = new WeakMap<File, { fileId?: string; sessionId: string }>() // File -> server id + its chat (#20195)

  const dropCancelled = (upload: UploadItem): void => {
    uploadProgress.value = uploadProgress.value.filter((u) => u.id !== upload.id)
    showToast(t('chat.input.uploadCancelled', { name: upload.filename }), 'info')
  }
  const { begin, settle, isCancellable, cancel: cancelUpload } = useUploadCancel<UploadItem>(dropCancelled)

  /** The server ids of the attached files: what a send carries, never the File objects. */
  const serverFileIds = (files: File[]): string[] =>
    files.flatMap((f) => {
      const stored = uploadedIds.get(f)
      return stored?.fileId && stored.sessionId === store.currentSessionId ? stored.fileId : []
    })

  /** A finished upload joins the list of the chat it was sent to, whichever chat is open now. */
  function attach(file: File): void {
    const chat = uploadedIds.get(file)?.sessionId
    if (chat === undefined) return
    const list = filesByChat[chat] ?? []
    if (!list.includes(file)) filesByChat[chat] = [...list, file] // by identity: two files may share a name
  }

  const reportProgress = (upload: UploadItem, startTime: number) => (loaded: number, total: number): void => {
    upload.current = loaded
    upload.total = total
    upload.progress = (loaded / total) * 100
    upload.eta = uploadEtaSeconds(loaded, total, Date.now() - startTime)
    upload.phase = 'uploading'
  }

  function markComplete(upload: UploadItem, file: File, sessionId: string, response: ConversationUploadResponse): void {
    settle(upload)
    Object.assign(upload, { phase: 'complete', progress: 100 })
    upload.fileId = response.file_info?.file_id
    uploadedIds.set(file, { fileId: upload.fileId, sessionId })
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
      upload.sessionId = sessionId
      markComplete(upload, file, sessionId, await postConversationUpload(sessionId, file, reportProgress(upload, Date.now()), signal))
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
      if (result.status === 'fulfilled') attach(result.value)
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
      attach(file)
    } catch (error) {
      if (isUploadCancelled(error)) return
      Object.assign(upload, { error: describeUploadError(error, t), phase: 'failed' })
    } finally {
      pendingUploads.value--
    }
  }

  const removeFile = (index: number): void => { attachedFiles.value = attachedFiles.value.filter((_, i) => i !== index) }
  const clearAllFiles = (): void => { attachedFiles.value = [] }

  return {
    attachedFiles, uploadProgress, hasPendingUploads, isCancellable, cancelUpload,
    serverFileIds, handleFileSelect, retryUpload, removeFile, clearAllFiles,
  }
}
