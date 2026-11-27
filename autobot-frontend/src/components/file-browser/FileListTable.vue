<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  The Files tab file table on the kit `BaseTable` (#22349). The name cell is a real button, so a row is reachable by Tab
  and the arrow keys; a click anywhere on a row (or Enter on its name) opens the folder or previews the file, as before.
-->
<template>
  <div class="file-list-container" @click="onTableClick" @keydown="onTableKeydown">
    <BaseTable
      :columns="columns"
      :rows="rows"
      row-key="path"
      :aria-label="$t('fileBrowser.fileList.tableLabel')"
      :sort-key="sortField"
      :sort-order="sortOrder"
      :actions-label="$t('fileBrowser.fileList.actions')"
      :empty-title="$t('fileBrowser.fileList.noFiles')"
      @sort="(key: string) => emit('sort', key)"
    >
      <template #cell-name="{ row }">
        <BaseButton variant="link" size="sm" class="file-name-cell" data-row-primary :data-testid="`file-row-${row.name}`">
          <Icon :name="getFileIcon(row as unknown as FileItem)" />
          <span class="file-name" :class="{ clickable: row.is_dir }">{{ row.name }}</span>
        </BaseButton>
      </template>
      <template #cell-type="{ row }">{{ row.is_dir ? $t('fileBrowser.fileList.directory') : getFileType(String(row.name)) }}</template>
      <template #cell-size="{ row }">{{ row.is_dir ? '-' : formatFileSize(row.size as number | undefined, sizeOptions) }}</template>
      <template #cell-modified="{ row }">{{ formatDateTime(row.last_modified as string | undefined) }}</template>
      <template #actions="{ row }">
        <div class="action-buttons">
          <BaseButton
            v-if="!row.is_dir"
            variant="ghost"
            size="sm"
            :aria-label="$t('fileBrowser.fileList.previewFile')"
            data-testid="row-preview"
            @click.stop="emit('view-file', row as unknown as FileItem)"
          >
            <Icon name="eye" />
          </BaseButton>
          <BaseButton
            v-else
            variant="ghost"
            size="sm"
            :aria-label="$t('fileBrowser.fileList.openDirectory')"
            data-testid="row-open"
            @click.stop="emit('navigate', String(row.path))"
          >
            <Icon name="folder-open" />
          </BaseButton>
          <BaseButton
            variant="ghost"
            size="sm"
            :aria-label="$t('fileBrowser.fileList.renameItem')"
            data-testid="row-rename"
            @click.stop="emit('rename-file', row as unknown as FileItem)"
          >
            <Icon name="edit" />
          </BaseButton>
          <BaseButton
            variant="ghost"
            size="sm"
            :aria-label="$t('fileBrowser.fileList.deleteItem')"
            data-testid="row-delete"
            @click.stop="emit('delete-file', row as unknown as FileItem)"
          >
            <Icon name="trash" />
          </BaseButton>
        </div>
      </template>
    </BaseTable>
  </div>
</template>

<script setup lang="ts">
import type { IconName } from '@/components/ui/Icon.vue'
import Icon from '@/components/ui/Icon.vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseButton, BaseTable } from '@autobot/ui'
import type { BaseTableColumn } from '@autobot/ui'
import { formatDateTime, formatFileSize, fileBrowserSizeOptions } from '@/utils/formatHelpers'
import { getFileIconName } from '@/utils/iconMappings'
import { getFileType } from '@/utils/fileTypeLabel'

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

const { t } = useI18n()
const sizeOptions = computed(() => fileBrowserSizeOptions(t('fileBrowser.zeroSize')))
const rows = computed(() => props.files as unknown as Record<string, unknown>[])
const columns = computed<BaseTableColumn[]>(() => [
  { key: 'name', label: t('fileBrowser.fileList.name'), sortable: true },
  { key: 'type', label: t('fileBrowser.fileList.type'), sortable: true },
  { key: 'size', label: t('fileBrowser.fileList.size'), sortable: true, numeric: true },
  { key: 'modified', label: t('fileBrowser.fileList.modified'), sortable: true },
])

// #9724: consumed by <Icon :name="..."> — must return an SVG IconName.
const getFileIcon = (file: FileItem): IconName => getFileIconName(file.name, file.is_dir)

/** The file behind a click: the Nth body row of the table is the Nth file (the table is neither paged nor filtered). */
function fileOfRow(target: EventTarget | null): FileItem | null {
  const row = (target as HTMLElement | null)?.closest?.('tbody tr[data-slot="table-row"]')
  if (!row) return null
  const index = Array.from(row.parentElement?.children ?? []).indexOf(row)
  return props.files[index] ?? null
}

function onTableClick(event: MouseEvent): void {
  const file = fileOfRow(event.target)
  if (!file) return
  if (file.is_dir) emit('navigate', file.path)
  else emit('view-file', file)
}

/** Arrow keys, Home and End move between the name buttons; Enter and Space are the button's own click. */
function onTableKeydown(event: KeyboardEvent): void {
  const keys = ['ArrowDown', 'ArrowUp', 'Home', 'End']
  if (!keys.includes(event.key)) return
  const buttons = Array.from((event.currentTarget as HTMLElement).querySelectorAll<HTMLElement>('[data-row-primary]'))
  const at = buttons.indexOf(event.target as HTMLElement)
  if (at < 0) return
  event.preventDefault()
  const next = { ArrowDown: at + 1, ArrowUp: at - 1, Home: 0, End: buttons.length - 1 }[event.key as 'ArrowDown']
  buttons[Math.min(Math.max(next, 0), buttons.length - 1)]?.focus()
}
</script>

<style scoped>
.file-list-container {
  overflow: auto;
}
.file-name-cell {
  max-width: 100%;
  gap: var(--aui-space-2);
}
.file-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.file-name.clickable {
  color: var(--aui-color-primary);
}
.file-name.clickable:hover {
  text-decoration: underline;
}
.action-buttons {
  display: flex;
  justify-content: flex-end;
  gap: var(--aui-space-1);
}
</style>
