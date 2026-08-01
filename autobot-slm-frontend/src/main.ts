// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import i18n from './i18n'

import './assets/styles/main.css'

// @autobot/ui shared kit: token contract fallbacks first, then the SLM adapter
// (mapping --aui-* onto the SLM control plane's own design tokens). Loaded AFTER
// main.css so the SLM tokens the adapter references are already defined — the
// SLM keeps its own color identity; only the token contract is shared (#10860).
import '@autobot/ui/tokens'
import './assets/styles/aui-theme.css'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(i18n)

app.mount('#app')
