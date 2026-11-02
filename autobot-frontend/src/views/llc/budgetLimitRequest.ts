// Copyright (c) 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/** The cost dashboard's budget settings form, as far as the limit request is concerned. */
export interface BudgetLimitForm {
  budget_mode: 'dollars' | 'tokens'
  budget_limit: number
  token_limit: number
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
    body.token_limit = form.token_limit
  }
  return body
}
