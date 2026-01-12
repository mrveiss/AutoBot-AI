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

      <!-- File Upload Method -->
      <div class="upload-method">
        <div class="method-header">
          <i class="fas fa-file-upload"></i>
          <h4>Upload File</h4>
        </div>

        <div class="method-content">
          <div
            class="file-drop-zone"
            :class="{ 'dragging': isDragging }"
            @drop="handleDrop"
            @dragover.prevent="isDragging = true"
            @dragleave="isDragging = false"
          >
            <input
              ref="fileInput"
              type="file"
              multiple
              accept=".txt,.md,.pdf,.doc,.docx,.json,.csv"
              @change="handleFileSelect"
              style="display: none"
            />

            <i class="fas fa-cloud-upload-alt drop-icon"></i>
            <p class="drop-text">
              Drag and drop files here or
              <button @click="fileInput?.click()" class="browse-btn">browse</button>
            </p>
            <p class="drop-hint">
              Supported: TXT, MD, PDF, DOC, DOCX, JSON, CSV (max 10MB)
            </p>
          </div>

          <div v-if="selectedFiles.length > 0" class="selected-files">
            <h5>Selected Files:</h5>
            <div v-for="(file, index) in selectedFiles" :key="index" class="file-item">
              <i :class="getFileIcon(file.name, false)"></i>
              <span class="file-name">{{ file.name }}</span>
              <span class="file-size">({{ formatFileSize(file.size) }})</span>
              <button @click="removeFile(index)" class="remove-file-btn">
                <i class="fas fa-times"></i>
              </button>
            </div>
          </div>

          <div v-if="selectedFiles.length > 0" class="form-row">
            <div class="form-group">
              <label for="file-category">Category for all files</label>
              <select id="file-category" v-model="fileEntry.category" class="form-select">
                <option value="">Select category...</option>
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
            v-if="selectedFiles.length > 0"
            @click="uploadFiles"
            :disabled="isSubmitting"
            class="submit-btn"
          >
            <i class="fas fa-upload"></i>
            Upload {{ selectedFiles.length }} file{{ selectedFiles.length > 1 ? 's' : '' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Upload Progress -->
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
import { ref, reactive, onMounted } from 'vue'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import { useKnowledgeController } from '@/models/controllers'
import { formatFileSize } from '@/utils/formatHelpers'
import { parseTags } from '@/utils/tagHelpers'
import { resetFormFields } from '@/utils/formHelpers'
import { useKnowledgeBase } from '@/composables/useKnowledgeBase'
import { useUploadProgress } from '@/composables/useUploadProgress'
import BaseAlert from '@/components/ui/BaseAlert.vue'

const store = useKnowledgeStore()
const controller = useKnowledgeController()
const { getFileIcon } = useKnowledgeBase()
const { progress: uploadProgress, startProgress, updateProgress, completeProgress, hideProgress, simulateProgress, updateFileProgress } = useUploadProgress()

// Form states
const textEntry = reactive({
  title: '',
  content: '',
  category: '',
  tagsInput: ''
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

// UI state
const isSubmitting = ref(false)
const isDragging = ref(false)
const selectedFiles = ref<File[]>([])
const fileInput = ref<HTMLInputElement | null>(null)
const successMessage = ref('')
const errorMessage = ref('')

// uploadProgress now provided by useUploadProgress() composable

// Methods
const addTextEntry = async () => {
  if (!textEntry.content.trim()) return

  isSubmitting.value = true
  errorMessage.value = ''
  successMessage.value = ''

  try {
    const tags = parseTags(textEntry.tagsInput)

    await controller.addTextDocument(
      textEntry.content,
      textEntry.title,
      textEntry.category || 'General',
      tags
    )

    successMessage.value = 'Text entry added successfully!'

    // Reset form
    resetFormFields(textEntry)

    setTimeout(() => {
      successMessage.value = ''
    }, 3000)

  } catch (error: any) {
    errorMessage.value = error.message || 'Failed to add text entry'
  } finally {
    isSubmitting.value = false
  }
}

const importFromUrl = async () => {
  if (!isValidUrl(urlEntry.url)) return

  isSubmitting.value = true
  errorMessage.value = ''
  successMessage.value = ''

  startProgress('Importing from URL', 'Fetching content...')

  try {
    const tags = parseTags(urlEntry.tagsInput)

    // Simulate progress (auto-increment to 90%)
    const progressInterval = simulateProgress(90, 10, 200)

    await controller.addUrlDocument(
      urlEntry.url,
      urlEntry.category || 'Web Content',
      tags
    )

    clearInterval(progressInterval)
    completeProgress('Import complete!')

    successMessage.value = 'URL content imported successfully!'

    // Reset form
    resetFormFields(urlEntry)

    setTimeout(() => {
      hideProgress()
      successMessage.value = ''
    }, 3000)

  } catch (error: any) {
    errorMessage.value = error.message || 'Failed to import URL'
    hideProgress()
  } finally {
    isSubmitting.value = false
  }
}

const handleDrop = (event: DragEvent) => {
  event.preventDefault()
  isDragging.value = false

  const files = Array.from(event.dataTransfer?.files || [])
  addFiles(files)
}

const handleFileSelect = (event: Event) => {
  const target = event.target as HTMLInputElement
  const files = Array.from(target.files || [])
  addFiles(files)
}

const addFiles = (files: File[]) => {
  const validFiles = files.filter(file => {
    // Check file size (10MB limit)
    if (file.size > 10 * 1024 * 1024) {
      errorMessage.value = `File "${file.name}" is too large (max 10MB)`
      return false
    }

    // Check if already selected
    if (selectedFiles.value.some(f => f.name === file.name)) {
      return false
    }

    return true
  })

  selectedFiles.value.push(...validFiles)
}

const removeFile = (index: number) => {
  selectedFiles.value.splice(index, 1)
}

const uploadFiles = async () => {
  if (selectedFiles.value.length === 0) return

  isSubmitting.value = true
  errorMessage.value = ''
  successMessage.value = ''

  startProgress('Uploading files', `Uploading 0 of ${selectedFiles.value.length} files...`)

  try {
    const tags = parseTags(fileEntry.tagsInput)

    // Upload files in parallel - eliminates N+1 sequential uploads
    let uploaded = 0
    const totalFiles = selectedFiles.value.length

    const uploadPromises = selectedFiles.value.map(async (file) => {
      await controller.addFileDocument(
        file,
        fileEntry.category || 'Uploads',
        tags
      )
      // Update progress as each upload completes
      uploaded++
      updateFileProgress(uploaded, totalFiles, uploaded === totalFiles ? undefined : file.name)
      return file.name
    })

    const results = await Promise.allSettled(uploadPromises)
    const succeeded = results.filter(r => r.status === 'fulfilled').length
    const failed = results.filter(r => r.status === 'rejected').length

    if (failed > 0) {
      successMessage.value = `Uploaded ${succeeded} file${succeeded > 1 ? 's' : ''}, ${failed} failed`
    } else {
      successMessage.value = `Successfully uploaded ${succeeded} file${succeeded > 1 ? 's' : ''}!`
    }

    // Reset
    selectedFiles.value = []
    resetFormFields(fileEntry)
    if (fileInput.value) {
      fileInput.value.value = ''
    }

    setTimeout(() => {
      hideProgress()
      successMessage.value = ''
    }, 3000)

  } catch (error: any) {
    errorMessage.value = error.message || 'Failed to upload files'
    hideProgress()
  } finally {
    isSubmitting.value = false
  }
}

// Utility functions
const isValidUrl = (url: string): boolean => {
  try {
    new URL(url)
    return true
  } catch {
    return false
  }
}

// NOTE: formatFileSize removed - now using shared utility from @/utils/formatHelpers
// NOTE: getFileIcon removed - now using shared utility from @/composables/useKnowledgeBase

// Load categories on mount
onMounted(() => {
  controller.loadCategories()
})
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
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
}

.method-content {
  padding: var(--spacing-6);
}

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

/* File upload styles */
.file-drop-zone {
  border: 2px dashed var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-8);
  text-align: center;
  transition: all var(--duration-200);
  cursor: pointer;
}

.file-drop-zone.dragging {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
}

.drop-icon {
  font-size: var(--text-4xl);
  color: var(--text-tertiary);
  margin-bottom: var(--spacing-4);
}

.drop-text {
  color: var(--text-secondary);
  margin-bottom: var(--spacing-2);
}

.browse-btn {
  color: var(--color-primary);
  text-decoration: underline;
  background: none;
  border: none;
  cursor: pointer;
  font-weight: var(--font-medium);
}

.browse-btn:hover {
  color: var(--color-primary-hover);
}

.drop-hint {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.selected-files {
  margin-top: var(--spacing-4);
}

.selected-files h5 {
  font-weight: var(--font-medium);
  color: var(--text-primary);
  margin-bottom: var(--spacing-2);
}

.file-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  margin-bottom: var(--spacing-2);
}

.file-name {
  flex: 1;
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.file-size {
  color: var(--text-secondary);
  font-size: var(--text-xs);
}

.remove-file-btn {
  width: 1.5rem;
  height: 1.5rem;
  border: none;
  background: var(--color-error);
  color: var(--text-on-primary);
  border-radius: var(--radius-sm);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-xs);
}

.remove-file-btn:hover {
  background: var(--color-error-hover);
}

/* Progress styles */
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


/* Responsive */
@media (max-width: 768px) {
  .upload-methods {
    grid-template-columns: 1fr;
  }

  .form-row {
    grid-template-columns: 1fr;
  }
}
</style>
