// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * UI Components Barrel
 *
 * Barrel exports for reusable UI components.
 * CommandPermissionDialog uses Options API with .vue.d.ts stub for TS7016 compatibility.
 *
 * Issue #4534: Options API components without TypeScript stubs
 */

export { default as BaseAlert } from './BaseAlert.vue'
export { BaseModal } from '@autobot/ui'
export { default as CommandPermissionDialog } from './CommandPermissionDialog.vue'
export { default as DarkModeToggle } from './DarkModeToggle.vue'
export { default as DataTable } from './DataTable.vue'
export { default as EmptyState } from './EmptyState.vue'
export { default as HostSelectionDialog } from './HostSelectionDialog.vue'
export { default as HostSelector } from './HostSelector.vue'
export { default as LoadingSpinner } from './LoadingSpinner.vue'
export { default as MessageStatus } from './MessageStatus.vue'
export { default as OfflineBanner } from './OfflineBanner.vue'
export { default as PreferencesPanel } from './PreferencesPanel.vue'
export { default as ProgressBar } from './ProgressBar.vue'
export { default as SkeletonLoader } from './SkeletonLoader.vue'
export { default as StableLoadingState } from './StableLoadingState.vue'
export { default as StatusBadge } from './StatusBadge.vue'
export { default as SystemStatusNotification } from './SystemStatusNotification.vue'
export { default as ThemeToggle } from './ThemeToggle.vue'
export { default as ToastContainer } from './ToastContainer.vue'
export { default as TouchFriendlyButton } from './TouchFriendlyButton.vue'
export { default as LoadingBoundary } from './LoadingBoundary.vue'
export { default as LoadingOverlay } from './LoadingOverlay.vue'
