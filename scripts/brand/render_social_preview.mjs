// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Render the GitHub social preview (1280x640) from the canonical brand mark (#18266).
 *
 * The mark is read from libs/autobot-ui/src/assets/brand/mark.svg and inlined, never
 * redrawn, so a new mark yields a new preview by re-running this script. The card's colours
 * are the mark's own (its surface and its stroke), and the words are the README's.
 *
 *   node scripts/brand/render_social_preview.mjs
 *
 * Uses the Playwright already installed for autobot-frontend; writes
 * docs/assets/social-preview.png. repo_tests/social_preview_18266_test.py pins the pair.
 */

import { readFileSync, mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createRequire } from 'node:module'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..')
const require = createRequire(resolve(root, 'autobot-frontend', 'package.json'))
const { chromium } = require('playwright')

/** The card takes its colours from the mark; a mark without them is an error that names which. */
function markColour(pattern, what) {
  const found = mark.match(pattern)
  if (!found) {
    throw new Error(`render_social_preview: mark.svg has no 6-digit hex ${what}; the card takes its colours from the mark (#18266)`)
  }
  return found[1]
}

const mark = readFileSync(resolve(root, 'libs/autobot-ui/src/assets/brand/mark.svg'), 'utf-8')
const surface = markColour(/<rect[^>]*fill="(#[0-9A-Fa-f]{6})"/, 'surface (the <rect> fill)')
const ink = markColour(/stroke="(#[0-9A-Fa-f]{6})"/, 'ink (the stroke)')
const out = resolve(root, 'docs/assets/social-preview.png')

const html = `<!doctype html><html><head><meta charset="utf-8"><style>
  html, body { margin: 0; width: 1280px; height: 640px; }
  body { display: flex; align-items: center; gap: 64px; padding: 0 112px; box-sizing: border-box;
         background: ${surface}; color: ${ink}; font-family: 'Inter', 'Segoe UI', system-ui, sans-serif; }
  .mark svg { width: 256px; height: 256px; display: block; }
  h1 { font-size: 88px; margin: 0 0 12px; letter-spacing: -2px; }
  p { margin: 0; font-size: 40px; opacity: 0.92; }
  small { display: block; margin-top: 28px; font-size: 26px; opacity: 0.7; text-wrap: balance; }
</style></head><body>
  <div class="mark">${mark}</div>
  <div><h1>AutoBot</h1><p>Your data. Your AI.</p><small>A self-hosted AI platform you own, not a service you rent.</small></div>
</body></html>`

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1280, height: 640 }, deviceScaleFactor: 1 })
await page.setContent(html, { waitUntil: 'load' })
mkdirSync(dirname(out), { recursive: true })
await page.screenshot({ path: out, type: 'png' })
await browser.close()
console.log(`wrote ${out}`)
