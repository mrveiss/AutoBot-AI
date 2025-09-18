<template>
  <div class="file-browser-header">
    <h2>{{ title }}</h2>
    <div class="file-actions">
      <button @click="$emit('refresh')" aria-label="Refresh files">
        <i class="fas fa-sync-alt"></i> Refresh
      </button>
      <button @click="$emit('upload')" aria-label="Upload file">
        <i class="fas fa-upload"></i> Upload File
      </button>
      <button @click="$emit('toggle-view')" aria-label="Toggle view mode">
        <i :class="viewMode === 'tree' ? 'fas fa-list' : 'fas fa-tree'"></i>
        {{ viewMode === 'tree' ? 'List View' : 'Tree View' }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Props {
  title?: string
  viewMode: 'tree' | 'list'
}

interface Emits {
  (e: 'refresh'): void
  (e: 'upload'): void
  (e: 'toggle-view'): void
}

withDefaults(defineProps<Props>(), {
  title: 'File Browser'
})

defineEmits<Emits>()
</script>

<style scoped>
.file-browser-header {
  @apply flex justify-between items-center mb-6 pb-4 border-b border-gray-200;
}

.file-browser-header h2 {
  @apply text-2xl font-bold text-gray-900;
}

.file-actions {
  @apply flex gap-2;
}

.file-actions button {
  @apply px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 flex items-center gap-2;
}

.file-actions button:hover {
  @apply shadow-sm;
}

.file-actions button i {
  @apply text-sm;
}
</style>