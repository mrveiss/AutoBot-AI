// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/** Board and source-card shapes for KnowledgeResearchPanel.vue (split out for the size ceiling, #18730). */

export interface Board {
  board_id: string
  name: string
}

export interface SourceCard {
  url: string
  title: string
  snippet: string
  score: number | null
  domain: string
  recommendation: string | null
  decision: 'accepted' | 'rejected' | null
}
