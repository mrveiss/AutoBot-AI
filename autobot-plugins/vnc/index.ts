// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// @autobot/vnc — VNC viewer + controls plugin for both frontends

import type { App } from 'vue'
import VncViewer from './src/components/VncViewer.vue'
import VncToolbar from './src/components/VncToolbar.vue'

export { VncViewer, VncToolbar }
export { useVncControls } from './src/composables/useVncControls'
// #12653: VncRequest/UseVncControlsOptions were added by #12931's transport
// injection but never re-exported here, so consumers could not name the
// injected transport's type — the package exported the seam without its shape.
export type {
  VncActionResponse,
  MouseClickParams,
  MouseDragParams,
  MouseScrollParams,
  VncRequest,
  UseVncControlsOptions,
} from './src/composables/useVncControls'
export type { VncHost } from './src/types'

export const VncPlugin = {
  install(app: App) {
    app.component('VncViewer', VncViewer)
    app.component('VncToolbar', VncToolbar)
  },
}

export default VncPlugin
