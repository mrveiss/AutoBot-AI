// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Entity anchor navigation (Issue #9479, follow-up to #9297).
 *
 * The chat system prompt emits `[Name](#kind-id)` markdown anchors for
 * navigable entities (sessions, documents, tasks, workflows, knowledge items).
 * This composable resolves a hash anchor href to a Vue Router location so the
 * chat message renderer can intercept clicks and route to the right view —
 * with zero backend changes.
 *
 * Anchor format: `#<kind>-<id>` where kind is one of the keys below.
 */

import type { RouteLocationRaw } from 'vue-router'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useEntityAnchors')

/** Recognised entity kinds and their anchor prefixes. */
export type EntityKind = 'session' | 'document' | 'task' | 'workflow' | 'knowledge'

const ENTITY_KINDS: readonly EntityKind[] = [
  'session',
  'document',
  'task',
  'workflow',
  'knowledge',
] as const

/** A parsed entity anchor. */
export interface ParsedEntityAnchor {
  kind: EntityKind
  id: string
}

/**
 * Parse a hash anchor href (e.g. `#document-42`) into its kind and id.
 *
 * Returns `null` for hrefs that are not recognised entity anchors so that
 * regular external links and plain heading anchors are left untouched.
 */
export function parseEntityAnchor(href: string | null | undefined): ParsedEntityAnchor | null {
  if (!href || !href.startsWith('#')) return null

  const body = href.slice(1)
  const dash = body.indexOf('-')
  if (dash <= 0) return null

  const kind = body.slice(0, dash)
  const id = body.slice(dash + 1)
  if (!id) return null

  if (!(ENTITY_KINDS as readonly string[]).includes(kind)) return null

  return { kind: kind as EntityKind, id }
}

/**
 * Resolve a parsed entity anchor to a Vue Router location.
 *
 * Kinds with a dedicated detail route navigate by named route + params;
 * the rest target the most useful existing destination and pass the id as a
 * query param so that view can focus/highlight the referenced entity.
 */
export function resolveEntityRoute(anchor: ParsedEntityAnchor): RouteLocationRaw {
  switch (anchor.kind) {
    case 'session':
      return { name: 'chat-session', params: { sessionId: anchor.id } }
    case 'document':
      return { name: 'document-detail', params: { docId: anchor.id } }
    case 'workflow':
      return { name: 'automation', query: { workflow: anchor.id } }
    case 'task':
      return { name: 'automation', query: { task: anchor.id } }
    case 'knowledge':
      return { name: 'knowledge-graph-entities', query: { entity: anchor.id } }
  }
}

/** Escape the HTML-significant characters in plain text. */
function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/**
 * Convert `[text](href)` markdown links to anchor tags.
 *
 * Entity-anchor hash hrefs (`#kind-id`) become same-tab links so the click
 * handler can intercept them; http(s) hrefs become new-tab external links.
 * Any other scheme is dropped (rendered as the link text only) to avoid
 * `javascript:` and similar injection — DOMPurify is the second line of
 * defence, this is the first.
 */
export function renderMarkdownLinks(content: string): string {
  return content.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_match, text: string, href: string) => {
    const label = escapeHtml(text)
    if (parseEntityAnchor(href)) {
      return `<a href="${escapeHtml(href)}">${label}</a>`
    }
    if (/^https?:\/\//i.test(href)) {
      return `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">${label}</a>`
    }
    return label
  })
}

export interface EntityAnchorNavigator {
  push: (to: RouteLocationRaw) => unknown
}

/**
 * Build a click handler that intercepts entity-anchor clicks within a
 * v-html message body and routes them via the supplied navigator.
 *
 * The handler is a no-op for non-anchor targets and for non-entity hrefs,
 * leaving external links and heading anchors to their default behaviour.
 *
 * @param navigator - object exposing a router-like `push` (e.g. `useRouter()`)
 * @returns a DOM event handler suitable for `@click` on the message container
 */
export function createEntityAnchorClickHandler(navigator: EntityAnchorNavigator) {
  return (event: MouseEvent): void => {
    const target = event.target as HTMLElement | null
    const anchorEl = target?.closest('a')
    if (!anchorEl) return

    const parsed = parseEntityAnchor(anchorEl.getAttribute('href'))
    if (!parsed) return

    // It's an entity anchor — take over from the default hash behaviour.
    event.preventDefault()

    const to = resolveEntityRoute(parsed)
    logger.debug(`Navigating to ${parsed.kind} ${parsed.id}`)
    Promise.resolve(navigator.push(to)).catch((err: unknown) => {
      logger.error(`Failed to navigate to ${parsed.kind} ${parsed.id}`, err)
    })
  }
}
