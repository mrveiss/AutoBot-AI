// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// The generated SLM contract lives in libs/slm-contract (ADR 011, #19834); `npm run gen:types`
// writes it there. This re-export keeps every `@/types/generated/api` importer resolving.
export type * from '@autobot/slm-contract/generated'
