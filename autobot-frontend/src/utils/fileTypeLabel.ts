// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// The one file-type label of the Files tab (#22349): the table's Type column and the sort-by-type key both read it,
// so the label and the order can never disagree. Moved from the two copies in FileBrowser.vue and FileListTable.vue.
// The labels are `fileBrowser.fileType.*` i18n keys, listed in full so a key scan finds each one.

/** The translate function the label is read through (`useI18n().t` in a component or composable). */
export type Translate = (key: string, params?: Record<string, unknown>) => string

const TYPE_LABEL_KEYS: Record<string, string> = {
  txt: 'fileBrowser.fileType.txt',
  md: 'fileBrowser.fileType.md',
  js: 'fileBrowser.fileType.js',
  ts: 'fileBrowser.fileType.ts',
  html: 'fileBrowser.fileType.html',
  css: 'fileBrowser.fileType.css',
  vue: 'fileBrowser.fileType.vue',
  json: 'fileBrowser.fileType.json',
  jpg: 'fileBrowser.fileType.jpg',
  jpeg: 'fileBrowser.fileType.jpeg',
  png: 'fileBrowser.fileType.png',
  gif: 'fileBrowser.fileType.gif',
  svg: 'fileBrowser.fileType.svg',
  pdf: 'fileBrowser.fileType.pdf',
  zip: 'fileBrowser.fileType.zip',
  tar: 'fileBrowser.fileType.tar',
  gz: 'fileBrowser.fileType.gz',
}

/** A readable type for a file name: a known label, else the upper-cased extension, else "Unknown". */
export function getFileType(filename: string, t: Translate): string {
  const extension = filename.split('.').pop()?.toLowerCase()
  if (!extension) return t('fileBrowser.fileType.unknown')
  const key = Object.hasOwn(TYPE_LABEL_KEYS, extension) ? TYPE_LABEL_KEYS[extension] : null
  return key ? t(key) : t('fileBrowser.fileType.extension', { ext: extension.toUpperCase() })
}
