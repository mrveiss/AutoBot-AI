// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Type-only home the feature-flag components still import (#12363 slice 4).
 *
 * The client class is gone: the settings panel calls `apiClient.call`. The types moved to
 * `@/types/featureFlags`. AccessMetrics.vue and FlagChangeHistory.vue are being edited by an open PR
 * (#20990), so they keep this path until it lands; then this file is deleted (removal tracked in #21076).
 */
export type * from '@/types/featureFlags';
