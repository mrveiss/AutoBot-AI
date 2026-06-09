// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot Embeddable Chat Widget — entry point
 *
 * Drop-in usage (always include integrity= when loading from a CDN):
 *
 *   <script src="https://cdn.example.com/embed.js"
 *           integrity="sha384-<hash from dist-embed/embed.sri.txt>"
 *           crossorigin="anonymous"
 *           data-api-url="https://your-autobot.example.com"
 *           data-org-id="my-org"
 *           data-theme="light"
 *           data-position="bottom-right"
 *           data-title="Chat with us"
 *           data-placeholder="Ask me anything…"
 *           data-primary-color="#6366f1"></script>
 *
 * Run `npm run build:embed` to build embed.js and generate the SRI hash.
 * The ready-to-paste snippet is written to dist-embed/embed.sri.txt.
 *
 * Or place the element yourself anywhere in the DOM:
 *   <autobot-widget data-api-url="…"></autobot-widget>
 */

import { AutobotWidget } from './AutobotWidget'

// Guard against double-registration (multiple script tags)
if (!customElements.get('autobot-widget')) {
  customElements.define('autobot-widget', AutobotWidget)
}

// Auto-inject element when loaded via <script data-api-url="…">
const currentScript = document.currentScript as HTMLScriptElement | null
if (currentScript) {
  const tag = document.createElement('autobot-widget')
  const forward = [
    'data-api-url',
    'data-org-id',
    'data-theme',
    'data-position',
    'data-title',
    'data-placeholder',
    'data-primary-color',
    'data-button-label',
  ]
  for (const attr of forward) {
    const val = currentScript.getAttribute(attr)
    if (val !== null) tag.setAttribute(attr, val)
  }
  document.body.appendChild(tag)
}
