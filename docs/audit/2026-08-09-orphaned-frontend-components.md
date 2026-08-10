# Orphaned frontend components — built, documented, unreachable

**Date:** 2026-08-09
**Umbrella issue:** https://github.com/mrveiss/AutoBot-AI/issues/13810
**Pairing wiring gap:** https://github.com/mrveiss/AutoBot-AI/issues/13794
**Supersedes:** `docs/audit/frontend-orphaned-components-4194.md` (2026-04-13, issue #4194), which asked the same question and is now stale — both components it named as true orphans (`CodeEvolutionTimeline`, `OperationDetail`) have since been wired in and do not appear below.
**Method:** every `components/**/*.vue` checked for any reference (import or tag) from any other `.vue`/`.ts`/`.js` in `autobot-frontend/src`.

```
total components:            368
referenced nowhere else:      11   (10 actionable; 1 example excluded)
```

## The components

| Component | Design doc | Issue ref in source |
|---|---|---|
| `admin/HealthBar.vue` | `docs/superpowers/plans/2026-07-07-content-reach-task8-frontend.md` | — |
| `chat/MCPPromptTemplatePicker.vue` | **none found** | — |
| `knowledge/modals/DocumentExportModal.vue` | `docs/archives/plans/2026-02-01-knowledge-manager-frontend-implementation.md` | — |
| `knowledge/panels/SourcePreviewPanel.vue` | `docs/archives/plans/2026-02-28-knowledge-system-vision-gaps.md` | #2849 † |
| `mobile/PairDeviceDialog.vue` | `docs/design/2026-06-04-pair-device-dialog.md` | — |
| `settings/DevicePairingSettingsPanel.vue` | **none found** | MVA-3085 |
| `transcriber/AiAnalysisPanel.vue` | `docs/superpowers/plans/2026-05-30-transcriber-plan-4-frontend.md` | — |
| `transcriber/ExportMenu.vue` | `docs/superpowers/specs/2026-05-30-transcriber-module-design.md` | — |
| `transcriber/KbPushButton.vue` | `docs/superpowers/specs/2026-05-30-transcriber-module-design.md` | — |
| `transcriber/SpeakerLabel.vue` | `docs/superpowers/specs/2026-05-30-transcriber-module-design.md` | — |

`examples/ThemingPatternExample.vue` is excluded — an example component with no consumer is expected. That is why this table
lists 10 while the count above says 11, and why #13810 is titled "10 components".

† `#2849` is a later memory-leak fix that touched the file, not the issue the component was built for. The column records
whatever issue the source cites; for this row that is provenance of a repair, not of the design.

## Two clusters, not ten isolated misses

**Transcriber (4 components, one design.)** `AiAnalysisPanel`, `ExportMenu`, `KbPushButton` and `SpeakerLabel` all trace to
`docs/superpowers/specs/2026-05-30-transcriber-module-design.md`. A whole feature area shipped its parts and never mounted them.

**Device pairing (2 components, built twice.)** `PairDeviceDialog.vue` (+ `usePairingQR.ts`) and
`settings/DevicePairingSettingsPanel.vue` are **independent implementations of the same feature**, and neither is reachable.
The panel does not use the dialog — it re-implements the QR flow, calling `GET /api/devices/pair-qr` and rendering with its own
`import QRCode from 'qrcode'`. `SettingsView.vue` mounts other settings panels; this one was never added.

## Why these drift out of sight: design docs have five homes

```
docs/design/              canonical per docs/README.md — dated YYYY-MM-DD-topic.md, current to 2026-08
docs/designs/             near-empty duplicate — only _index.md and mockups/
docs/archives/plans/      "Jan–Mar 2026" per docs/INDEX.md, 103 files
docs/superpowers/plans/   active, holds live frontend plans
docs/superpowers/specs/   active, holds the transcriber design
```

A design doc in `superpowers/specs/` has no relationship to the issue tracker and no link from the component it describes, so
"is this wired?" is answerable only by a retrospective grep — which is exactly how each of these was found.
`.paperclip-work/MVA-2993-design.md` sat at the repo root for two months for the same reason — and it is not alone:
ten `*_REPORT.md` analyses are parked at the root, unlinked from any index (#13873).

## Recommended

1. **One design home.** `docs/design/` is already canonical per `docs/README.md`; fold `docs/designs/` into it and stop new designs landing in `superpowers/`.
2. **Bidirectional links.** Every design doc carries `**Issue:** <url>`; every issue links its design. The convention exists — `docs/archives/plans/2026-01-19-issue-722-credential-handling-design.md` does it — but is not applied consistently.
   The same applies to audits: this document supersedes an earlier one that nothing pointed at, which is how its stale
   conclusions stayed reachable. `docs/design/` also carries two competing indexes (`README.md`'s "## 2026" table and
   `_index.md`, which lists 2 of 5 docs) — the five-homes problem repeating one level down.
3. **A wiring check.** An orphan grep of this kind is cheap enough to run in CI. That is the durable fix: #13631 describes the same gap as "no declared-vs-executable capability flags", and every entry above was found by audit rather than by a gate.
