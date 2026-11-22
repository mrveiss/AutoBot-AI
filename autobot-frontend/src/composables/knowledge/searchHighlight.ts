// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Query-term highlighting for the knowledge search results (#3296, moved out of
 * KBSearchResultPanel.vue in #18244). Text is HTML-escaped first, then the matched
 * terms are wrapped in `<mark class="kb-highlight">`, so the result is safe for v-html.
 */
import { escapeHtml, type SemanticVariant } from '@autobot/ui'

const MIN_TERM_LENGTH = 2
const SNIPPET_LENGTH = 200
const SCORE_HIGH = 0.8
const SCORE_MEDIUM = 0.6

function escapeRegex(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/** A regex matching any individual query word of two or more characters; null when there are none. */
export function buildHighlightRegex(query: string): RegExp | null {
  const terms = query
    .trim()
    .split(/\s+/)
    .filter((term) => term.length >= MIN_TERM_LENGTH)
    .map(escapeRegex)
  return terms.length ? new RegExp(`(${terms.join('|')})`, 'gi') : null
}

/** Escaped text with the query's terms marked. */
export function highlightText(text: string, query: string): string {
  if (!text) return ''
  const regex = buildHighlightRegex(query)
  const escaped = escapeHtml(text)
  return regex ? escaped.replace(regex, '<mark class="kb-highlight">$1</mark>') : escaped
}

/** The first highlight (or the opening of the content), cut to a snippet and marked. */
export function highlightSnippet(raw: string, query: string): string {
  const snippet = raw.length > SNIPPET_LENGTH ? `${raw.substring(0, SNIPPET_LENGTH)}…` : raw
  return highlightText(snippet, query)
}

/** The badge variant for a 0..1 relevance score. */
export function scoreVariant(score: number): SemanticVariant {
  if (score >= SCORE_HIGH) return 'success'
  if (score >= SCORE_MEDIUM) return 'warning'
  return 'error'
}
