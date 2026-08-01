// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// Canonical shared prop types for UI components
export type { Size as ComponentSize } from '@/design-tokens/tokens'
import type { SemanticVariant } from '@autobot/ui'

export type ButtonVariant =
  | 'primary'
  | 'secondary'
  | 'success'
  | 'error'
  | 'warning'
  | 'info'
  | 'light'
  | 'dark'
  | 'outline-solid'
  | 'ghost'
  | 'link'

// BadgeVariant is the shared presentational semantic vocabulary (#10885):
// neutral | primary | success | warning | danger | info. The former local
// 'default'/'error' members were reconciled to canonical 'neutral'/'danger'.
export type BadgeVariant = SemanticVariant
