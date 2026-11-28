// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Type-only home ChatInput.vue still imports (#12363 slice 4).
 *
 * The client class is gone: the vision components call `composables/useVisionApi`. The types moved to
 * `@/types/visionMultimodal`. ChatInput.vue is being edited by open PRs (#21007, #21009, #21051), so it
 * keeps this path until they land; then this file is deleted (removal tracked in #21076).
 */
export type * from '@/types/visionMultimodal';
