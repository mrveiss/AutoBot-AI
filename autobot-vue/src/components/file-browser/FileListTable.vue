<template>
  <div class="file-list-container">
    <table v-if="files.length > 0" class="file-table">
      <thead>
        <tr>
          <th @click="$emit('sort', 'name')" class="sortable">
            Name
            <i :class="getSortIcon('name')" class="sort-icon"></i>
          </th>
          <th @click="$emit('sort', 'type')" class="sortable">
            Type
            <i :class="getSortIcon('type')" class="sort-icon"></i>
          </th>
          <th @click="$emit('sort', 'size')" class="sortable">
            Size
            <i :class="getSortIcon('size')" class="sort-icon"></i>
          </th>
          <th @click="$emit('sort', 'modified')" class="sortable">
            Modified
            <i :class="getSortIcon('modified')" class="sort-icon"></i>
          </th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(file, index) in files"
          :key="file.name || file.id || `file-${index}`"
          :ref="el => setRowRef(el as HTMLElement | null, index)"
          :tabindex="index === focusedIndex ? 0 : -1"
          :aria-selected="index === focusedIndex"
          role="button"
          @click="handleRowClick(file, index)"
          @keydown="handleRowKeydown($event, file, index)"
          @focus="focusedIndex = index"
          class="file-row"
        >
          <td class="file-name-cell">
            <i :class="getFileIcon(file)" class="file-icon" aria-hidden="true"></i>
            <span
              :class="{ clickable: file.is_dir }"
              class="file-name"
            >
              {{ file.name }}
            </span>
          </td>
          <td>{{ file.is_dir ? 'Directory' : getFileType(file.name) }}</td>
          <td>{{ file.is_dir ? '-' : formatSize(file.size) }}</td>
          <td>{{ formatDate(file.last_modified) }}</td>
          <td>
            <div class="action-buttons">
              <BaseButton
                v-if="!file.is_dir"
                variant="ghost"
                size="sm"
                @click.stop="$emit('view-file', file)"
                class="action-btn view-btn"
                aria-label="View file"
                title="View file"
              >
                <i class="fas fa-eye" aria-hidden="true"></i>
              </BaseButton>
              <BaseButton
                v-if="file.is_dir"
                variant="ghost"
                size="sm"
                @click.stop="$emit('navigate', file.path)"
                class="action-btn open-btn"
                aria-label="Open directory"
                title="Open directory"
              >
                <i class="fas fa-folder-open" aria-hidden="true"></i>
              </BaseButton>
              <BaseButton
                variant="ghost"
                size="sm"
                @click.stop="$emit('rename-file', file)"
                class="action-btn rename-btn"
                aria-label="Rename"
                title="Rename"
              >
                <i class="fas fa-edit" aria-hidden="true"></i>
              </BaseButton>
              <BaseButton
                variant="ghost"
                size="sm"
                @click.stop="$emit('delete-file', file)"
                class="action-btn delete-btn"
                aria-label="Delete"
                title="Delete"
              >
                <i class="fas fa-trash" aria-hidden="true"></i>
              </BaseButton>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
    <EmptyState
      v-else
      icon="fas fa-folder-open"
      :message="`No files or directories found${currentPath ? ' in ' + currentPath : ''}`"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { formatDateTime } from '@/utils/formatHelpers'
import { getFileIcon as getFileIconUtil } from '@/utils/iconMappings'
import EmptyState from '@/components/ui/EmptyState.vue'
import BaseButton from '@/components/base/BaseButton.vue'

interface FileItem {
  name: string
  path: string
  is_dir: boolean
  size?: number
  last_modified?: string
  id?: string
}

interface Props {
  files: FileItem[]
  sortField: string
  sortOrder: 'asc' | 'desc'
  currentPath?: string
}

