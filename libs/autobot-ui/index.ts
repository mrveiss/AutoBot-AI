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

export { default as BaseBadge } from './src/components/BaseBadge.vue'
export type { BadgeVariant, BadgeSize } from './src/components/BaseBadge.vue'

export { default as BaseCard } from './src/components/BaseCard.vue'

export { default as EmptyState } from './src/components/EmptyState.vue'

export { default as BaseModal } from './src/components/BaseModal.vue'
export type { ModalSize } from './src/components/BaseModal.vue'

// Dialog-a11y composables — the focus-trap / scroll-lock / focus-restore /
// initial-focus primitives shared by every dialog and modal consumer.
export { useFocusTrap, isTabbable, FOCUSABLE_SELECTOR } from './src/composables/useFocusTrap'
export type { UseFocusTrapReturn } from './src/composables/useFocusTrap'

export { useFocusRestore } from './src/composables/useFocusRestore'

export { useInitialFocus } from './src/composables/useInitialFocus'
export type { UseInitialFocusReturn } from './src/composables/useInitialFocus'

export { useBodyScrollLock, __resetLockStateForTests } from './src/composables/useBodyScrollLock'

// Data composables — pagination + form-validation primitives promoted from
// the main app (#10885) so both frontends import them from one canonical
// home instead of re-deriving them per view.
export { usePagination, useSimplePagination, useShowAllToggle } from './src/composables/usePagination'
export type { PaginationOptions, UsePaginationReturn } from './src/composables/usePagination'

export { useFormValidation, quickValidate, validators } from './src/composables/useFormValidation'
export type {
  ValidationRule,
  ValidationRuleConfig,
  FieldConfig,
  UseFormValidationReturn,
} from './src/composables/useFormValidation'
