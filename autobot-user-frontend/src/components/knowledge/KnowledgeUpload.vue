<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<template>
  <div class="knowledge-upload">
    <div class="upload-header">
      <p class="upload-description">
        Upload documents, add web content, or create new knowledge entries
      </p>
    </div>

    <div class="upload-methods">
      <!-- Text Input Method -->
      <div class="upload-method">
        <div class="method-header">
          <i class="fas fa-keyboard"></i>
          <h4>Text Entry</h4>
        </div>

        <div class="method-content">
          <div class="form-group">
            <label for="text-title">Title</label>
            <input
              id="text-title"
              v-model="textEntry.title"
              type="text"
              class="form-input"
              placeholder="Enter a descriptive title..."
            />
          </div>

          <div class="form-group">
            <label for="text-content">Content *</label>
            <textarea
              id="text-content"
              v-model="textEntry.content"
              class="form-textarea"
              rows="6"
              placeholder="Enter your knowledge content..."
              required
            ></textarea>
            <div class="char-count">
              {{ textEntry.content.length }} characters
            </div>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label for="text-category">Category</label>
              <select id="text-category" v-model="textEntry.category" class="form-select">
                <option value="">Select category...</option>
                <option v-for="cat in store.categories" :key="cat.id" :value="cat.name">
                  {{ cat.name }}
                </option>
              </select>
            </div>

            <div class="form-group">
              <label for="text-tags">Tags</label>
              <input
                id="text-tags"
                v-model="textEntry.tagsInput"
                type="text"
                class="form-input"
                placeholder="Enter tags separated by commas..."
                @keyup.enter="addTextEntry"
              />
            </div>
          </div>

          <!-- Issue #685: Hierarchical Access Controls -->
          <div class="form-row">
            <div class="form-group">
              <label for="text-access-level">Access Level</label>
              <select id="text-access-level" v-model="textEntry.accessLevel" class="form-select">
                <option value="user">User Content (default)</option>
                <option value="system">System Documentation</option>
                <option value="general">Public Knowledge</option>
                <option value="autobot">Platform Documentation</option>
              </select>
              <small class="form-hint">Determines the type of knowledge</small>
            </div>

            <div class="form-group">
              <label for="text-visibility">Visibility</label>
              <select id="text-visibility" v-model="textEntry.visibility" class="form-select">
                <option value="private">Private (only me)</option>
                <option value="shared">Shared (specific users)</option>
                <option value="group">Group (team members)</option>
                <option value="organization">Organization (all org members)</option>
                <option value="system">System (all authenticated users)</option>
              </select>
              <small class="form-hint">Who can access this knowledge</small>
            </div>
          </div>

          <button
            @click="addTextEntry"
            :disabled="!textEntry.content.trim() || isSubmitting"
            class="submit-btn"
          >
            <i class="fas fa-plus"></i>
            Add to Knowledge Base
          </button>
        </div>
      </div>

      <!-- URL Import Method -->
      <div class="upload-method">
        <div class="method-header">
          <i class="fas fa-globe"></i>
          <h4>Import from URL</h4>
        </div>

        <div class="method-content">
          <div class="form-group">
            <label for="url-input">URL *</label>
            <input
              id="url-input"
              v-model="urlEntry.url"
              type="url"
              class="form-input"
              placeholder="https://example.com/article"
              @keyup.enter="importFromUrl"
            />
          </div>

          <div class="form-row">
            <div class="form-group">
              <label for="url-category">Category</label>
              <select id="url-category" v-model="urlEntry.category" class="form-select">
                <option value="">Select category...</option>
                <option v-for="cat in store.categories" :key="cat.id" :value="cat.name">
                  {{ cat.name }}
                </option>
              </select>
            </div>

            <div class="form-group">
              <label for="url-tags">Tags</label>
              <input
                id="url-tags"
                v-model="urlEntry.tagsInput"
                type="text"
                class="form-input"
                placeholder="Enter tags separated by commas..."
              />
            </div>
          </div>

          <button
            @click="importFromUrl"
            :disabled="!isValidUrl(urlEntry.url) || isSubmitting"
            class="submit-btn"
          >
            <i class="fas fa-download"></i>
            Import Content
          </button>
        </div>
      </div>

      <!-- File Upload Method (Issue #747: Enhanced with drag-drop, preview, auto-category) -->
      <div class="upload-method upload-method--file">
        <div class="method-header">
          <i class="fas fa-file-upload"></i>
          <h4>Upload Files</h4>
          <span v-if="selectedFiles.length > 0" class="file-count-badge">
            {{ selectedFiles.length }}
          </span>
        </div>

        <div class="method-content">
          <!-- Enhanced Drop Zone -->
          <div
            class="file-drop-zone"
            :class="{
              'dragging': isDragging,
              'drag-valid': isDragging && dragValid,
              'drag-invalid': isDragging && !dragValid,
              'has-files': selectedFiles.length > 0
            }"
            @drop="handleDrop"
            @dragover.prevent="handleDragOver"
            @dragenter.prevent="handleDragEnter"
            @dragleave="handleDragLeave"
            @click="fileInput?.click()"
          >
            <input
              ref="fileInput"
              type="file"
              multiple
              accept=".txt,.md,.pdf,.doc,.docx,.json,.csv,.yaml,.yml,.xml,.html"
              @change="handleFileSelect"
              style="display: none"
            />

            <div class="drop-zone-content" :class="{ 'compact': selectedFiles.length > 0 }">
              <div class="drop-icon-wrapper">
                <i :class="dropZoneIcon"></i>
              </div>
              <p class="drop-text">
                <template v-if="isDragging">
                  {{ dragValid ? 'Drop files to add' : 'Invalid file type' }}
                </template>
                <template v-else>
                  Drag and drop files here or <span class="browse-link">browse</span>
                </template>
              </p>
              <p v-if="!isDragging" class="drop-hint">
                Supported: TXT, MD, PDF, DOC, DOCX, JSON, CSV, YAML, XML, HTML (max 10MB each)
              </p>
            </div>
          </div>

          <!-- Selected Files List with Preview -->
          <div v-if="selectedFiles.length > 0" class="selected-files">
            <div class="files-header">
              <h5>
                <i class="fas fa-folder-open"></i>
                {{ selectedFiles.length }} file{{ selectedFiles.length > 1 ? 's' : '' }} selected
              </h5>
              <button @click="clearAllFiles" class="clear-all-btn" title="Clear all files">
                <i class="fas fa-trash-alt"></i>
                Clear All
              </button>
            </div>

            <div class="files-list">
              <div
                v-for="(fileItem, index) in selectedFiles"
                :key="fileItem.id"
                class="file-item"
                :class="{
                  'expanded': expandedFileId === fileItem.id,
                  'uploading': fileItem.status === 'uploading',
                  'completed': fileItem.status === 'completed',
                  'failed': fileItem.status === 'failed'
                }"
              >
                <div class="file-item-main" @click="toggleFilePreview(fileItem.id)">
                  <div class="file-icon-wrapper">
                    <i :class="getFileIcon(fileItem.file.name, false)"></i>
                  </div>

                  <div class="file-info">
                    <span class="file-name" :title="fileItem.file.name">
                      {{ truncateFileName(fileItem.file.name, 35) }}
                    </span>
                    <div class="file-meta">
                      <span class="file-size">{{ formatFileSize(fileItem.file.size) }}</span>
                      <span class="file-type">{{ getFileExtension(fileItem.file.name) }}</span>
                      <span
                        v-if="fileItem.suggestedCategory"
                        class="suggested-category"
                        :title="`Auto-detected category: ${fileItem.suggestedCategory}`"
                      >
                        <i class="fas fa-magic"></i>
                        {{ fileItem.suggestedCategory }}
                      </span>
                    </div>
                  </div>

                  <div class="file-actions">
                    <button
                      v-if="fileItem.previewAvailable"
                      class="preview-toggle-btn"
                      :class="{ 'active': expandedFileId === fileItem.id }"
                      @click.stop="toggleFilePreview(fileItem.id)"
                      title="Preview content"
                    >
                      <i :class="expandedFileId === fileItem.id ? 'fas fa-chevron-up' : 'fas fa-eye'"></i>
                    </button>
                    <button
                      class="remove-file-btn"
                      @click.stop="removeFile(index)"
                      title="Remove file"
                    >
                      <i class="fas fa-times"></i>
                    </button>
                  </div>
                </div>

                <!-- File Progress Bar (during upload) -->
                <div v-if="fileItem.status === 'uploading'" class="file-progress">
                  <div class="file-progress-bar">
                    <div
                      class="file-progress-fill"
                      :style="{ width: `${fileItem.progress}%` }"
                    ></div>
                  </div>
                  <span class="file-progress-text">{{ fileItem.progress }}%</span>
                </div>

                <!-- Upload Status -->
                <div v-if="fileItem.status === 'completed'" class="file-status success">
                  <i class="fas fa-check-circle"></i>
                  Uploaded successfully
                </div>
                <div v-if="fileItem.status === 'failed'" class="file-status error">
                  <i class="fas fa-exclamation-circle"></i>
                  {{ fileItem.errorMessage || 'Upload failed' }}
                </div>

                <!-- File Preview Panel -->
                <Transition name="slide">
                  <div v-if="expandedFileId === fileItem.id && fileItem.preview" class="file-preview">
                    <div class="preview-header">
                      <span class="preview-label">Content Preview</span>
                      <span class="preview-chars">
                        {{ fileItem.preview.length }} / {{ fileItem.fullContentLength || '?' }} chars
                      </span>
                    </div>
                    <pre class="preview-content">{{ fileItem.preview }}</pre>
                    <div v-if="fileItem.previewTruncated" class="preview-truncated">
                      <i class="fas fa-info-circle"></i>
                      Preview truncated. Full content will be uploaded.
                    </div>
                  </div>
                </Transition>
              </div>
            </div>
          </div>

          <!-- Category & Tags for All Files -->
          <div v-if="selectedFiles.length > 0" class="batch-options">
            <div class="form-row">
              <div class="form-group">
                <label for="file-category">
                  Category for all files
                  <span v-if="hasAutoCategories" class="auto-detect-hint">
                    (or use auto-detected)
                  </span>
                </label>
                <select id="file-category" v-model="fileEntry.category" class="form-select">
                  <option value="">
                    {{ hasAutoCategories ? 'Use auto-detected categories' : 'Select category...' }}
                  </option>
                  <option v-for="cat in store.categories" :key="cat.id" :value="cat.name">
                    {{ cat.name }}
                  </option>
                </select>
              </div>

              <div class="form-group">
                <label for="file-tags">Tags for all files</label>
                <input
                  id="file-tags"
                  v-model="fileEntry.tagsInput"
                  type="text"
                  class="form-input"
                  placeholder="Enter tags separated by commas..."
                />
              </div>
            </div>

            <button
              @click="uploadFiles"
              :disabled="isSubmitting || selectedFiles.length === 0"
              class="submit-btn upload-btn"
            >
              <template v-if="isSubmitting">
                <i class="fas fa-spinner fa-spin"></i>
                Uploading...
              </template>
              <template v-else>
                <i class="fas fa-cloud-upload-alt"></i>
                Upload {{ selectedFiles.length }} file{{ selectedFiles.length > 1 ? 's' : '' }}
              </template>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Overall Upload Progress -->
    <div v-if="uploadProgress.show" class="upload-progress">
      <div class="progress-header">
        <h4>{{ uploadProgress.title }}</h4>
        <span class="progress-percentage">{{ uploadProgress.percentage }}%</span>
      </div>
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: uploadProgress.percentage + '%' }"></div>
      </div>
      <p class="progress-status">{{ uploadProgress.status }}</p>
    </div>

    <!-- Success/Error Messages -->
    <BaseAlert
      v-if="successMessage"
      variant="success"
      :message="successMessage"
    />

    <BaseAlert
      v-if="errorMessage"
      variant="error"
      :message="errorMessage"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * Knowledge Upload Component (Issue #747)
 *
 * Enhanced file upload with:
 * - Drag-and-drop with visual feedback
 * - File content preview before upload
 * - Auto-category detection from file type/name
 * - Individual file progress tracking
 * - Batch upload with parallel processing
 */

import { ref, reactive, computed, onMounted } from 'vue'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import { useKnowledgeController } from '@/models/controllers'
import { formatFileSize } from '@/utils/formatHelpers'
import { parseTags } from '@/utils/tagHelpers'
import { resetFormFields } from '@/utils/formHelpers'
import { useKnowledgeBase } from '@/composables/useKnowledgeBase'
import { useUploadProgress } from '@/composables/useUploadProgress'
import BaseAlert from '@/components/ui/BaseAlert.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('KnowledgeUpload')

// =============================================================================
// Type Definitions
// =============================================================================

interface FileItem {
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

// =============================================================================
// Composables & Store
// =============================================================================

const store = useKnowledgeStore()
const controller = useKnowledgeController()
const { getFileIcon } = useKnowledgeBase()
const {
  progress: uploadProgress,
  startProgress,
  completeProgress,
  hideProgress,
  simulateProgress
} = useUploadProgress()

// =============================================================================
// Form State
// =============================================================================

const textEntry = reactive({
  title: '',
  content: '',
  category: '',
  tagsInput: '',
  // Issue #685: Hierarchical access fields
  accessLevel: 'user',
  visibility: 'private'
})

const urlEntry = reactive({
  url: '',
  category: '',
  tagsInput: ''
})

const fileEntry = reactive({
  category: '',
  tagsInput: ''
})

// =============================================================================
// UI State
// =============================================================================

const isSubmitting = ref(false)
const isDragging = ref(false)
const dragValid = ref(true)
const dragCounter = ref(0)
const selectedFiles = ref<FileItem[]>([])
const expandedFileId = ref<string | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const successMessage = ref('')
const errorMessage = ref('')

// =============================================================================
// Constants
// =============================================================================

const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10MB
const PREVIEW_MAX_LENGTH = 2000
const SUPPORTED_EXTENSIONS = [
  '.txt', '.md', '.pdf', '.doc', '.docx',
  '.json', '.csv', '.yaml', '.yml', '.xml', '.html'
]
const PREVIEWABLE_EXTENSIONS = ['.txt', '.md', '.json', '.csv', '.yaml', '.yml', '.xml', '.html']

// Category detection patterns
const CATEGORY_PATTERNS: Record<string, RegExp[]> = {
  'Documentation': [/readme/i, /doc/i, /guide/i, /manual/i, /\.md$/i],
  'API': [/api/i, /swagger/i, /openapi/i, /endpoint/i],
  'Configuration': [/config/i, /\.yaml$/i, /\.yml$/i, /\.json$/i, /settings/i],
  'Code': [/\.py$/i, /\.js$/i, /\.ts$/i, /script/i, /function/i],
  'Data': [/\.csv$/i, /data/i, /dataset/i, /export/i],
  'Web Content': [/\.html$/i, /\.xml$/i, /web/i, /page/i]
}

// =============================================================================
// Issue #685: Validation Helpers
// =============================================================================

/**
 * Validates hierarchical access level combinations
 * @param visibility - The visibility level
 * @param fields - Object containing org_id, team_ids, shared_with
 * @returns Error message if validation fails, null if valid
 */
function validateAccessLevelCombination(
  visibility: string,
  fields: { org_id?: string; team_ids?: string[]; shared_with?: string[] }
): string | null {
  if (visibility === 'organization' && !fields.org_id) {
    return 'Organization ID is required when visibility is set to "Organization"'
  }

  if (visibility === 'group' && (!fields.team_ids || fields.team_ids.length === 0)) {
    return 'At least one Team ID is required when visibility is set to "Group"'
  }

  if (visibility === 'shared' && (!fields.shared_with || fields.shared_with.length === 0)) {
    return 'At least one user must be specified when visibility is set to "Shared"'
  }

  return null
}

// =============================================================================
// Computed
// =============================================================================

const dropZoneIcon = computed(() => {
  if (isDragging.value) {
    return dragValid.value ? 'fas fa-download fa-bounce' : 'fas fa-ban'
  }
  return selectedFiles.value.length > 0 ? 'fas fa-plus' : 'fas fa-cloud-upload-alt'
})

const hasAutoCategories = computed(() => {
  return selectedFiles.value.some(f => f.suggestedCategory !== null)
})

// =============================================================================
// Methods - Text Entry
// =============================================================================

async function addTextEntry(): Promise<void> {
  if (!textEntry.content.trim()) return

  // Issue #685: Frontend validation for hierarchical access
  const validationError = validateAccessLevelCombination(textEntry.visibility, {
    org_id: undefined, // Not collected in text entry form yet
    team_ids: undefined, // Not collected in text entry form yet
    shared_with: undefined // Not collected in text entry form yet
  })

  if (validationError) {
    errorMessage.value = validationError
    return
  }

  isSubmitting.value = true
  errorMessage.value = ''
  successMessage.value = ''

  try {
    const tags = parseTags(textEntry.tagsInput)

    // Issue #685: Pass hierarchical access fields
    await controller.addTextDocument(
      textEntry.content,
      textEntry.title,
      textEntry.category || 'General',
      tags,
      {
        access_level: textEntry.accessLevel,
        visibility: textEntry.visibility
      }
    )

    successMessage.value = 'Text entry added successfully!'
    resetFormFields(textEntry)

    setTimeout(() => {
      successMessage.value = ''
    }, 3000)

  } catch (error: unknown) {
    const err = error as Error
    errorMessage.value = err.message || 'Failed to add text entry'
  } finally {
    isSubmitting.value = false
  }
}

// =============================================================================
// Methods - URL Import
// =============================================================================

async function importFromUrl(): Promise<void> {
  if (!isValidUrl(urlEntry.url)) return

  isSubmitting.value = true
  errorMessage.value = ''
  successMessage.value = ''

  startProgress('Importing from URL', 'Fetching content...')

  try {
    const tags = parseTags(urlEntry.tagsInput)
    const progressInterval = simulateProgress(90, 10, 200)

    await controller.addUrlDocument(
      urlEntry.url,
      urlEntry.category || 'Web Content',
      tags
    )

    clearInterval(progressInterval)
    completeProgress('Import complete!')

    successMessage.value = 'URL content imported successfully!'
    resetFormFields(urlEntry)

    setTimeout(() => {
      hideProgress()
      successMessage.value = ''
    }, 3000)

  } catch (error: unknown) {
    const err = error as Error
    errorMessage.value = err.message || 'Failed to import URL'
    hideProgress()
  } finally {
    isSubmitting.value = false
  }
}

// =============================================================================
// Methods - Drag & Drop
// =============================================================================

function handleDragOver(event: DragEvent): void {
  event.preventDefault()
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = dragValid.value ? 'copy' : 'none'
  }
}

function handleDragEnter(event: DragEvent): void {
  event.preventDefault()
  dragCounter.value++
  isDragging.value = true

  // Validate files being dragged
  if (event.dataTransfer?.items) {
    const items = Array.from(event.dataTransfer.items)
    dragValid.value = items.every(item => {
      if (item.kind !== 'file') return false
      const type = item.type
      // Check by MIME type or allow if empty (browser may not provide)
      return type === '' || isValidFileType(type)
    })
  }
}

function handleDragLeave(event: DragEvent): void {
  event.preventDefault()
  dragCounter.value--
  if (dragCounter.value === 0) {
    isDragging.value = false
    dragValid.value = true
  }
}

function handleDrop(event: DragEvent): void {
  event.preventDefault()
  isDragging.value = false
  dragCounter.value = 0
  dragValid.value = true

  const files = Array.from(event.dataTransfer?.files || [])
  addFiles(files)
}

function handleFileSelect(event: Event): void {
  const target = event.target as HTMLInputElement
  const files = Array.from(target.files || [])
  addFiles(files)
  // Reset input to allow selecting same file again
  if (target) target.value = ''
}

// =============================================================================
// Methods - File Management
// =============================================================================

async function addFiles(files: File[]): Promise<void> {
  errorMessage.value = ''

  for (const file of files) {
    // Validate file size
    if (file.size > MAX_FILE_SIZE) {
      errorMessage.value = `File "${file.name}" is too large (max 10MB)`
      continue
    }

    // Validate file type
    const ext = getFileExtension(file.name).toLowerCase()
    if (!SUPPORTED_EXTENSIONS.includes(ext)) {
      errorMessage.value = `File "${file.name}" has unsupported format`
      continue
    }

    // Check for duplicates
    if (selectedFiles.value.some(f => f.file.name === file.name && f.file.size === file.size)) {
      continue
    }

    // Create file item
    const fileItem: FileItem = {
      id: generateId(),
      file,
      suggestedCategory: detectCategory(file.name),
      preview: null,
      previewAvailable: isPreviewable(file.name),
      previewTruncated: false,
      fullContentLength: null,
      status: 'pending',
      progress: 0,
      errorMessage: null
    }

    // Load preview for previewable files
    if (fileItem.previewAvailable) {
      loadFilePreview(fileItem)
    }

    selectedFiles.value.push(fileItem)
  }
}

async function loadFilePreview(fileItem: FileItem): Promise<void> {
  try {
    const content = await readFileAsText(fileItem.file)
    fileItem.fullContentLength = content.length

    if (content.length > PREVIEW_MAX_LENGTH) {
      fileItem.preview = content.substring(0, PREVIEW_MAX_LENGTH)
      fileItem.previewTruncated = true
    } else {
      fileItem.preview = content
      fileItem.previewTruncated = false
    }
  } catch (error) {
    logger.error('Failed to load preview:', error)
    fileItem.previewAvailable = false
  }
}

function readFileAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = () => reject(reader.error)
    reader.readAsText(file, 'utf-8')
  })
}