interface Emits {
  (e: 'sort', field: string): void
  (e: 'navigate', path: string): void
  (e: 'view-file', file: FileItem): void
  (e: 'rename-file', file: FileItem): void
  (e: 'delete-file', file: FileItem): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// Keyboard navigation state
const focusedIndex = ref(0)
const rowRefs = ref<(HTMLElement | null)[]>([])

// Set row reference for keyboard navigation
const setRowRef = (el: HTMLElement | null, index: number) => {
  if (el) {
    rowRefs.value[index] = el
  }
}

// Handle row click (mouse or keyboard activation)
const handleRowClick = (file: FileItem, index: number) => {
  focusedIndex.value = index

  if (file.is_dir) {
    emit('navigate', file.path)
  } else {
    emit('view-file', file)
  }
}

// Handle keyboard navigation
const handleRowKeydown = (event: KeyboardEvent, file: FileItem, index: number) => {
  switch (event.key) {
    case 'ArrowDown':
      event.preventDefault()
      if (index < props.files.length - 1) {
        focusedIndex.value = index + 1
        nextTick(() => {
          rowRefs.value[index + 1]?.focus()
        })
      }
      break

    case 'ArrowUp':
      event.preventDefault()
      if (index > 0) {
        focusedIndex.value = index - 1
        nextTick(() => {
          rowRefs.value[index - 1]?.focus()
        })
      }
      break

    case 'Home':
      event.preventDefault()
      focusedIndex.value = 0
      nextTick(() => {
        rowRefs.value[0]?.focus()
      })
      break

    case 'End':
      event.preventDefault()
      focusedIndex.value = props.files.length - 1
      nextTick(() => {
        rowRefs.value[props.files.length - 1]?.focus()
      })
      break

    case 'Enter':
    case ' ':
      event.preventDefault()
      handleRowClick(file, index)
      break
  }
}

// Methods
const getSortIcon = (field: string): string => {
  if (props.sortField !== field) return 'fas fa-sort text-gray-400'
  return props.sortOrder === 'asc' ? 'fas fa-sort-up' : 'fas fa-sort-down'
}

// Icon mapping centralized in @/utils/iconMappings
// Color classes added for visual distinction
const getFileIcon = (file: FileItem): string => {
  const icon = getFileIconUtil(file.name, file.is_dir)

  // Add color classes based on file type
  if (file.is_dir) return `${icon} text-blue-500`

  const extension = file.name.split('.').pop()?.toLowerCase()

  // Map extensions to color classes for visual distinction
  const colorMap: Record<string, string> = {
    // Text files
    'txt': 'text-gray-500',
    'md': 'text-gray-500',
    'readme': 'text-gray-500',
    // Code files
    'js': 'text-green-500',
    'ts': 'text-green-500',
    'jsx': 'text-green-500',
    'tsx': 'text-green-500',
    'html': 'text-green-500',
    'css': 'text-green-500',
    'vue': 'text-green-500',
    'json': 'text-green-500',
    'py': 'text-green-500',
    // Images
    'jpg': 'text-purple-500',
    'jpeg': 'text-purple-500',
    'png': 'text-purple-500',
    'gif': 'text-purple-500',
    'svg': 'text-purple-500',
    'webp': 'text-purple-500',
    // Documents
    'pdf': 'text-red-500',
    // Archives
    'zip': 'text-orange-500',
    'tar': 'text-orange-500',
    'gz': 'text-orange-500',
    'rar': 'text-orange-500',
    // Media
    'mp4': 'text-pink-500',
    'avi': 'text-pink-500',
    'mov': 'text-pink-500',
    'webm': 'text-pink-500',
    'mp3': 'text-indigo-500',
    'wav': 'text-indigo-500',
    'ogg': 'text-indigo-500'
  }

  const color = colorMap[extension || ''] || 'text-gray-400'
  return `${icon} ${color}`
}

const getFileType = (filename: string): string => {
  const extension = filename.split('.').pop()?.toLowerCase()
  if (!extension) return 'Unknown'

  const typeMap: Record<string, string> = {
    txt: 'Text',
    md: 'Markdown',
    js: 'JavaScript',
    ts: 'TypeScript',
    html: 'HTML',
    css: 'CSS',
    vue: 'Vue Component',
    json: 'JSON',
    jpg: 'JPEG Image',
    jpeg: 'JPEG Image',
    png: 'PNG Image',
    gif: 'GIF Image',
    svg: 'SVG Image',
    pdf: 'PDF Document',
    zip: 'ZIP Archive',
    tar: 'TAR Archive',
    gz: 'GZ Archive'
  }

  return typeMap[extension] || extension.toUpperCase() + ' File'
}

const formatSize = (bytes: number = 0): string => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

// NOTE: formatDate removed - now using formatDateTime from @/utils/formatHelpers
const formatDate = formatDateTime
</script>

<style scoped>
.file-list-container {
  @apply overflow-auto;
}

.file-table {
  @apply w-full border-collapse bg-white shadow-sm rounded-lg overflow-hidden;
}

.file-table thead {
  @apply bg-gray-50;
}

.file-table th {
  @apply px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider border-b border-gray-200;
}

.file-table th.sortable {
  @apply cursor-pointer hover:bg-gray-100 select-none;
}

.file-table td {
  @apply px-4 py-3 text-sm text-gray-900 border-b border-gray-100;
}

.file-table tbody tr:hover {
  @apply bg-gray-50;
}

.file-table tbody tr:focus {
  @apply outline-none bg-blue-50 ring-2 ring-blue-500 ring-inset;
}

.file-table tbody tr:focus-visible {
  @apply outline-none bg-blue-50 ring-2 ring-blue-500 ring-inset;
}

.file-name-cell {
  @apply flex items-center gap-2;
}

.file-name {
  @apply truncate;
}

.file-name.clickable {
  @apply cursor-pointer text-blue-600 hover:text-blue-800 hover:underline;
}

.file-icon {
  @apply flex-shrink-0;
}

.sort-icon {
  @apply ml-1;
}

.action-buttons {
  @apply flex gap-1;
}

/* Button styling handled by BaseButton component */
</style>