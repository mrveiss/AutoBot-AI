<template>
  <div class="file-browser-header">
    <h2>{{ title }}</h2>

    <!-- Path Navigation (Inline) -->
    <div class="path-navigation-inline">
      <!-- Breadcrumb Navigation -->
      <div class="breadcrumb">
        <span @click="$emit('navigate-to-path', '/')" class="breadcrumb-item">
          <i class="fas fa-home"></i> Home
        </span>
        <span v-for="(part, index) in pathParts" :key="index" class="breadcrumb-item">
          <i class="fas fa-chevron-right breadcrumb-separator"></i>
          <span @click="$emit('navigate-to-path', getPathUpTo(index))" class="clickable">
            {{ part }}
          </span>
        </span>
      </div>

      <!-- Path Input -->
      <div class="path-input">
        <input
          v-model="pathInput"
          @keyup.enter="$emit('navigate-to-path', pathInput)"
          placeholder="/path/to/directory"
          class="path-field"
        />
        <BaseButton
          variant="primary"
          size="sm"
          @click="$emit('navigate-to-path', pathInput)"
          class="path-go-btn"
          aria-label="Navigate to path"
        >
          <i class="fas fa-arrow-right"></i>
        </BaseButton>
      </div>
    </div>

    <div class="file-actions">
      <BaseButton
        variant="outline"
        size="sm"
        @click="$emit('new-folder')"
        aria-label="Create new folder"
      >
        <i class="fas fa-folder-plus"></i> New Folder
      </BaseButton>
      <BaseButton
        variant="outline"
        size="sm"
        @click="$emit('upload')"
        aria-label="Upload file"
      >
        <i class="fas fa-upload"></i> Upload File
      </BaseButton>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import BaseButton from '@/components/base/BaseButton.vue'

interface Props {
  title?: string
  viewMode: 'tree' | 'list'
  currentPath: string
}

interface Emits {
  (e: 'upload'): void
  (e: 'new-folder'): void
  (e: 'navigate-to-path', path: string): void
}

const props = withDefaults(defineProps<Props>(), {
  title: 'File Browser',
  currentPath: '/'
})

const emit = defineEmits<Emits>()

// Local state for path input
const pathInput = ref(props.currentPath)

// Watch for external path changes
watch(() => props.currentPath, (newPath) => {
  pathInput.value = newPath
})

// Computed properties
const pathParts = computed(() => {
  return props.currentPath.split('/').filter(part => part)
})

// Methods
const getPathUpTo = (index: number): string => {
  const parts = pathParts.value.slice(0, index + 1)
  return '/' + parts.join('/')
}
</script>

<style scoped>
.file-browser-header {
  @apply flex flex-wrap items-center gap-4 mb-6 pb-4 border-b border-gray-200;
}

.file-browser-header h2 {
  @apply text-2xl font-bold text-gray-900 flex-shrink-0;
}

.path-navigation-inline {
  @apply flex items-center gap-3 flex-1 min-w-0;
  flex-basis: 66%;
}

.breadcrumb {
  @apply flex items-center flex-wrap gap-1 flex-shrink min-w-0;
}

.breadcrumb-item {
  @apply flex items-center text-sm;
}

.breadcrumb-item .clickable {
  @apply cursor-pointer text-blue-600 hover:text-blue-800 hover:underline;
}

.breadcrumb-separator {
  @apply text-gray-400 mx-1;
}

.path-input {
  @apply flex gap-2 flex-shrink-0;
}

.path-field {
  @apply px-3 py-1.5 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 min-w-[200px];
}

.file-actions {
  @apply flex gap-2 flex-shrink-0 ml-auto;
}

/* Button styling handled by BaseButton component */
</style>