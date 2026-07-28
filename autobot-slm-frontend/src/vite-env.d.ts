// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/// <reference types="vite/client" />

// @autobot/ui ships its design-token contract as CSS via the "./tokens" export
// subpath (a side-effect-only import). vite/client's `*.css` glob only matches
// specifiers ending in `.css`, not this bare specifier, so declare it explicitly
// for vue-tsc (bundler resolution maps it to src/tokens/contract.css at build).
declare module '@autobot/ui/tokens'

interface ImportMetaEnv {
  readonly VITE_API_URL: string
  readonly VITE_WS_URL: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
