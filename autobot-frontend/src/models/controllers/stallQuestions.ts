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

/** *loaded* history plus every unanswered question card of *local* that it does not already hold (by question id). */
export function keepUnansweredQuestions<L extends Card>(local: readonly Card[], loaded: L[]): L[] {
  const held = new Set(loaded.map(questionId).filter((id) => id !== undefined))
  const missing = local.filter((card) => {
    if (!isUnansweredQuestion(card)) return false
    const id = questionId(card)
    return id === undefined || !held.has(id)
  })
  return missing.length ? [...loaded, ...(missing as unknown as L[])] : loaded
}