function removeFile(index: number): void {
  const file = selectedFiles.value[index]
  if (file && expandedFileId.value === file.id) {
    expandedFileId.value = null
  }
  selectedFiles.value.splice(index, 1)
}

function clearAllFiles(): void {
  selectedFiles.value = []
  expandedFileId.value = null
  if (fileInput.value) {
    fileInput.value.value = ''
  }
}

function toggleFilePreview(fileId: string): void {
  expandedFileId.value = expandedFileId.value === fileId ? null : fileId
}

// =============================================================================
// Methods - Upload
// =============================================================================

async function uploadFiles(): Promise<void> {
  if (selectedFiles.value.length === 0) return

  isSubmitting.value = true
  errorMessage.value = ''
  successMessage.value = ''

  const totalFiles = selectedFiles.value.length
  startProgress('Uploading files', `Uploading 0 of ${totalFiles} files...`)

  try {
    const tags = parseTags(fileEntry.tagsInput)
    let uploadedCount = 0
    let failedCount = 0

    // Process uploads in parallel with individual progress tracking
    const uploadPromises = selectedFiles.value.map(async (fileItem) => {
      fileItem.status = 'uploading'
      fileItem.progress = 0

      try {
        // Determine category (use override or auto-detected or default)
        const category = fileEntry.category || fileItem.suggestedCategory || 'Uploads'

        // Simulate progress updates
        const progressInterval = setInterval(() => {
          if (fileItem.progress < 90) {
            fileItem.progress += 10
          }
        }, 100)

        await controller.addFileDocument(fileItem.file, category, tags)

        clearInterval(progressInterval)
        fileItem.progress = 100
        fileItem.status = 'completed'
        uploadedCount++

      } catch (error: unknown) {
        const err = error as Error
        fileItem.status = 'failed'
        fileItem.errorMessage = err.message || 'Upload failed'
        failedCount++
      }

      // Update overall progress
      const completed = uploadedCount + failedCount
      const percentage = Math.round((completed / totalFiles) * 100)
      uploadProgress.value.percentage = percentage
      uploadProgress.value.status = `Uploaded ${completed} of ${totalFiles} files...`
    })

    await Promise.allSettled(uploadPromises)

    // Show completion message
    if (failedCount > 0) {
      successMessage.value = `Uploaded ${uploadedCount} file${uploadedCount !== 1 ? 's' : ''}, ${failedCount} failed`
    } else {
      successMessage.value = `Successfully uploaded ${uploadedCount} file${uploadedCount !== 1 ? 's' : ''}!`
    }

    completeProgress('Upload complete!')

    // Clear successfully uploaded files after delay
    setTimeout(() => {
      selectedFiles.value = selectedFiles.value.filter(f => f.status !== 'completed')
      resetFormFields(fileEntry)
      hideProgress()
      successMessage.value = ''
    }, 3000)

  } catch (error: unknown) {
    const err = error as Error
    errorMessage.value = err.message || 'Failed to upload files'
    hideProgress()
  } finally {
    isSubmitting.value = false
  }
}

