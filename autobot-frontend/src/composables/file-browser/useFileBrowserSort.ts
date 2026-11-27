// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #22349: the Files tab's sort state, split out of useFileBrowserActions.
import { computed, ref, type Ref } from 'vue'
import type { FileBrowserItem } from '@/composables/file-browser/useFileBrowser'
import { useI18n } from 'vue-i18n'
import type { SortOrder } from '@autobot/ui'
import { getFileType, type Translate } from '@/utils/fileTypeLabel'

function sortValue(file: FileBrowserItem, field: string, t: Translate): string | number {
  if (field === 'size') return file.size || 0
  if (field === 'modified') return new Date(file.last_modified || 0).getTime()
  if (field === 'type') return file.is_dir ? 'Directory' : getFileType(file.name, t)
  return file.name
}

/** Directories first, then the chosen field in the chosen order. */
export function sortFileItems(files: FileBrowserItem[], field: string, order: SortOrder, t: Translate): FileBrowserItem[] {
  const sign = order === 'asc' ? 1 : -1
  return [...files].sort((a, b) => {
    if (a.is_dir && !b.is_dir) return -1
    if (!a.is_dir && b.is_dir) return 1
    const av = sortValue(a, field, t)
    const bv = sortValue(b, field, t)
    return av < bv ? -sign : av > bv ? sign : 0
  })
}

export function useFileBrowserSort(files: Ref<FileBrowserItem[]>) {
  const { t } = useI18n()
  const sortField = ref('name')
  const sortOrder = ref<SortOrder>('asc')
  const sortedFiles = computed(() => sortFileItems(files.value, sortField.value, sortOrder.value, t))

  const sortBy = (field: string) => {
    if (sortField.value === field) {
      sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
    } else {
      sortField.value = field
      sortOrder.value = 'asc'
    }
  }

  return { sortField, sortOrder, sortedFiles, sortBy }
}
