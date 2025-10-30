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
              <button @click="$refs.fileInput.click()" class="browse-btn">browse</button>
            </p>
            <p class="drop-hint">
              Supported: TXT, MD, PDF, DOC, DOCX, JSON, CSV (max 10MB)
            </p>
          </div>

          <div v-if="selectedFiles.length > 0" class="selected-files">
            <h5>Selected Files:</h5>
            <div v-for="(file, index) in selectedFiles" :key="index" class="file-item">
              <i :class="getFileIcon(file.type)"></i>
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
    <div v-if="successMessage" class="alert alert-success">
      <i class="fas fa-check-circle"></i>
      {{ successMessage }}
    </div>

    <div v-if="errorMessage" class="alert alert-error">
      <i class="fas fa-exclamation-circle"></i>
      {{ errorMessage }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import { useKnowledgeController } from '@/models/controllers'
import { formatFileSize } from '@/utils/formatHelpers'

const store = useKnowledgeStore()
const controller = useKnowledgeController()

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
const fileInput = ref<HTMLInputElement>()
const successMessage = ref('')
const errorMessage = ref('')

const uploadProgress = reactive({
  show: false,
  title: '',
  percentage: 0,
  status: ''
})

// Methods
const addTextEntry = async () => {
  if (!textEntry.content.trim()) return

  isSubmitting.value = true
  errorMessage.value = ''
  successMessage.value = ''

  try {
    const tags = textEntry.tagsInput
      .split(',')
      .map(tag => tag.trim())
      .filter(tag => tag.length > 0)

    await controller.addTextDocument(
      textEntry.content,
      textEntry.title,
      textEntry.category || 'General',
      tags
    )

    successMessage.value = 'Text entry added successfully!'

    // Reset form
    textEntry.title = ''
    textEntry.content = ''
    textEntry.category = ''
    textEntry.tagsInput = ''

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

  uploadProgress.show = true
  uploadProgress.title = 'Importing from URL'
  uploadProgress.percentage = 0
  uploadProgress.status = 'Fetching content...'

  try {
    const tags = urlEntry.tagsInput
      .split(',')
      .map(tag => tag.trim())
      .filter(tag => tag.length > 0)

    // Simulate progress
    const progressInterval = setInterval(() => {
      if (uploadProgress.percentage < 90) {
        uploadProgress.percentage += 10
      }
    }, 200)

    await controller.addUrlDocument(
      urlEntry.url,
      urlEntry.category || 'Web Content',
      tags
    )

    clearInterval(progressInterval)
    uploadProgress.percentage = 100
    uploadProgress.status = 'Import complete!'

    successMessage.value = 'URL content imported successfully!'

    // Reset form
    urlEntry.url = ''
    urlEntry.category = ''
    urlEntry.tagsInput = ''

    setTimeout(() => {
      uploadProgress.show = false
      successMessage.value = ''
    }, 3000)

  } catch (error: any) {
    errorMessage.value = error.message || 'Failed to import URL'
    uploadProgress.show = false
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

  uploadProgress.show = true
  uploadProgress.title = 'Uploading files'
  uploadProgress.percentage = 0
  uploadProgress.status = `Uploading 0 of ${selectedFiles.value.length} files...`

  try {
    const tags = fileEntry.tagsInput
      .split(',')
      .map(tag => tag.trim())
      .filter(tag => tag.length > 0)

    let uploaded = 0
    for (const file of selectedFiles.value) {
      uploadProgress.status = `Uploading ${file.name}...`

      await controller.addFileDocument(
        file,
        fileEntry.category || 'Uploads',
        tags
      )

      uploaded++
      uploadProgress.percentage = Math.round((uploaded / selectedFiles.value.length) * 100)
      uploadProgress.status = `Uploaded ${uploaded} of ${selectedFiles.value.length} files`
    }

    successMessage.value = `Successfully uploaded ${uploaded} file${uploaded > 1 ? 's' : ''}!`

    // Reset
    selectedFiles.value = []
    fileEntry.category = ''
    fileEntry.tagsInput = ''
    if (fileInput.value) {
      fileInput.value.value = ''
    }

    setTimeout(() => {
      uploadProgress.show = false
      successMessage.value = ''
    }, 3000)

  } catch (error: any) {
    errorMessage.value = error.message || 'Failed to upload files'
    uploadProgress.show = false
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

const getFileIcon = (type: string): string => {
  if (type.includes('pdf')) return 'fas fa-file-pdf'
  if (type.includes('word') || type.includes('doc')) return 'fas fa-file-word'
  if (type.includes('json')) return 'fas fa-file-code'
  if (type.includes('csv')) return 'fas fa-file-csv'
  if (type.includes('text') || type.includes('plain')) return 'fas fa-file-alt'
  return 'fas fa-file'
}

// Load categories on mount
onMounted(() => {
  controller.loadCategories()
})
</script>

<style scoped>
.knowledge-upload {
  padding: 1.5rem;
}

.upload-header {
  margin-bottom: 2rem;
}

.upload-header h3 {
  font-size: 1.25rem;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 0.5rem;
}

.upload-description {
  color: #6b7280;
}

.upload-methods {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
  gap: 1.5rem;
}

.upload-method {
  background: white;
  border: 2px solid #e5e7eb;
  border-radius: 0.5rem;
  overflow: hidden;
}

.method-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem 1.5rem;
  background: #f9fafb;
  border-bottom: 1px solid #e5e7eb;
}

.method-header i {
  font-size: 1.25rem;
  color: #3b82f6;
}

.method-header h4 {
  font-weight: 600;
  color: #1f2937;
}

.method-content {
  padding: 1.5rem;
}

.form-group {
  margin-bottom: 1.25rem;
}

.form-group label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 500;
  color: #374151;
  font-size: 0.875rem;
}

.form-input,
.form-textarea,
.form-select {
  width: 100%;
  padding: 0.625rem;
  border: 1px solid #d1d5db;
  border-radius: 0.375rem;
  font-size: 0.875rem;
  transition: all 0.2s;
}

.form-input:focus,
.form-textarea:focus,
.form-select:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.char-count {
  text-align: right;
  font-size: 0.75rem;
  color: #6b7280;
  margin-top: 0.25rem;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

.submit-btn {
  width: 100%;
  padding: 0.75rem;
  background: #3b82f6;
  color: white;
  border: none;
  border-radius: 0.375rem;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  transition: all 0.2s;
}

.submit-btn:hover:not(:disabled) {
  background: #2563eb;
}

.submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* File upload styles */
.file-drop-zone {
  border: 2px dashed #d1d5db;
  border-radius: 0.5rem;
  padding: 2rem;
  text-align: center;
  transition: all 0.2s;
  cursor: pointer;
}

.file-drop-zone.dragging {
  border-color: #3b82f6;
  background: #eff6ff;
}

.drop-icon {
  font-size: 3rem;
  color: #9ca3af;
  margin-bottom: 1rem;
}

.drop-text {
  color: #4b5563;
  margin-bottom: 0.5rem;
}

.browse-btn {
  color: #3b82f6;
  text-decoration: underline;
  background: none;
  border: none;
  cursor: pointer;
  font-weight: 500;
}

.browse-btn:hover {
  color: #2563eb;
}

.drop-hint {
  font-size: 0.875rem;
  color: #6b7280;
}

.selected-files {
  margin-top: 1rem;
}

.selected-files h5 {
  font-weight: 500;
  color: #374151;
  margin-bottom: 0.5rem;
}

.file-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem;
  background: #f9fafb;
  border-radius: 0.375rem;
  margin-bottom: 0.5rem;
}

.file-name {
  flex: 1;
  color: #374151;
  font-size: 0.875rem;
}

.file-size {
  color: #6b7280;
  font-size: 0.75rem;
}

.remove-file-btn {
  width: 1.5rem;
  height: 1.5rem;
  border: none;
  background: #ef4444;
  color: white;
  border-radius: 0.25rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.75rem;
}

.remove-file-btn:hover {
  background: #dc2626;
}

/* Progress styles */
.upload-progress {
  margin-top: 1.5rem;
  padding: 1rem;
  background: #f9fafb;
  border-radius: 0.5rem;
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.progress-header h4 {
  font-weight: 500;
  color: #374151;
}

.progress-percentage {
  font-weight: 600;
  color: #3b82f6;
}

.progress-bar {
  height: 0.5rem;
  background: #e5e7eb;
  border-radius: 0.25rem;
  overflow: hidden;
  margin-bottom: 0.5rem;
}

.progress-fill {
  height: 100%;
  background: #3b82f6;
  transition: width 0.3s ease;
}

.progress-status {
  font-size: 0.875rem;
  color: #6b7280;
}

/* Alert styles */
.alert {
  margin-top: 1rem;
  padding: 0.75rem 1rem;
  border-radius: 0.375rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.alert-success {
  background: #d1fae5;
  color: #065f46;
}

.alert-error {
  background: #fee2e2;
  color: #991b1b;
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
