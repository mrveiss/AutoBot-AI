// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * The three export formats of the Manage bulk toolbar (#747): JSON, Markdown and CSV of the
 * selected documents. Pure text builders; the download itself is the kit's `saveTextFile`.
 */
import { saveTextFile } from '@autobot/ui'
import type { KnowledgeDocument } from '@/stores/useKnowledgeStore'
import { formatDate, formatDateTime, isoDateStamp } from '@/utils/formatHelpers'

export type ExportFormat = 'json' | 'csv' | 'markdown'

const CSV_CONTENT_PREVIEW = 500

export function escapeCsvField(field: string): string {
  return /[,"\n]/.test(field) ? `"${field.replace(/"/g, '""')}"` : field
}

function markdownEntry(entry: KnowledgeDocument, index: number): string[] {
  const lines = [`## ${index + 1}. ${entry.title || 'Untitled'}`, '']
  lines.push(`**Category:** ${entry.category}`, `**Type:** ${entry.type}`, `**Source:** ${entry.source}`)
  if (entry.tags.length > 0) lines.push(`**Tags:** ${entry.tags.join(', ')}`)
  lines.push(`**Created:** ${formatDateTime(entry.createdAt)}`, `**Updated:** ${formatDateTime(entry.updatedAt)}`)
  lines.push('', '### Content', '', entry.content, '', '---', '')
  return lines
}

export function generateMarkdownExport(entries: KnowledgeDocument[]): string {
  const head = ['# Knowledge Base Export', '', `> Exported on ${formatDate(new Date())}`, `> ${entries.length} entries`, '']
  return [...head, ...entries.flatMap(markdownEntry)].join('\n')
}

export function generateCsvExport(entries: KnowledgeDocument[]): string {
  const headers = ['Title', 'Category', 'Type', 'Source', 'Tags', 'Created', 'Updated', 'Content']
  const rows = entries.map((entry) =>
    [
      entry.title || 'Untitled',
      entry.category,
      entry.type,
      entry.source,
      entry.tags.join('; '),
      formatDateTime(entry.createdAt),
      formatDateTime(entry.updatedAt),
      entry.content.substring(0, CSV_CONTENT_PREVIEW) + (entry.content.length > CSV_CONTENT_PREVIEW ? '...' : ''),
    ]
      .map(escapeCsvField)
      .join(','),
  )
  return [headers.join(','), ...rows].join('\n')
}

function generateJsonExport(entries: KnowledgeDocument[]): string {
  return JSON.stringify(
    entries.map((e) => ({
      title: e.title, content: e.content, category: e.category, type: e.type, source: e.source,
      tags: e.tags, createdAt: e.createdAt, updatedAt: e.updatedAt,
    })),
    null,
    2,
  )
}

const FORMATS: Record<ExportFormat, { build: (e: KnowledgeDocument[]) => string; mime: string; ext: string }> = {
  markdown: { build: generateMarkdownExport, mime: 'text/markdown', ext: 'md' },
  csv: { build: generateCsvExport, mime: 'text/csv', ext: 'csv' },
  json: { build: generateJsonExport, mime: 'application/json', ext: 'json' },
}

export function exportEntries(entries: KnowledgeDocument[], format: ExportFormat): void {
  const { build, mime, ext } = FORMATS[format] ?? FORMATS.json
  saveTextFile(build(entries), `knowledge-export-${isoDateStamp()}.${ext}`, mime)
}
