// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * SLM Type Definitions
 *
 * The definitions live in `@autobot/slm-contract` (libs/slm-contract), the one home both
 * frontends import (ADR 011, #19834). This module re-exports them so every `@/types/slm`
 * importer keeps resolving unchanged.
 */
export type * from '@autobot/slm-contract'
