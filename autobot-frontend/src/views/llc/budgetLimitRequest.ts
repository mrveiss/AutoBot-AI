// Copyright (c) 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/** The least a token limit may be on a write. Mirrors `TOKEN_LIMIT_MIN` (autobot-backend/llc/models/budget.py, #20930). */
export const TOKEN_LIMIT_MIN = 1

/** The cost dashboard's budget settings form, as far as the limit request is concerned. */
export interface BudgetLimitForm {
  budget_mode: 'dollars' | 'tokens'
  budget_limit: number
  /** null (or an emptied field) means no token limit; a typed value must be >= TOKEN_LIMIT_MIN. */
  token_limit: number | null | ''
  alert_threshold_pct: number
}

/** The PATCH /budget/{agent}/limit body: the mode, the one limit that mode uses, and the alert threshold. */
export function limitPatchBody(form: BudgetLimitForm): Record<string, unknown> {
  const body: Record<string, unknown> = {
    budget_mode: form.budget_mode,
    alert_threshold: form.alert_threshold_pct / 100,
  }
  if (form.budget_mode === 'dollars') {
    body.budget_limit = form.budget_limit.toFixed(2)
  } else {
    body.token_limit = form.token_limit === '' ? null : form.token_limit
  }
  return body
}

/** Whether the form's token limit is a value the backend refuses (a typed value below TOKEN_LIMIT_MIN). */
export function tokenLimitInvalid(form: BudgetLimitForm): boolean {
  if (form.budget_mode !== 'tokens') return false
  const v = form.token_limit
  return v !== null && v !== '' && !(v >= TOKEN_LIMIT_MIN)
}
