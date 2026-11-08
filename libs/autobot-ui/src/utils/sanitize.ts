// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * HTML sanitization utilities using DOMPurify.
 * All user-generated or LLM-generated content rendered via v-html
 * MUST be sanitized through these functions to prevent XSS (#2847).
 */

import DOMPurify from 'dompurify'
import type { Config as DOMPurifyConfig } from 'dompurify'

/** Named allow-lists. Call sites choose a preset; they never supply a config. */
export type SanitizePreset = 'chat' | 'knowledge' | 'code' | 'plain'

const FORMAT_TAGS = ['br', 'strong', 'b', 'em', 'i', 'code', 'pre', 'span', 'p', 'ul', 'ol', 'li']

const PRESETS: Readonly<Record<SanitizePreset, DOMPurifyConfig>> = Object.freeze({
  // Chat/message content: formatting plus links.
  chat: {
    ALLOWED_TAGS: [...FORMAT_TAGS, 'a', 'div'],
    ALLOWED_ATTR: ['href', 'target', 'rel', 'class'],
  },
  // Knowledge/document content: formatting only, no links.
  knowledge: { ALLOWED_TAGS: FORMAT_TAGS, ALLOWED_ATTR: ['class'] },
  // Syntax-highlighter output: spans carrying token classes.
  code: { ALLOWED_TAGS: ['span', 'br'], ALLOWED_ATTR: ['class'] },
  // Text only: every tag and attribute removed.
  plain: { ALLOWED_TAGS: [], ALLOWED_ATTR: [] },
})

let hooksRegistered = false

/**
 * Registered once for the process: any link that opens a new browsing context
 * gets rel="noopener noreferrer" so the target page cannot reach window.opener.
 */
function registerHooks(): void {
  if (hooksRegistered) return
  hooksRegistered = true
  DOMPurify.addHook('afterSanitizeAttributes', (node: Node) => {
    if (node instanceof HTMLAnchorElement && node.hasAttribute('target')) {
      node.setAttribute('rel', 'noopener noreferrer')
    }
  })
}

/**
 * Sanitize HTML with a named preset (default: chat). Safe for v-html.
 *
 * @param html - Raw HTML string to sanitize
 * @param preset - Named allow-list; there is deliberately no way to pass a config
 */
export function sanitizeHtml(html: string, preset: SanitizePreset = 'chat'): string {
  registerHooks()
  return DOMPurify.sanitize(html, PRESETS[preset]) as string
}

/** Sanitize chat message HTML (formatting + links). */
export function sanitizeChatHtml(html: string): string {
  return sanitizeHtml(html, 'chat')
}

/** Sanitize knowledge entry HTML (formatting only, no links). */
export function sanitizeKnowledgeHtml(html: string): string {
  return sanitizeHtml(html, 'knowledge')
}

/**
 * Escape special HTML characters in a plain-text string so it can be safely
 * embedded in an HTML context without being interpreted as markup.
 *
 * Escapes: & < > " '
 *
 * Use this when constructing raw HTML strings (e.g. innerHTML / v-html
 * templates).  For full sanitization of rich HTML, use sanitizeChatHtml or
 * sanitizeHtml instead.
 *
 * @param text - Plain-text string to escape
 * @returns HTML-safe string
 */
export function escapeHtml(text: string): string {
  const map: Record<string, string> = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;',
  }
  return text.replace(/[&<>"']/g, (m) => map[m])
}
