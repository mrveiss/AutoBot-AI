// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// @autobot/vnc — VNC viewer + controls plugin for both frontends

import type { App } from 'vue'
import VncViewer from './src/components/VncViewer.vue'
import VncToolbar from './src/components/VncToolbar.vue'

export { VncViewer, VncToolbar }
export { useVncControls } from './src/composables/useVncControls'
export type { VncActionResponse, MouseClickParams, MouseDragParams, MouseScrollParams } from './src/composables/useVncControls'
export type { VncHost } from './src/types'

export const VncPlugin = {
  install(app: App) {
    app.component('VncViewer', VncViewer)
    app.component('VncToolbar', VncToolbar)
  },
}

export default VncPlugin