// =============================================================================
// Utility Functions
// =============================================================================

function isValidUrl(url: string): boolean {
  try {
    new URL(url)
    return true
  } catch {
    return false
  }
}

function isValidFileType(mimeType: string): boolean {
  const validTypes = [
    'text/plain', 'text/markdown', 'text/csv', 'text/html', 'text/xml',
    'application/json', 'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/x-yaml', 'text/yaml'
  ]
  return validTypes.includes(mimeType)
}

function isPreviewable(filename: string): boolean {
  const ext = getFileExtension(filename).toLowerCase()
  return PREVIEWABLE_EXTENSIONS.includes(ext)
}

function getFileExtension(filename: string): string {
  const lastDot = filename.lastIndexOf('.')
  return lastDot >= 0 ? filename.substring(lastDot) : ''
}

function truncateFileName(name: string, maxLength: number): string {
  if (name.length <= maxLength) return name

  const ext = getFileExtension(name)
  const baseName = name.substring(0, name.length - ext.length)
  const truncatedBase = baseName.substring(0, maxLength - ext.length - 3)

  return `${truncatedBase}...${ext}`
}

function detectCategory(filename: string): string | null {
  for (const [category, patterns] of Object.entries(CATEGORY_PATTERNS)) {
    if (patterns.some(pattern => pattern.test(filename))) {
      return category
    }
  }
  return null
}

