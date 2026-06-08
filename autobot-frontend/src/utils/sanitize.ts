// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * HTML sanitization utilities using DOMPurify.
 * All user-generated or LLM-generated content rendered via v-html
 * MUST be sanitized through these functions to prevent XSS (#2847).
 */

import DOMPurify from 'dompurify'
import type { Config as DOMPurifyConfig } from 'dompurify'

/**
 * Default DOMPurify configuration for chat/message content.
 * Allows safe formatting tags while stripping scripts and event handlers.
 */
const CHAT_SANITIZE_CONFIG: DOMPurifyConfig = {
  ALLOWED_TAGS: [
    'br',
    'strong',
    'em',
    'code',
    'pre',
    'a',
    'span',
    'div',
    'p',
  ],
  ALLOWED_ATTR: ['href', 'target', 'rel', 'class'],
}

/**
 * Strict DOMPurify configuration for knowledge/document content.
 * Allows basic formatting only.
 */
const KNOWLEDGE_SANITIZE_CONFIG: DOMPurifyConfig = {
  ALLOWED_TAGS: ['br', 'strong', 'em', 'code', 'pre', 'span', 'p'],
  ALLOWED_ATTR: ['class'],
}

/**
 * Sanitize HTML content intended for chat messages.
 * Permits formatting tags (br, strong, em, code, pre, a, span)
 * and safe attributes (href, target, rel, class).
 *
 * @param html - Raw HTML string to sanitize
 * @returns Sanitized HTML string safe for v-html rendering
 */
export function sanitizeChatHtml(html: string): string {
  return DOMPurify.sanitize(html, CHAT_SANITIZE_CONFIG) as string
}

/**
 * Sanitize HTML content intended for knowledge entries.
 * More restrictive than chat -- no links allowed.
 *
 * @param html - Raw HTML string to sanitize
 * @returns Sanitized HTML string safe for v-html rendering
 */
export function sanitizeKnowledgeHtml(html: string): string {
  return DOMPurify.sanitize(html, KNOWLEDGE_SANITIZE_CONFIG) as string
}

/**
 * Sanitize HTML content with a custom DOMPurify configuration.
 *
 * @param html - Raw HTML string to sanitize
 * @param config - DOMPurify configuration object
 * @returns Sanitized HTML string safe for v-html rendering
 */
export function sanitizeHtml(
  html: string,
  config?: DOMPurifyConfig,
): string {
  return DOMPurify.sanitize(html, config ?? CHAT_SANITIZE_CONFIG) as string
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
