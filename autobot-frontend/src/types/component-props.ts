// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// Canonical shared prop types for UI components
export type { Size as ComponentSize } from '@/design-tokens/tokens'

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

export type BadgeVariant = 'default' | 'primary' | 'success' | 'warning' | 'error' | 'info'
