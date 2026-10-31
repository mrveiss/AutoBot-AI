// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Debug Utilities
 *
 * Structured logging for the SLM Admin frontend. The logger is the kit's (`@autobot/ui`):
 * its level filtering (debug dropped in production builds) used to live only in this
 * file and moved into the kit so both apps behave the same (#14908). This module keeps
 * the import path the SLM's callers already use.
 */

export { createLogger, type LogLevel } from '@autobot/ui'
