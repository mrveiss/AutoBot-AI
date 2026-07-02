// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// @autobot/ui — shared, theme-agnostic UI component kit.
//
// Consumed by BOTH frontends (autobot-frontend, autobot-slm-frontend) via a
// file: dependency. Components are styled entirely off the semantic token
// contract in ./src/tokens/contract.css — they NEVER hardcode a color. Each
// app supplies its own token values, so the same component renders in each
// app's own color identity (the SLM control plane keeps its distinct scheme).
//
// See README.md for the token contract and authoring rules.

export { default as BaseButton } from './src/components/BaseButton.vue'
export type { ButtonVariant, ButtonSize } from './src/components/BaseButton.vue'
