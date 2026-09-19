// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The clients of the endpoints #17009 authenticates send the token (#17009, #16457).
 *
 * #17009 made nine backend WebSocket endpoints authenticate before accepting.
 * Five of them have a frontend client, and all five opened their socket through
 * `useWebSocket()` with no credential at all. A browser cannot set a header on a
 * WebSocket, and the backend reads no cookie there, so without the bearer
 * subprotocol every one of them would be refused and its panel would stop
 * working. Each must pass `protocols` built from `buildAuthenticatedWsSubprotocols()`.
 *
 * The list is explicit rather than "every useWebSocket caller": offering a
 * subprotocol to an endpoint that does not echo it fails the handshake in the
 * browser (#16457), so only endpoints that authenticate may be sent one.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const SRC = resolve(dirname(fileURLToPath(import.meta.url)), '..')

/** Client file -> the backend endpoint it opens. */
const CLIENTS: Record<string, string> = {
  'components/knowledge/KnowledgeResearchPanel.vue': '/api/ws/knowledge/research',
  'composables/useOverseerAgent.ts': '/overseer/ws/',
  'composables/useWorkflowBuilder.ts': '/api/workflow-automation/workflow_ws/',
  'components/analytics/CodeQualityDashboard.vue': '/api/quality/ws',
  'composables/usePrometheusMetrics.ts': '/api/monitoring/realtime',
}

const SENDS_TOKEN = /protocols:\s*\(\)\s*=>\s*buildAuthenticatedWsSubprotocols\(\)/

describe('clients of #17009-authenticated WebSocket endpoints send the bearer subprotocol', () => {
  for (const [file, endpoint] of Object.entries(CLIENTS)) {
    it(`${file} opens ${endpoint} with the token`, () => {
      const source = readFileSync(resolve(SRC, file), 'utf-8')
      expect(source, `${file} no longer opens ${endpoint}; re-derive this list`).toContain(endpoint)
      expect(source).toMatch(SENDS_TOKEN)
    })
  }

  it('the detector refuses a client that opens the socket with no credential', () => {
    expect("useWebSocket(url, { autoConnect: false })").not.toMatch(SENDS_TOKEN)
    expect("useWebSocket(url, { protocols: () => buildAuthenticatedWsSubprotocols() ?? undefined })").toMatch(
      SENDS_TOKEN,
    )
  })
})
