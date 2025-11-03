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
        <tr v-for="(file, index) in files" :key="file.name || file.id || `file-${index}`">
          <td class="file-name-cell">
            <i :class="getFileIcon(file)" class="file-icon"></i>
            <span
              @click="file.is_dir ? $emit('navigate', file.path) : null"
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
              <button
                v-if="!file.is_dir"
                @click="$emit('view-file', file)"
                class="action-btn view-btn"
                aria-label="View file"
                title="View file"
              >
                <i class="fas fa-eye"></i>
              </button>
              <button
                v-if="file.is_dir"
                @click="$emit('navigate', file.path)"
                class="action-btn open-btn"
                aria-label="Open directory"
                title="Open directory"
              >
                <i class="fas fa-folder-open"></i>
              </button>
              <button
                @click="$emit('rename-file', file)"
                class="action-btn rename-btn"
                aria-label="Rename"
                title="Rename"
              >
                <i class="fas fa-edit"></i>
              </button>
              <button
                @click="$emit('delete-file', file)"
                class="action-btn delete-btn"
                aria-label="Delete"
                title="Delete"
              >
                <i class="fas fa-trash"></i>
              </button>
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
import { computed } from 'vue'
import { formatDateTime } from '@/utils/formatHelpers'
import EmptyState from '@/components/ui/EmptyState.vue'

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
defineEmits<Emits>()

// Methods
const getSortIcon = (field: string): string => {
  if (props.sortField !== field) return 'fas fa-sort text-gray-400'
  return props.sortOrder === 'asc' ? 'fas fa-sort-up' : 'fas fa-sort-down'
}

const getFileIcon = (file: FileItem): string => {
  if (file.is_dir) return 'fas fa-folder text-blue-500'

  const extension = file.name.split('.').pop()?.toLowerCase()

  switch (extension) {
    case 'txt':
    case 'md':
    case 'readme':
      return 'fas fa-file-alt text-gray-500'
    case 'js':
    case 'ts':
    case 'html':
    case 'css':
    case 'vue':
    case 'json':
      return 'fas fa-file-code text-green-500'
    case 'jpg':
    case 'jpeg':
    case 'png':
    case 'gif':
    case 'svg':
    case 'webp':
      return 'fas fa-file-image text-purple-500'
    case 'pdf':
      return 'fas fa-file-pdf text-red-500'
    case 'zip':
    case 'tar':
    case 'gz':
    case 'rar':
      return 'fas fa-file-archive text-orange-500'
    case 'mp4':
    case 'avi':
    case 'mov':
    case 'webm':
      return 'fas fa-file-video text-pink-500'
    case 'mp3':
    case 'wav':
    case 'ogg':
      return 'fas fa-file-audio text-indigo-500'
    default:
      return 'fas fa-file text-gray-400'
  }
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

.action-btn {
  @apply w-8 h-8 flex items-center justify-center rounded text-gray-500 hover:text-gray-700 hover:bg-gray-100;
}

.view-btn:hover {
  @apply text-blue-600;
}

.open-btn:hover {
  @apply text-green-600;
}

.rename-btn:hover {
  @apply text-yellow-600;
}

.delete-btn:hover {
  @apply text-red-600;
}
</style>