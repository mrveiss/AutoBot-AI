// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// Type boundary for the @autobot/terminal plugin (a `file:` package at
// ../autobot-plugins/terminal), mapped here via tsconfig `paths`. The SLM app
// consumes the plugin's public SshTerminal component; it must NOT type-check the
// plugin's internals, which resolve @xterm/* and pinia from the plugin's own
// node_modules (absent in this app's install). Vite still bundles the real
// plugin source at build time via its alias — only vue-tsc uses this stub. The
// plugin's own type debt is tracked separately. (#10493)
import type { DefineComponent } from 'vue'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const SshTerminal: DefineComponent<any, any, any>