function generateId(): string {
  return `file-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`
}

// =============================================================================
// Lifecycle
// =============================================================================

onMounted(() => {
  controller.loadCategories()
})
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
/* Issue #747: Enhanced with drag-drop visual feedback */

.knowledge-upload {
  padding: var(--spacing-6);
}

.upload-header {
  margin-bottom: var(--spacing-8);
}

.upload-header h3 {
  font-size: var(--text-xl);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin-bottom: var(--spacing-2);
}

.upload-description {
  color: var(--text-secondary);
}

.upload-methods {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
  gap: var(--spacing-6);
}

.upload-method {
  background: var(--bg-primary);
  border: 2px solid var(--border-default);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.upload-method--file {
  grid-column: 1 / -1;
}

.method-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-4) var(--spacing-6);
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-default);
}

.method-header i {
  font-size: var(--text-xl);
  color: var(--color-primary);
}

.method-header h4 {
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  flex: 1;
}

.file-count-badge {
  background: var(--color-primary);
  color: var(--text-on-primary);
  font-size: var(--text-xs);
  font-weight: var(--font-bold);
  padding: 0.125rem 0.5rem;
  border-radius: var(--radius-full);
  min-width: 1.25rem;
  text-align: center;
}

.method-content {
  padding: var(--spacing-6);
}

