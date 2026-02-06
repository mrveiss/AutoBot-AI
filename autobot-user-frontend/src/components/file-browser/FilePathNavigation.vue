<template>
  <div class="path-navigation">
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
      <button @click="$emit('navigate-to-path', pathInput)" class="path-go-btn">
        <i class="fas fa-arrow-right"></i>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'

interface Props {
  currentPath: string
}

interface Emits {
  (e: 'navigate-to-path', path: string): void
}

const props = defineProps<Props>()
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
.path-navigation {
  @apply bg-gray-50 border rounded-lg p-4 mb-4 flex flex-wrap items-center gap-4;
}

.breadcrumb {
  @apply flex items-center flex-wrap gap-1 flex-1 min-w-0;
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
  @apply flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500;
}

.path-go-btn {
  @apply px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500;
}
</style>
