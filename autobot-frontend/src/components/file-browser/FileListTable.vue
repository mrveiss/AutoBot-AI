<template>
  <div class="file-list-container">
    <table v-if="files.length > 0" class="file-table">
      <thead>
        <tr>
          <th @click="$emit('sort', 'name')" class="sortable">
            {{ $t('fileBrowser.fileList.name') }}
            <Icon :name="getSortIcon('name')" />
          </th>
          <th @click="$emit('sort', 'type')" class="sortable">
            {{ $t('fileBrowser.fileList.type') }}
            <Icon :name="getSortIcon('type')" />
          </th>
          <th @click="$emit('sort', 'size')" class="sortable">
            {{ $t('fileBrowser.fileList.size') }}
            <Icon :name="getSortIcon('size')" />
          </th>
          <th @click="$emit('sort', 'modified')" class="sortable">
            {{ $t('fileBrowser.fileList.modified') }}
            <Icon :name="getSortIcon('modified')" />
          </th>
          <th>{{ $t('fileBrowser.fileList.actions') }}</th>
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
            <Icon :name="getFileIcon(file)" />
            <span
              :class="{ clickable: file.is_dir }"
              class="file-name"
            >
              {{ file.name }}
            </span>
          </td>
          <td>{{ file.is_dir ? $t('fileBrowser.fileList.directory') : getFileType(file.name) }}</td>
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
                :aria-label="$t('fileBrowser.fileList.previewFile')"
                :title="$t('fileBrowser.fileList.preview')"
              >
                <Icon name="eye" />
              </BaseButton>
              <BaseButton
                v-if="file.is_dir"
                variant="ghost"
                size="sm"
                @click.stop="$emit('navigate', file.path)"
                class="action-btn open-btn"
                :aria-label="$t('fileBrowser.fileList.openDirectory')"
                :title="$t('fileBrowser.fileList.open')"
              >
                <Icon name="folder-open" />
              </BaseButton>
              <BaseButton
                variant="ghost"
                size="sm"
                @click.stop="$emit('rename-file', file)"
                class="action-btn rename-btn"
                :aria-label="$t('fileBrowser.fileList.renameItem')"
                :title="$t('fileBrowser.fileList.rename')"
              >
                <Icon name="edit" />
              </BaseButton>
              <BaseButton
                variant="ghost"
                size="sm"
                @click.stop="$emit('delete-file', file)"
                class="action-btn delete-btn"
                :aria-label="$t('fileBrowser.fileList.deleteItem')"
                :title="$t('fileBrowser.fileList.delete')"
              >
                <Icon name="trash" />
              </BaseButton>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
    <EmptyState
      v-else
      icon="folder-open"
      :message="$t('fileBrowser.fileList.noFiles')"
    />
  </div>
</template>

<script setup lang="ts">
import type { IconName } from '@/components/ui/Icon.vue'
import Icon from '@/components/ui/Icon.vue'
import { ref, nextTick } from 'vue'
import { formatDateTime } from '@/utils/formatHelpers'
import { getFileIconName } from '@/utils/iconMappings'
import EmptyState from '@/components/ui/EmptyState.vue'
import BaseButton from '@/components/base/BaseButton.vue'

// #9724: aligned with FileBrowserItem (useFileBrowser) — is_dir is optional
// in the backend payload.
interface FileItem {
  name: string
  path: string
  is_dir?: boolean
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
const getSortIcon = (field: string): IconName => {
  if (props.sortField !== field) return 'sort'
  return props.sortOrder === 'asc' ? 'sort-up' : 'sort-down'
}

// Icon mapping centralized in @/utils/iconMappings
// #9724: consumed by <Icon :name="..."> — must return an SVG IconName. The
// previous "<fa-class> <color-class>" strings rendered an empty SVG.
const getFileIcon = (file: FileItem): IconName => {
  return getFileIconName(file.name, file.is_dir)
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
@reference "../../assets/tailwind.css";
.file-list-container {
  @apply overflow-auto;
}

.file-table {
  @apply w-full border-collapse bg-autobot-bg-card shadow-sm rounded-lg overflow-hidden;
}

.file-table thead {
  @apply bg-autobot-bg-tertiary;
}

.file-table th {
  @apply px-4 py-3 text-left text-xs font-medium text-autobot-text-muted uppercase tracking-wider border-b border-autobot-border;
}

.file-table th.sortable {
  @apply cursor-pointer hover:bg-autobot-bg-secondary select-none;
}

.file-table td {
  @apply px-4 py-3 text-sm text-autobot-text-primary border-b border-autobot-border;
}

.file-table tbody tr:hover {
  @apply bg-autobot-bg-tertiary;
}

.file-table tbody tr:focus {
  @apply outline-hidden ring-2 ring-inset;
  background: var(--color-info-bg);
  --tw-ring-color: var(--color-primary);
}

.file-table tbody tr:focus-visible {
  @apply outline-hidden ring-2 ring-inset;
  background: var(--color-info-bg);
  --tw-ring-color: var(--color-primary);
}

.file-name-cell {
  @apply flex items-center gap-2;
}

.file-name {
  @apply truncate;
}

.file-name.clickable {
  @apply cursor-pointer hover:underline;
  color: var(--text-link);
}

.file-name.clickable:hover {
  color: var(--text-link-hover);
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