/* Form Styles */
.form-group {
  margin-bottom: var(--spacing-5);
}

.form-group label {
  display: block;
  margin-bottom: var(--spacing-2);
  font-weight: var(--font-medium);
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.form-input,
.form-textarea,
.form-select {
  width: 100%;
  padding: var(--spacing-2-5);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  transition: all var(--duration-200);
  background: var(--bg-primary);
  color: var(--text-primary);
}

.form-input:focus,
.form-textarea:focus,
.form-select:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--ring-primary);
}

.char-count {
  text-align: right;
  font-size: var(--text-xs);
  color: var(--text-secondary);
  margin-top: var(--spacing-1);
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-4);
}

.submit-btn {
  width: 100%;
  padding: var(--spacing-3);
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
  border-radius: var(--radius-md);
  font-weight: var(--font-medium);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
  transition: all var(--duration-200);
}

.submit-btn:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Enhanced Drop Zone */
.file-drop-zone {
  border: 2px dashed var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-8);
  text-align: center;
  transition: all var(--duration-200);
  cursor: pointer;
  position: relative;
  overflow: hidden;
}

.file-drop-zone::before {
  content: '';
  position: absolute;
  inset: 0;
  background: var(--color-primary);
  opacity: 0;
  transition: opacity var(--duration-200);
  pointer-events: none;
}

