#!/usr/bin/env node
// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Post-build: generate an SRI sha384 hash for dist-embed/embed.js
 * and write a ready-to-paste <script> tag to dist-embed/embed.sri.txt.
 *
 * Run automatically via the build:embed npm script.
 */

import { readFileSync, writeFileSync } from 'node:fs'
import { createHash } from 'node:crypto'

const distFile = 'dist-embed/embed.js'

let content
try {
  content = readFileSync(distFile)
} catch {
  console.error(`[embed-sri] ERROR: ${distFile} not found — run build first`)
  process.exit(1)
}

const hash = createHash('sha384').update(content).digest('base64')
const integrity = `sha384-${hash}`

const snippet = `<!-- AutoBot chat widget — replace CDN_URL with the actual hosted URL -->
<script src="CDN_URL/embed.js"
        integrity="${integrity}"
        crossorigin="anonymous"
        data-api-url="https://YOUR_AUTOBOT_HOST"
        data-org-id="YOUR_ORG_ID"></script>`

writeFileSync('dist-embed/embed.sri.txt', snippet)

console.log(`[embed-sri] Integrity: ${integrity}`)
console.log(`[embed-sri] Snippet written to dist-embed/embed.sri.txt`)
