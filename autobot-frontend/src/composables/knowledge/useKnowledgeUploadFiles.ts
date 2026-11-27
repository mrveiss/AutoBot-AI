// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * The file half of the Knowledge upload screen (#747, #18244): the picked files, drag and drop,
 * previews, and the parallel upload with one progress line per file. Small files go through the
 * controller; media and files over the single-shot limit use the resumable route (#19713).
 */
import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useKnowledgeController } from '@/models/controllers'
import { parseTags } from '@/utils/tagHelpers'
import { resetFormFields } from '@/utils/formHelpers'
import { createLogger } from '@/utils/debugUtils'
import { useExpansion } from '@/composables/useExpansion'
import { KNOWLEDGE_UPLOAD_EXTENSIONS } from '@/constants/knowledgeUpload'
import { useKnowledgeUploadLimit } from '@/composables/knowledge/useKnowledgeUploadLimit'
import { useChunkedUpload } from '@/composables/knowledge/useChunkedUpload'
import type { UploadFeedback } from '@/composables/knowledge/useKnowledgeUploadFeedback'
import {
  detectCategory, generateFileId, getFileExtension, isPreviewable, isValidFileType, readFileAsText,
} from '@/composables/knowledge/knowledgeUploadFileUtils'

const logger = createLogger('useKnowledgeUploadFiles')
const PREVIEW_MAX_LENGTH = 2000
const BYTES_PER_MB = 1048576

export interface FileItem {
  id: string
  file: File
  suggestedCategory: string | null
  preview: string | null
  previewAvailable: boolean
  previewTruncated: boolean
  fullContentLength: number | null
  status: 'pending' | 'uploading' | 'completed' | 'failed'
  progress: number
  errorMessage: string | null
}

