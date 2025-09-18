<template>
  <div class="file-upload-section">
    <label for="visible-file-input" class="file-input-label">
      <i class="fas fa-cloud-upload-alt"></i>
      Drag & drop files here or click to select:
    </label>

    <!-- Visible file input -->
    <input
      id="visible-file-input"
      ref="visibleFileInput"
      type="file"
      @change="handleFileSelected"
      class="visible-file-input"
      data-testid="visible-file-upload-input"
      aria-label="Visible file upload input"
      multiple
    />

    <!-- Hidden file input for programmatic access -->
    <input
      ref="hiddenFileInput"
      type="file"
      style="display: none"
      @change="handleFileSelected"
      data-testid="file-upload-input"
      aria-label="File upload input"
      multiple
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

interface Emits {
  (e: 'files-selected', files: FileList): void
}

const emit = defineEmits<Emits>()

// Template refs
const visibleFileInput = ref<HTMLInputElement>()
const hiddenFileInput = ref<HTMLInputElement>()

// Methods
const handleFileSelected = (event: Event) => {
  const target = event.target as HTMLInputElement
  if (target.files && target.files.length > 0) {
    emit('files-selected', target.files)
  }
}

const triggerFileSelect = () => {
  hiddenFileInput.value?.click()
}

// Expose methods for parent component
defineExpose({
  triggerFileSelect
})
</script>

<style scoped>
.file-upload-section {
  @apply mb-6 p-4 border-2 border-dashed border-gray-300 rounded-lg bg-gray-50 hover:border-gray-400 transition-colors;
}

.file-input-label {
  @apply flex items-center justify-center gap-2 text-gray-600 font-medium cursor-pointer;
}

.file-input-label:hover {
  @apply text-gray-800;
}

.visible-file-input {
  @apply mt-3 block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-medium file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100;
}

/* Drag and drop styling */
.file-upload-section.drag-over {
  @apply border-blue-400 bg-blue-50;
}
</style>