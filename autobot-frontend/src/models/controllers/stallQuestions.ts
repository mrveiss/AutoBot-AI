// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * A stalled chat turn's question (#21022) waits for the person while the graph is paused. A poll of the backend
 * history must not replace it: the graph would stay paused with no control left to answer it.
 */

type Card = { type?: string; metadata?: Record<string, unknown> | undefined }

const QUESTION_TYPE = 'human_question'

function questionId(card: Card): string | undefined {
  const id = card.type === QUESTION_TYPE ? card.metadata?.question_id : undefined
  return typeof id === 'string' ? id : undefined
}

/** True for a question card the person has not answered yet. */
export function isUnansweredQuestion(card: Card): boolean {
  return card.type === QUESTION_TYPE && card.metadata?.answered !== true
}

/** A loaded unanswered question takes the local answered state of the same question id (a stale response must not reopen it). */
function withLocalAnswer<L extends Card>(card: L, answered: ReadonlyMap<string, Card>): L {
  const id = questionId(card)
  const local = id === undefined ? undefined : answered.get(id)
  if (!local || !isUnansweredQuestion(card)) return card
  const { answered: done, answer_text: text } = local.metadata ?? {}
  return { ...card, metadata: { ...card.metadata, answered: done, answer_text: text } } as L
}

/**
 * *loaded* history plus every unanswered question card of *local* that it does not already hold (by question id).
 * A loaded card the person has already answered locally stays answered: a history response that started before the
 * answer was accepted must not offer the question again.
 */
export function keepUnansweredQuestions<L extends Card>(local: readonly Card[], loaded: L[]): L[] {
  const held = new Set(loaded.map(questionId).filter((id) => id !== undefined))
  const answered = new Map<string, Card>()
  for (const card of local) {
    const id = questionId(card)
    if (id !== undefined && card.metadata?.answered === true) answered.set(id, card)
  }
  const merged = answered.size ? loaded.map((card) => withLocalAnswer(card, answered)) : loaded
  const missing = local.filter((card) => {
    if (!isUnansweredQuestion(card)) return false
    const id = questionId(card)
    return id === undefined || !held.has(id)
  })
  return missing.length ? [...merged, ...(missing as unknown as L[])] : merged
}
