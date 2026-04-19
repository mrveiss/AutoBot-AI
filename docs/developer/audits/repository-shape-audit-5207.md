# Repository Shape Audit (#5207)

Date: 2026-04-18 → 2026-04-19
Scope: `autobot-frontend/src/models/repositories/KnowledgeRepository.ts`
       + `autobot-frontend/src/models/repositories/SystemRepository.ts`
Related: #5200, #5202, #5203, #5204 (original connector-shape fixes)
Follow-ups filed: #5212, #5214, #5215

## Summary

- **49 `response.data as T` casts audited** across KnowledgeRepository (12) + SystemRepository (37)
- **7 fixed in this PR** (#5207) — shape-unwrap / envelope-normalisation applied
- **3 follow-up issues filed** for mismatches requiring backend-contract decisions or broad TS type refactors
- **~20 verified aligned** (mostly `any`-typed methods where backend returns a compatible envelope)
- **~19 not verifiable in this PR** (POST endpoints needing real connector_id / fact_id / running backup / security scan, and 4 aspirational endpoints that don't exist in the backend yet)

## Fix list

| Method | Endpoint | Backend shape | Declared shape | Action |
|---|---|---|---|---|
| `getPendingVerifications` | GET `/api/knowledge_base/verification/pending` | `{status, pending, total, limit, offset, has_more}` | `{sources, total, page}` | FIXED — unwrap `pending`, map `page`↔`offset` |
| `getVerificationConfig` | GET `/api/knowledge_base/verification/config` | `{status, config}` | `VerificationConfig` | FIXED — unwrap `.config` |
| `testConnector` | POST `/api/knowledge_base/connectors/{id}/test` | `{connector_id, healthy}` | `{success, message}` | FIXED — synthesise `{success, message}` from `healthy` (also #5203) |
| `syncConnector` | POST `/api/knowledge_base/connectors/{id}/sync` | `{connector_id, status, incremental}` | `SyncResult` | FIXED — return type changed to trigger-ack shape (also #5204). `ConnectorManager.vue` caller updated. |
| `getConnectorHistory` | GET `/api/knowledge_base/connectors/{id}/history` | `{connector_id, history, total}` | `SyncResult[]` | FIXED — unwrap `.history` |
| `getTerminalHistory` | GET `/api/agent-terminal/sessions` | `{status, total, sessions}` | `CommandExecutionResponse[]` | FIXED — unwrap `.sessions` |
| `getLogs` | GET `/api/logs/recent` | `{entries, count, limit, source}` | `any[]` | FIXED — unwrap `.entries` |

## Follow-ups filed

| Issue | Methods | Reason not fixed inline |
|---|---|---|
| [#5212](https://github.com/mrveiss/AutoBot-AI/issues/5212) | `checkHealth`, `getSystemInfo`, `getSystemMetrics` | Requires rewriting `HealthCheckResponse` / `SystemInfoResponse` / `SystemMetrics` in `types/models.ts` plus cascading call-site updates |
| [#5214](https://github.com/mrveiss/AutoBot-AI/issues/5214) | `getSettings`, `updateSettings`, `getConfigFiles`, `getConfigFile` | `AutoBotSettings` interface needs full rewrite to match backend section-keyed shape; config-file methods target an abstraction the backend no longer exposes |
| [#5215](https://github.com/mrveiss/AutoBot-AI/issues/5215) | `getKnowledgeStats`, `getDetailedKnowledgeStats` | Out of strict scope (generic-based not `as T`), but same class of bug; types need rewrite |

## KnowledgeRepository cast-by-cast walkthrough

| Line | Method | Verdict |
|---|---|---|
| L191 | `searchKnowledge` — reads `response.data.results` (no cast) | aligned via generic |
| L217 | `ragSearch` (no cast) | aligned via generic |
| L228 | `searchKnowledgeBase` — reads `.results` | aligned |
| L251 | `addTextToKnowledge` (no cast) | couldn't verify (needs POST body with valid content) |
| L261 | `addKnowledge` | couldn't verify |
| L282 | `addUrlToKnowledge` | couldn't verify |
| L313 | `addFileToKnowledge` | couldn't verify |
| L322 | `exportKnowledge` (Blob) | couldn't verify |
| L331 | `cleanupKnowledge` | couldn't verify |
| L339 | `getKnowledgeStats` | mismatch, filed #5215 |
| L347 | `getDetailedKnowledgeStats` | mismatch, filed #5215 |
| L355 | `getCategories` declared `string[]` | backend returns `{categories, total}` — MISMATCH, not in 49-cast list (generic-typed); added to #5215 |
| L363 | `getDocumentsByCategory` | couldn't verify without a real category |
| L371 | `getDocument` | couldn't verify without real id |
| L380 | `updateDocument` | couldn't verify |
| L389 | `deleteDocument` | couldn't verify |
| L402 | `bulkDeleteDocuments` | couldn't verify |
| **L412** | `getSimilarDocuments` | already defensively unwraps via `(data as any).results \|\| data`; OK |
| **L436** | `getSearchSuggestions` | backend returns 404 (endpoint not implemented); catch-all returns `[]`, safe |
| **L476** | `getPendingVerifications` | **FIXED** |
| **L490** | `approveSource` | declared `{status, message}`; backend returns `{status, fact_id, verified_by, verified_at, message}` — superset, aligned |
| **L505** | `rejectSource` | declared `{status, message}`; backend returns `{status, fact_id, deleted, message}` — compatible superset, aligned |
| **L516** | `getVerificationConfig` | **FIXED** |
| **L529** | `updateVerificationConfig` | declared `{status, config}`; backend returns `{status, config, message}` — superset, aligned |
| L559 | `listConnectors` | already fixed in #5200/#5202 |
| L575 | `createConnector` | already fixed in #5200/#5202 |
| **L588** | `getConnector` | backend returns `{config, status}` exactly as declared, aligned |
| L608 | `updateConnector` | already fixed in #5200/#5202 |
| **L629** | `testConnector` | **FIXED** (also resolves #5203) |
| **L642** | `syncConnector` | **FIXED** (also resolves #5204) |
| **L656** | `getConnectorHistory` | **FIXED** |
| **L682** | `getAllEntries` | already defensively unwraps; OK |

## SystemRepository cast-by-cast walkthrough

| Line | Method | Verdict |
|---|---|---|
| L55 | `checkHealth` | mismatch, filed #5212 |
| L61 | `getSystemStatus` | returns `any`, benign |
| L66 | `getSystemInfo` | mismatch, filed #5212 |
| L71 | `getSystemMetrics` | mismatch, filed #5212 |
| L77 | `getSettings` | mismatch, filed #5214 |
| L82 | `updateSettings` | mismatch, filed #5214 |
| L87 | `getBackendSettings` | returns `any`, benign |
| L92 | `saveBackendSettings` | returns `any`, benign |
| L98 | `getConfigFiles` | mismatch, filed #5214 |
| L104 | `getConfigFile` | mismatch, filed #5214 |
| L110 | `updateConfigFile` | returns `any`, benign |
| L117 | `executeCommand` | couldn't verify without running a command (declared type plausible) |
| L124 | `interruptProcess` | returns `any`, benign |
| L131 | `killAllProcesses` | returns `any`, benign |
| **L137** | `getTerminalHistory` | **FIXED** |
| L143 | `clearTerminalHistory` | returns `any`, benign |
| L151 | `restartBackend` | aspirational — endpoint doesn't exist |
| L157 | `shutdownSystem` | aspirational |
| L163 | `reloadConfiguration` | returns `any`, couldn't verify |
| L170 | `getDiagnosticsReport` | endpoint returns HTTP 500 — unverifiable in current backend state |
| L175 | `runDiagnostics` | POST, couldn't verify |
| L181 | `fixDiagnosticIssue` | returns `any`, couldn't verify |
| **L192** | `getLogs` | **FIXED** |
| L198 | `clearLogs` | returns `any`, benign |
| L204 | `downloadLogs` | endpoint `/api/logs/unified` returns 404 (path is wrong; handler likely at `/api/logs/read/unified`) — separate bug; out of audit scope |
| L212 | `getPerformanceMetrics` | returns `any`, benign |
| L218 | `getResourceUsage` | endpoint returns 500 — unverifiable |
| L225–L240 | backup methods (4) | aspirational |
| L247 | `getEnvironmentInfo` | returns `any`, benign |
| L253 | `getVersionInfo` | returns `any`, aligned |
| L259 | `checkForUpdates` | aspirational |
| L266 | `getSecurityStatus` | endpoint returns 500 — unverifiable |
| L271 | `runSecurityScan` | POST, couldn't verify |
| L277 | `getAuditLogs` | same endpoint as L266, 500 |

## Recommendation for the class-of-bug

Per #5207, three options were on the table. Recommendation: **Option C (openapi-typescript)**.

Rationale:
- Options A (per-method Zod) and C (generated types) both catch shape drift. C is strictly more comprehensive (every endpoint, not just the ones we've audited) and cheaper to maintain (no per-method schema to drift).
- FastAPI already serves `/openapi.json` natively. The remaining work is (1) add `openapi-typescript` as a dev dependency, (2) wire a `pnpm gen:api` script, (3) replace the hand-written `autobot-frontend/src/types/api.ts` bindings with the generated output.
- Option A becomes the migration strategy: file a new issue for each endpoint whose Zod-validated shape doesn't match the generated OpenAPI type, and fix either the backend response model or the frontend consumer.

The 49-cast audit was the necessary groundwork — now we know which specific endpoints are currently lying. Filed #5212, #5214, #5215 carry those forward.
