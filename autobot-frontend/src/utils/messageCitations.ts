// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The one reading of an answer's sources (#21976, #4448).
 *
 * A source is either the unified entry the backend writes (`type`, `reliability`, a step's tool, args and origin),
 * identical in the stream (`metadata.citations`) and in the stored message (`sources`), or a legacy stored
 * knowledge-base entry `{title, path, score, chunk_id}` with no `type`, which reads as `knowledge_base`.
 */

import type { ChatMessage, RagSource } from '@/types/api'

/** What the backend proved about the values an answer quotes (see `answer_sources.py`). */
export interface AnswerProof {
  checked: number
  /** The check read only part of a step's output, or could not read it. */
  truncated?: boolean
  /** value -> the step id, `user` or `knowledge_base` it appears in. */
  found: Record<string, string>
  /** Values that appear in no tool result of the turn: not proven, which is not the same as wrong. */
  unproven: string[]
}

/** A source as the backend stores or streams it: every `RagSource` field optional, legacy or unified. */
export type StoredSource = Partial<RagSource> & { source?: string }

/** A stored or streamed source as one `RagSource` that keeps every unified field and fills the legacy ones. */
export function toSource(raw: StoredSource): RagSource {
  const source = raw.source ?? raw.path ?? ''
  return {
    ...raw,
    type: raw.type ?? 'knowledge_base',
    title: raw.title ?? source,
    path: raw.path ?? source,
    score: typeof raw.score === 'number' ? raw.score : 0,
    chunk_id: raw.chunk_id ?? raw.id ?? '',
  }
}

/** The citation list a message shows: its stored sources, else the stream's `metadata.citations`. */
export function messageCitations(message: ChatMessage): RagSource[] {
  const stored = Array.isArray(message.sources) ? message.sources : []
  const streamed: unknown = message.metadata?.citations // untyped wire data: read as the stored shape
  const raw = stored.length > 0 ? stored : Array.isArray(streamed) ? (streamed as StoredSource[]) : []
  return raw.map((s) => ({ ...toSource(s), id: s.id ?? s.chunk_id }))
}

/** The values of this message's answer that no tool result of the turn contains. */
export function unprovenValues(message: ChatMessage): string[] {
  const proof = message.metadata?.proof as AnswerProof | undefined
  return Array.isArray(proof?.unproven) ? proof!.unproven : []
}

/** True when the proof check was partial, so the UI must not read "no unproven values" as a full check. */
export function proofIsPartial(message: ChatMessage): boolean {
  const proof = message.metadata?.proof as AnswerProof | undefined
  return proof?.truncated === true
}