.file-drop-zone:hover {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
}

.file-drop-zone.dragging {
  border-style: solid;
  border-width: 3px;
}

.file-drop-zone.drag-valid {
  border-color: var(--color-success);
  background: rgba(var(--color-success-rgb), 0.1);
}

.file-drop-zone.drag-valid::before {
  background: var(--color-success);
  opacity: 0.05;
}

.file-drop-zone.drag-invalid {
  border-color: var(--color-error);
  background: rgba(var(--color-error-rgb), 0.1);
}

.file-drop-zone.has-files {
  padding: var(--spacing-4);
}

.drop-zone-content {
  position: relative;
  z-index: 1;
}

.drop-zone-content.compact {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-3);
}

.drop-zone-content.compact .drop-icon-wrapper {
  margin-bottom: 0;
}

.drop-zone-content.compact .drop-text {
  margin-bottom: 0;
}

.drop-zone-content.compact .drop-hint {
  display: none;
}

.drop-icon-wrapper {
  margin-bottom: var(--spacing-4);
}

.drop-icon-wrapper i {
  font-size: var(--text-4xl);
  color: var(--text-tertiary);
  transition: all var(--duration-200);
}

.drag-valid .drop-icon-wrapper i {
  color: var(--color-success);
}

.drag-invalid .drop-icon-wrapper i {
  color: var(--color-error);
}

