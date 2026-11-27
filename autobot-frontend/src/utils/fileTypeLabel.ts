// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// The one file-type label of the Files tab (#22349): the table's Type column and the sort-by-type key both read it,
// so the label and the order can never disagree. Moved from the two copies in FileBrowser.vue and FileListTable.vue.

const TYPE_LABELS: Record<string, string> = {
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
  gz: 'GZ Archive',
}

/** A readable type for a file name: a known label, else the upper-cased extension, else "Unknown". */
export function getFileType(filename: string): string {
  const extension = filename.split('.').pop()?.toLowerCase()
  if (!extension) return 'Unknown'
  return TYPE_LABELS[extension] || extension.toUpperCase() + ' File'
}
