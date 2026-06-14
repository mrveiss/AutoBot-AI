// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// @autobot/terminal — SSH terminal plugin for both frontends

import type { App } from 'vue'
import SshTerminal from './src/components/SshTerminal.vue'
import BaseXTerminal from './src/components/BaseXTerminal.vue'

export { SshTerminal, BaseXTerminal }
export { useTerminalStore } from './src/composables/useTerminalStore'
export type { HostConfig, TerminalSession, TerminalTab } from './src/composables/useTerminalStore'
export { useWebSocket } from './src/composables/useWebSocket'
export { usePollingJob } from './src/composables/usePollingJob'

export const TerminalPlugin = {
  install(app: App) {
    app.component('SshTerminal', SshTerminal)
    app.component('BaseXTerminal', BaseXTerminal)
  },
}

export default TerminalPlugin