.drop-text {
  color: var(--text-secondary);
  margin-bottom: var(--spacing-2);
}

.browse-link {
  color: var(--color-primary);
  text-decoration: underline;
  font-weight: var(--font-medium);
  cursor: pointer;
}

.browse-link:hover {
  color: var(--color-primary-hover);
}

.drop-hint {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

/* Selected Files */
.selected-files {
  margin-top: var(--spacing-4);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.files-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-3) var(--spacing-4);
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-default);
}

.files-header h5 {
  font-weight: var(--font-medium);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  margin: 0;
}

.files-header h5 i {
  color: var(--color-primary);
}

.clear-all-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
  padding: var(--spacing-1) var(--spacing-2);
  background: none;
  border: none;
  color: var(--color-error);
  font-size: var(--text-sm);
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: all var(--duration-150);
}

.clear-all-btn:hover {
  background: rgba(var(--color-error-rgb), 0.1);
}

.files-list {
  max-height: 300px;
  overflow-y: auto;
}

/* File Item */
.file-item {
  border-bottom: 1px solid var(--border-light);
  transition: background var(--duration-150);
}

.file-item:last-child {
  border-bottom: none;
}

.file-item:hover {
  background: var(--bg-secondary);
}

.file-item.expanded {
  background: var(--bg-secondary);
}