/** `accept` is the shared allow-list (`@/constants/knowledgeUpload`) the file input and the resumable route use. */
export function useKnowledgeUploadFiles(feedback: UploadFeedback, accept: string) {
  const { t } = useI18n()
  const controller = useKnowledgeController()
  const { maxMb, loadLimit, exceedsLimit } = useKnowledgeUploadLimit()
  const chunked = useChunkedUpload(accept)
  const { isExpanded, expand, collapseAll } = useExpansion<string>()

  const fileEntry = reactive({ category: '', tagsInput: '' })
  const selectedFiles = ref<FileItem[]>([])
  const fileInput = ref<HTMLInputElement | null>(null)
  const isDragging = ref(false)
  const dragValid = ref(true)
  const dragCounter = ref(0)

  const hasAutoCategories = computed(() => selectedFiles.value.some((f) => f.suggestedCategory !== null))
  const dropZoneIcon = computed(() => {
    if (isDragging.value) return dragValid.value ? 'download' : 'ban'
    return selectedFiles.value.length > 0 ? 'plus' : 'cloud-upload-alt'
  })

  // ---- drag and drop ----
  const onDragOver = (event: DragEvent) => {
    event.preventDefault()
    if (event.dataTransfer) event.dataTransfer.dropEffect = dragValid.value ? 'copy' : 'none'
  }

  function onDragEnter(event: DragEvent): void {
    event.preventDefault()
    dragCounter.value++
    isDragging.value = true
    const items = event.dataTransfer?.items
    if (items) dragValid.value = Array.from(items).every((item) => item.kind === 'file' && isValidFileType(item.type))
  }

  function onDragLeave(event: DragEvent): void {
    event.preventDefault()
    dragCounter.value--
    if (dragCounter.value === 0) {
      isDragging.value = false
      dragValid.value = true
    }
  }

  function onDrop(event: DragEvent): void {
    event.preventDefault()
    isDragging.value = false
    dragCounter.value = 0
    dragValid.value = true
    void addFiles(Array.from(event.dataTransfer?.files || []))
  }

  function onFileSelect(event: Event): void {
    const target = event.target as HTMLInputElement
    void addFiles(Array.from(target.files || []))
    target.value = '' // the same file can be picked again
  }

  // ---- the picked files ----
  function rejectionOf(file: File): string | null {
    const maxBytes = chunked.maxBytesFor(file.name)
    if (maxBytes ? file.size > maxBytes : exceedsLimit(file.size)) {
      return t('knowledge.upload.errorFileTooLarge', { name: file.name, max: maxBytes ? Math.floor(maxBytes / BYTES_PER_MB) : maxMb.value })
    }
    const ext = getFileExtension(file.name).toLowerCase()
    if (!chunked.isMedia(file.name) && !KNOWLEDGE_UPLOAD_EXTENSIONS.includes(ext)) {
      return t('knowledge.upload.errorUnsupportedFormat', { name: file.name })
    }
    return null
  }

  const isDuplicate = (file: File) => selectedFiles.value.some((f) => f.file.name === file.name && f.file.size === file.size)

  function toFileItem(file: File): FileItem {
    return {
      id: generateFileId(), file, suggestedCategory: detectCategory(file.name), preview: null,
      previewAvailable: isPreviewable(file.name), previewTruncated: false, fullContentLength: null,
      status: 'pending', progress: 0, errorMessage: null,
    }
  }

  async function addFiles(files: File[]): Promise<void> {
    feedback.clearError()
    for (const file of files) {
      const rejection = rejectionOf(file)
      if (rejection) feedback.showError(rejection)
      if (rejection || isDuplicate(file)) continue
      const item = toFileItem(file)
      if (item.previewAvailable) void loadFilePreview(item)
      selectedFiles.value.push(item)
    }
  }

  async function loadFilePreview(item: FileItem): Promise<void> {
    try {
      const content = await readFileAsText(item.file)
      item.fullContentLength = content.length
      item.previewTruncated = content.length > PREVIEW_MAX_LENGTH
      item.preview = item.previewTruncated ? content.substring(0, PREVIEW_MAX_LENGTH) : content
    } catch (error) {
      logger.error('Failed to load preview:', error)
      item.previewAvailable = false
    }
  }

  function removeFile(index: number): void {
    const item = selectedFiles.value[index]
    if (item && isExpanded(item.id)) collapseAll()
    if (item) void chunked.cancelUpload(item.file)
    selectedFiles.value.splice(index, 1)
  }

  function clearAllFiles(): void {
    selectedFiles.value = []
    collapseAll()
    if (fileInput.value) fileInput.value.value = ''
  }

  function toggleFilePreview(fileId: string): void {
    const wasExpanded = isExpanded(fileId)
    collapseAll()
    if (!wasExpanded) expand(fileId)
  }

  // ---- upload ----
  async function uploadOne(item: FileItem, tags: string[]): Promise<boolean> {
    item.status = 'uploading'
    item.progress = 0
    try {
      const category = fileEntry.category || item.suggestedCategory || 'Uploads'
      const target = chunked.isMedia(item.file.name) ? 'transcript' : 'document' // #19713
      if (target === 'transcript' || exceedsLimit(item.file.size)) {
        await chunked.uploadInChunks(item.file, { target, category, tags }, (percent) => { item.progress = percent })
      } else {
        await controller.addFileDocument(item.file, category, tags, false)
      }
      item.progress = 100
      item.status = 'completed'
      return true
    } catch (error: unknown) {
      item.status = 'failed'
      item.errorMessage = (error as Error).message || t('knowledge.upload.uploadFailed')
      return false
    }
  }

  async function runUploads(total: number, tags: string[]): Promise<number> {
    let done = 0
    let uploaded = 0
    await Promise.allSettled(
      selectedFiles.value.map(async (item) => {
        if (await uploadOne(item, tags)) uploaded++
        done++
        feedback.progress.percentage = Math.round((done / total) * 100)
        feedback.progress.status = t('knowledge.upload.progressUploaded', { done, total })
      }),
    )
    return uploaded
  }

  async function uploadFiles(): Promise<void> {
    if (selectedFiles.value.length === 0) return
    feedback.begin()
    const total = selectedFiles.value.length
    feedback.startProgress(t('knowledge.upload.uploadingFiles'), t('knowledge.upload.progressUploaded', { done: 0, total }))
    try {
      const uploaded = await runUploads(total, parseTags(fileEntry.tagsInput))
      await controller.loadAllDocuments() // one re-read for the batch (#17530)
      feedback.completeProgress(t('knowledge.upload.uploadComplete'))
      const failed = total - uploaded
      const summary = failed > 0
        ? t('knowledge.upload.uploadSummaryPartial', { uploaded, failed })
        : t('knowledge.upload.uploadSummaryAll', { count: uploaded }, uploaded)
      feedback.showSuccess(summary, () => {
        selectedFiles.value = selectedFiles.value.filter((f) => f.status !== 'completed')
        resetFormFields(fileEntry)
        feedback.hideProgress()
      })
    } catch (error: unknown) {
      feedback.showError((error as Error).message || t('knowledge.upload.errorUploadFiles'))
      feedback.hideProgress()
    } finally {
      feedback.end()
    }
  }

  const onMount = () => {
    controller.loadCategories()
    loadLimit()
    chunked.loadLimits()
  }

  return {
    fileEntry, selectedFiles, fileInput, isDragging, dragValid, hasAutoCategories, dropZoneIcon,
    uploadAccept: chunked.uploadAccept, isFileExpanded: isExpanded,
    onDragOver, onDragEnter, onDragLeave, onDrop, onFileSelect,
    removeFile, clearAllFiles, toggleFilePreview, uploadFiles, onMount,
  }
}
