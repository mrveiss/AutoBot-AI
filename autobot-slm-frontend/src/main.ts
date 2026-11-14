// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import i18n, { initI18n } from './i18n'

import './assets/styles/main.css'

// @autobot/ui shared kit: token contract fallbacks first, then the kit's one
// adapter (mapping --aui-* onto the shared semantic token names, which main.css
// and slm-scheme.css define with the SLM's own values). Loaded AFTER main.css so
// those tokens are already defined — the SLM keeps its own color identity; only
// the token names are shared (#10860).
import '@autobot/ui/tokens'
import '@autobot/ui/adapter'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(i18n)
// #14781: set html[lang]/html[dir] from the resolved locale before mount, so an
// RTL language lays out right-to-left on first paint rather than after a switch.
initI18n()

app.mount('#app')