.file-item.uploading {
  background: rgba(var(--color-primary-rgb), 0.05);
}

.file-item.completed {
  background: rgba(var(--color-success-rgb), 0.05);
}

.file-item.failed {
  background: rgba(var(--color-error-rgb), 0.05);
}

.file-item-main {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3) var(--spacing-4);
  cursor: pointer;
}

.file-icon-wrapper {
  width: 2.5rem;
  height: 2.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  flex-shrink: 0;
}

.file-info {
  flex: 1;
  min-width: 0;
}

.file-name {
  display: block;
  font-weight: var(--font-medium);
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.file-meta {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  margin-top: var(--spacing-1);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.file-type {
  text-transform: uppercase;
  font-weight: var(--font-medium);
}

.suggested-category {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1);
  padding: 0.125rem var(--spacing-2);
  background: var(--color-info-bg);
  color: var(--color-info);
  border-radius: var(--radius-full);
  font-size: 0.625rem;
}

.suggested-category i {
  font-size: 0.5rem;
}

.file-actions {
  display: flex;
  gap: var(--spacing-1);
}

.preview-toggle-btn,
.remove-file-btn {
  width: 1.75rem;
  height: 1.75rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--duration-150);
}

.preview-toggle-btn {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.preview-toggle-btn:hover,
.preview-toggle-btn.active {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.remove-file-btn {
  background: transparent;
  color: var(--text-tertiary);
}

.remove-file-btn:hover {
  background: var(--color-error-bg);
  color: var(--color-error);
}

/* File Progress */
.file-progress {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: 0 var(--spacing-4) var(--spacing-2);
}

.file-progress-bar {
  flex: 1;
  height: 4px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.file-progress-fill {
  height: 100%;
  background: var(--color-primary);
  transition: width var(--duration-200);
}

.file-progress-text {
  font-size: var(--text-xs);
  color: var(--color-primary);
  font-weight: var(--font-medium);
  min-width: 2.5rem;
  text-align: right;
}

/* File Status */
.file-status {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-4);
  font-size: var(--text-sm);
}

.file-status.success {
  color: var(--color-success);
}

.file-status.error {
  color: var(--color-error);
}

/* File Preview */
.file-preview {
  border-top: 1px solid var(--border-light);
  padding: var(--spacing-3) var(--spacing-4);
  background: var(--bg-primary);
}

.preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-2);
}

.preview-label {
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.preview-chars {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.preview-content {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  line-height: 1.6;
  color: var(--text-primary);
  background: var(--bg-tertiary);
  padding: var(--spacing-3);
  border-radius: var(--radius-md);
  white-space: pre-wrap;
  word-wrap: break-word;
  max-height: 200px;
  overflow-y: auto;
  margin: 0;
}

.preview-truncated {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  margin-top: var(--spacing-2);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.preview-truncated i {
  color: var(--color-info);
}

/* Batch Options */
.batch-options {
  margin-top: var(--spacing-4);
  padding-top: var(--spacing-4);
  border-top: 1px solid var(--border-default);
}

.auto-detect-hint {
  font-weight: var(--font-normal);
  color: var(--text-secondary);
  font-size: var(--text-xs);
}

.upload-btn {
  margin-top: var(--spacing-4);
}

/* Overall Progress */
.upload-progress {
  margin-top: var(--spacing-6);
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-2);
}

.progress-header h4 {
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.progress-percentage {
  font-weight: var(--font-semibold);
  color: var(--color-primary);
}

.progress-bar {
  height: 0.5rem;
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
  overflow: hidden;
  margin-bottom: var(--spacing-2);
}

.progress-fill {
  height: 100%;
  background: var(--color-primary);
  transition: width var(--duration-300) ease;
}

.progress-status {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

/* Transitions */
.slide-enter-active,
.slide-leave-active {
  transition: all var(--duration-200) ease;
}

.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  max-height: 0;
  padding-top: 0;
  padding-bottom: 0;
}

.slide-enter-to,
.slide-leave-from {
  max-height: 300px;
}

/* Responsive */
@media (max-width: 768px) {
  .upload-methods {
    grid-template-columns: 1fr;
  }

  .upload-method--file {
    grid-column: auto;
  }

  .form-row {
    grid-template-columns: 1fr;
  }

  .file-item-main {
    flex-wrap: wrap;
  }

  .file-info {
    flex: 0 0 calc(100% - 4rem);
  }

  .file-actions {
    flex: 0 0 100%;
    justify-content: flex-end;
    margin-top: var(--spacing-2);
  }
}
</style>
