# Source Analysis: Model Hardware Standard (MHS)

**Source:** <https://www.modelhardwarestandard.com/> — research preview landing page + waitlist
**Researched:** 2026-08-29 · **Phase 1 only** (AutoBot comparison not yet approved)

## References

| # | Source | Type | Used for |
|---|--------|------|----------|
| S1 | [modelhardwarestandard.com](https://www.modelhardwarestandard.com/) | Primary — vendor landing page | Scope, status, device categories, waitlist gate |
| S2 | [Previewing the Model Hardware Standard — Anthropic](https://www.anthropic.com/news/model-hardware-standard-research-preview) | Primary — vendor announcement | Architecture, partners, all benchmark numbers |
| S3 | [Anthropic's MHS Lets Claude Control Lab Robots Overnight — AlphaSignal](https://alphasignal.ai/news/anthropic-s-model-hardware-standard-lets-claude-control-lab-robots-overnight) | Secondary — trade press | Driver primitives, failure modes, limitations |
| S4 | [New Anthropic standard MHS connects AI to machines — Techzine](https://www.techzine.eu/news/infrastructure/143906/new-anthropic-standard-mhs-connects-ai-to-machines/) | Secondary — trade press | MCP relationship, partner list, caveats |
| S5 | [Anthropic pushes into physical world… — CNBC](https://www.cnbc.com/2026/08/27/anthropic-pushes-into-physical-world-with-new-standard-to-help-ai-agents-operate-machines.html) | Secondary — trade press | Announcement framing (403 on fetch; cited via search index only) |
| S6 | [Anthropic proposes plumbing spec to link AI agents to lab kit and robots — The Register](https://www.theregister.com/ai-and-ml/2026/08/28/anthropic-proposes-plumbing-spec-to-link-ai-agents-to-lab-kit-and-robots/5293135) | Secondary — skeptical trade press | Framing as "plumbing spec" (404 on fetch; cited via search index only) |
| S7 | [ANI: Anthropic announces new MHS, plans open-source release](https://www.aninews.in/news/business/anthropic-announces-new-model-hardware-standard-for-ai-agents-plans-open-source-release-with-safety-guidance20260828112959/) | Secondary — wire | Open-source intent (403 on fetch; cited via search index only) |
| S8 | [@AnthropicAI announcement post](https://x.com/AnthropicAI/status/2093038426140651791) | Primary — vendor social | Launch date, one-line positioning |

> **Sourcing caveat:** every technical claim below traces to S2/S3/S4. The specification
> itself is **not public** — no schema, no IDL, no repository, no version number is
> published. S5, S6 and S7 returned 403/404 to direct fetch and are cited only from
> search-engine summaries; treat their attributions as weaker than S1–S4.

## What It Is

MHS is a proposed open standard from **Anthropic**, originating in a collaboration with
**HHMI Janelia Research Campus** (Anthropic's Alek Kemeny with Janelia's Arco Bast), that
lets AI agents drive physical laboratory and manufacturing equipment — microscopes,
liquid handlers / pipette robots, robot arms, centrifuges, spectrometers, incubators,
cameras, lasers (S1, S2). Announced **2026-08-27** as a **limited research preview**
behind an application form; Anthropic states an intent to open-source it after the
preview establishes safety evaluations and operating practices (S1, S2, S7). Maturity:
**pre-spec**. There is a waitlist and a set of design partners, not a downloadable
standard.

## Architecture & Key Patterns

- **Standardized driver layer.** One driver per device translates vendor-specific control
  — SDKs, COM scripting, scheduling files, GUI-only interfaces — into a common surface (S2, S3).
- **Two primitives.** Everything reduces to `read` (get a value, e.g. temperature) and
  `write` (set a value / issue a command). Vendor complexity lives below this line (S2, S3).
- **States and procedures.** Devices are presented as *states* (conditions: "plate at
  position 3", "sample at 25 °C") and *procedures* (operations: "aspirate", "shake") (S2).
- **Natural-language tags as first-class metadata.** Drivers carry plain-language
  descriptions of physical characteristics and constraints — arm mass, safety limits —
  knowledge that previously existed only in manuals or in an operator's head. From these,
  MHS generates reference files enumerating capabilities, tunable parameters and safety
  bounds (S2, S3).
- **Network discovery.** Devices and agents find each other in a standard format; no
  bespoke translator program per pairing (S2, S3).
- **Three interchangeable transports.** MCP, a CLI, and code files acting as APIs — an
  agent may use whichever fits, and orchestration across several devices is claimed to
  collapse to "a single line of code" (S2, S3).
- **Shared-memory state bus.** One reference implementation unifies device states and
  procedures in a shared memory dictionary, giving real-time cross-vendor state sharing (S2).
- **Model-agnostic by design.** Any harness speaking a standard protocol (MCP among them)
  can drive it; MCP is one transport, not the interface (S2, S3, S4).

## Notable Implementation Details

- **Safety limits bind below the agent.** Device-level limits (e.g. maximum laser power)
  are enforced by the driver and cannot be overridden by the model — a floor, not a prompt
  instruction (S2).
- **Structured hardware errors.** Drivers detect and report failures as structured data so
  the agent can choose autonomous recovery or a safe stop. Anthropic reports blocking six
  deliberately induced failure conditions (S2).
- **Human approval gates** are required for high-risk decisions, with real-time monitoring
  and recovery around them (S2).
- **Closed-loop tuning without per-step prompting.** Real-time state streaming lets the
  agent observe, adjust parameters and sequence dependent operations by itself (S2).
- **Tacit-knowledge capture is the actual novelty.** The read/write pair is unremarkable;
  encoding "what this machine physically is and must not do" as agent-legible metadata,
  next to the control surface, is the part existing lab standards do not do.

## Strengths

- **Integration cost collapse — the headline claim.** Genentech: weeks-to-months → "hours
  or minutes". University of Washington: six instruments connected in under a week.
  Carnegie Mellon: a complete driver in eight hours vs. several weeks for a typical vendor
  integration (S2).
- **Measured closed-loop wins.** QuEra laser relocking went from 58 % success at ~150 s per
  attempt to **99.3 % at 0.9–14 s** across 700 trials; PID tuning cut residual error 15.7 mV
  → 1.55 mV (~10×) over 363 experiments, with **zero lock losses over a 19-hour run** against
  an expert baseline losing lock ~1.6×/hour (S2).
- **Other reported results:** Carnegie Mellon dose–response ~3× faster with the agent
  independently rejecting saturated curves; Tetsuwan Scientific 17 % better precision
  prediction than manufacturer specs on held-out experiments; Genentech BCA assay flow
  rates autonomously optimized (water ~140 µL/s, BSA ~10 µL/s) (S2).
- **Serious partner bench.** Genentech, HHMI Janelia, UW Baker & Pinglay labs, Carnegie
  Mellon, QuEra, Tetsuwan Scientific; vendors AWS/Strands Robots, Automata, Danaher, Doosan
  Robotics, MBF Bioscience, QIAGEN, Tecan, Universal Robots, Hugging Face (LeRobot) and
  Raspberry Pi (S2, S4).
- **Right abstraction level.** States/procedures + NL tags + hard limits is a genuinely
  agent-shaped interface, not an RPC surface with a chat wrapper.

## Weaknesses / Limitations

- **The standard does not exist publicly.** No schema, no reference implementation, no
  version, no repository, no conformance suite — only a waitlist (S1). Nothing is
  implementable today.
- **Every number is self-reported by the standard's author**, drawn from design partners
  with an interest in the result. No independent replication, no published protocol or
  raw data (S2). Treat as directional.
- **Physical reasoning remains the weak link.** Anthropic states Claude learns the physical
  world from text and images, so spatial reasoning needs expert oversight. Concretely:
  the agent retried a failing operation identically when air bubbles were the cause (S2, S3).
- **Over-caution has a measured cost.** Overnight human-confirmation requests idled runs —
  the safety gate itself is a throughput problem (S3).
- **Purely mechanical devices are out of scope** — anything driven by a physical knob or
  switch has no programmable interface to wrap (S3).
- **Prior art is unaddressed in the public material.** Lab automation already has SiLA 2,
  AnIML, OPC UA and LADS; none of the sources reviewed explain how MHS relates to or
  interoperates with them. The Register frames it as a "plumbing spec" (S6).
- **Single-vendor governance.** "We will open-source it later" is intent, not a foundation,
  a working group, or an IPR policy — the trajectory MCP took, but not yet arrived.

## Visible vs Hidden Metrics

**Visible (advertised):**
- Integration time: weeks/months → hours (self-reported, 3 sites).
- Task success: 58 % → 99.3 % laser relock; ~10× PID error reduction; 3× faster assays;
  19 h unattended operation (self-reported, single partner each).
- Breadth: ~16 named partners across science, robotics and instrument vendors.
- Simplicity: two primitives; "orchestration via a single line of code".
- *None of it independently verified.* All numbers originate from S2, Anthropic's own post.

**Hidden (the costs an adopter inherits):**
- **Availability risk, today total** — you cannot adopt it; you can only join a waitlist and
  wait on someone else's timetable.
- **Spec churn.** A pre-1.0 standard under a single vendor's control will move; every early
  driver is rework.
- **Governance lock-in.** Model-agnostic in design, Anthropic-controlled in fact. Until
  there is a neutral body, adoption bets on one company's roadmap.
- **Safety burden transfers to you.** Device limits must be authored correctly per driver;
  a wrong bound is a broken machine or a ruined sample, and the preview exists precisely
  because those evaluation practices are *not yet written*.
- **Operational load.** Human-approval gates, real-time monitoring and recovery paths are
  staffing, not code — the overnight-confirmation stall is that bill arriving.
- **Standards fragmentation.** Adding MHS to a lab already on SiLA 2 / OPC UA means
  maintaining two control surfaces, not replacing one.
- **The abstraction leaks where it matters.** Two primitives do not fix a model that cannot
  reason about a bubble; the failure modes remaining are the physical ones.

**Weighing:** the visible wins are real in kind — a uniform agent-legible device surface
with hard safety floors is the right shape, and the QuEra closed-loop numbers are the
strongest evidence that agents can beat expert baselines on tuning tasks. But every hidden
cost is currently at maximum: no spec, no governance, no independent verification, and the
one unavoidable operational cost (human approval gates) is already documented as a
throughput drag. **For anyone not a design partner, the correct posture today is
"track the ideas, do not build on it".** The transferable value is architectural — states +
procedures, NL capability tags, driver-enforced limits agents cannot override, structured
hardware errors — and those patterns can be borrowed without waiting for the standard.

---

# AutoBot Comparison: MHS → AutoBot

**Scope note.** MHS governs *physical instruments*; AutoBot has no physical-device layer.
Grep across the tree for a serial/USB/GPIO/instrument path returns nothing — AutoBot's
"hardware" is compute accelerators (`autobot-backend/llm_shared/hardware.py`,
`autobot-npu-worker/`, OpenVINO NPU/GPU/CPU selection), a VNC-driven desktop
(`autobot-backend/api/vnc_*.py`), paired mobile devices
(`autobot-backend/models/mobile_device.py`), and browser/TTS workers. Adopting MHS itself
is out of scope. What transfers is its **interface doctrine**, applied to the actuation
surfaces AutoBot already drives.

## What We Can Adopt

### 1. Make declared limits actually bind — finish `MCPBridgeManifest.resource_limits`

- **Already-exists audit.** Declared at
  [`services/mcp_bridge_manifest.py:20`](../../autobot-backend/services/mcp_bridge_manifest.py#L20);
  echoed to the client at
  [`api/mcp_registry.py:552`](../../autobot-backend/api/mcp_registry.py#L552);
  shape-asserted at `tests/unit/api/test_mcp_plugin_discovery.py:36-45`. A tree-wide grep
  for `resource_limits` finds **no enforcement consumer for the manifest field** — the
  limits that actually bind come from a separate, env-var authority,
  [`services/mcp_isolation_config.py`](../../autobot-backend/services/mcp_isolation_config.py)
  `BridgePolicy` (`MCP_BRIDGE_CPU_LIMIT` / `MCP_BRIDGE_MEM_LIMIT_MB` /
  `MCP_BRIDGE_NOFILE_LIMIT`). A bridge can
  therefore *declare* a ceiling that nothing checks.
- **MHS parallel.** Its central safety property is that device-level limits live in the
  driver and the agent cannot override them (S2). Declared-and-unenforced is the failure
  mode that property exists to prevent.
- **Visible benefit:** a bridge's advertised ceiling becomes a real one; one answer to
  "what is this bridge allowed to consume?".
- **Hidden cost:** two limit authorities now exist and must be reconciled — declared
  manifest vs. env policy. Pick one as canonical or the drift returns under a new name.
- **Verdict: adopt** — and note this is *unwired existing work*, so it is a wire-in, not a
  new feature. **Effort: moderate.**

### 2. Capability descriptors that carry bounds and risk, not just names

- **Already-exists audit.** Four capability surfaces were read; none carries operating
  limits:
  - `ToolMetadata` — [`autobot_shared/tool_sdk/base.py:73-94`](../../autobot_shared/tool_sdk/base.py#L73-L94):
    `name`, `description`, `version`, `permission`, `tags`. No bounds, no risk grade.
  - `SelfCapabilitiesResponse` — [`api/schemas_agent.py:902-912`](../../autobot-backend/api/schemas_agent.py#L902-L912),
    served by [`api/self_capabilities.py`](../../autobot-backend/api/self_capabilities.py):
    a live route inventory with counts and tag groupings — no constraints, no danger grade.
  - `MCPBridgeManifest` — `features: List[str]`, a name list.
  - `Capability` / `TrustTier` — `autobot_shared/plugin_sdk/capabilities.py` (re-exported by
    [`plugin_sdk/capabilities.py`](../../autobot-backend/plugin_sdk/capabilities.py)):
    a permission axis, not a physical/operational one.
  - Risk vocabulary **does** exist — `CommandRisk` at
    [`autobot_shared/status_enums.py:183`](../../autobot_shared/status_enums.py#L183)
    (SAFE/MODERATE/HIGH/CRITICAL/DANGEROUS/FORBIDDEN, with `.blocks`) — but it grades
    *shell command strings*, not tools, routes or bridges.
- **Missing delta only:** no tool, endpoint or bridge tells the model its own operating
  bounds or risk grade. The model discovers *what exists*, never *how far it may go*.
- **Visible benefit:** the agent plans against declared limits instead of discovering them
  by tripping a guard — MHS's "reference file of capabilities, adjustable parameters and
  safety limits" (S2).
- **Hidden cost:** every descriptor becomes a thing that can go stale and lie. A wrong
  declared bound is worse than none, because the agent trusts it.
- **Verdict: adopt-with-conditions** — extend `ToolMetadata` with an existing risk grade
  (`CommandRisk`) plus optional bounds; **do not mint a new vocabulary** (core rules 2 and
  3). Condition: any declared bound must be enforced at the same call site that publishes
  it, or it repeats gap #1. **Effort: moderate.**

### 3. Structured failure that reaches the model

- **Already-exists audit.** `ErrorCategory` —
  [`autobot-backend/utils/error_boundaries/types.py:68-91`](../../autobot-backend/utils/error_boundaries/types.py#L68-L91)
  — has 9 system categories and 9 HTTP-aligned ones; **none is physical/device**.
  `RecoveryStrategy` (same file, `:94-102`) enumerates RETRY / FALLBACK /
  GRACEFUL_DEGRADATION / USER_INTERVENTION / SYSTEM_RESTART / IGNORE. But `classify_error`
  is consumed in exactly one place — [`agent_loop/loop.py:1916`](../../autobot-backend/agent_loop/loop.py#L1916)
  — to spend a per-severity **retry budget**. Meanwhile the model's own view of a failure
  is `ToolResult.error`, a bare string
  ([`tool_sdk/base.py:116`](../../autobot_shared/tool_sdk/base.py#L116)).
- **Missing delta:** AutoBot classifies errors *for the loop* and hands the *model* prose.
  MHS's drivers hand the agent structured error information so it can choose recovery or a
  safe stop (S2).
- **Visible benefit:** the agent distinguishes "retry is pointless" from "retry now" —
  directly the failure MHS documents, where Claude retried an operation identically because
  it could not tell that air bubbles, not timing, were the cause (S3).
- **Hidden cost:** a category on the wire is a contract; changing it later breaks prompts
  and any downstream consumer.
- **Verdict: adopt** the *structured-error-reaches-the-model* half (add `category` and
  `recovery` to `ToolResult`, populated from the existing `classify_error`). A `DEVICE`
  category is **rejected for now** — no physical device layer exists to raise it.
  **Effort: trivial to moderate.**

### 4. States vs. procedures for the desktop actuation surface

- **Already-exists audit.** VNC control is verb-only:
  [`api/vnc_humanization.py`](../../autobot-backend/api/vnc_humanization.py) provides
  `humanize_click_position`, variable typing speed and curved movement — actions, with no
  companion contract describing the desktop's *current declared state*. The agent reads
  state by looking at pixels (`components/vision/ScreenCaptureViewer`, screen capture) —
  inference, not declaration.
- **Missing delta:** no structured, readable state for a surface the agent actuates. MHS
  splits every device into *states* ("plate at position 3") and *procedures* ("aspirate"),
  which is what lets an agent sequence dependent operations without per-step prompting (S2).
- **Visible benefit:** dependent action sequencing and verification without a screenshot
  round-trip per step.
- **Hidden cost: high, and it is the deciding factor.** A declared state contract needs a
  producer that stays truthful under every failure mode; a stale desktop state is a
  confidently wrong agent driving a real screen. Pixels are slow but self-correcting.
- **Verdict: adopt-with-conditions, low priority** — worth it only for a bounded,
  reliably-observable subset (focused window, session lifecycle, connection state), never
  as a general "what is on screen" contract. **Effort: significant.**

## What We Already Do Better

| Area | AutoBot | Evidence | vs. MHS |
|---|---|---|---|
| Discovery that degrades safely | Credential-gated registries: absent capability returns an empty list, never raises | [`autobot_shared/credential_gated_registry.py`](../../autobot_shared/credential_gated_registry.py), [`integrations/capability_registry.py`](../../autobot-backend/integrations/capability_registry.py), `llm_shared/provider_registry.py`, `agent_loop/search/registry.py` | MHS publishes discovery; nothing on graceful degradation |
| Registry honesty | A failed fetch never reads as an empty fleet — `FleetSnapshot.source` labels the fallback | [`services/fleet_registry.py:14-27`](../../autobot-backend/services/fleet_registry.py#L14-L27) | Not a property MHS's material claims |
| Risk vocabulary | `CommandRisk` reconciles two forks, keeps `DANGEROUS` and `FORBIDDEN` as distinct *reasons* for one verdict, and forces `.blocks` over identity comparison | [`status_enums.py:183-208`](../../autobot_shared/status_enums.py#L183-L208) | MHS's published safety story is "limits the agent cannot override" — one axis |
| Approval as a state machine | Explicit legal transitions, WebSocket notification, comments, revision-request path | [`services/approval_gate_service.py:27-37`](../../autobot-backend/services/approval_gate_service.py#L27-L37), wired via [`api/approval_gates.py:33`](../../autobot-backend/api/approval_gates.py#L33) and `chat_workflow/compose_tool_handler.py:88` | MHS has "human approval for high-risk decisions" with no published lifecycle |
| Per-component isolation | Bridges run inprocess / subprocess / container with RLIMIT_CPU, RLIMIT_AS, RLIMIT_NOFILE and a restart ceiling | [`services/mcp_isolation_config.py`](../../autobot-backend/services/mcp_isolation_config.py) | MHS publishes nothing on sandboxing the driver itself |
| Capability revocation timing | Device capability decisions are deliberately **uncached** so a revocation takes effect on the next handshake | [`services/device_capabilities.py:11-17`](../../autobot-backend/services/device_capabilities.py#L11-L17) | Not addressed in MHS material |

## Gaps & Opportunities

Prioritised by impact to AutoBot.

1. **The approval-stall answer is half-built, and already tracked — not an MHS import.**
   MHS documents its sharpest operational cost:
   overnight human-confirmation requests idle a run (S3). AutoBot has the fix —
   [`services/remote_approval.py`](../../autobot-backend/services/remote_approval.py),
   [`services/remote_approval_routing.py`](../../autobot-backend/services/remote_approval_routing.py)
   and [`services/slack_approval_integration.py`](../../autobot-backend/services/slack_approval_integration.py)
   — but a tree-wide grep finds **only test callers and docstring mentions** for all three;
   no production import path reaches them. An approval today can only be answered by
   someone at the screen. This is **deliberately staged work, not dropped work**:
   `remote_approval.py`'s own header names delivery and the per-session routing flag as "the
   next change in the stack", and #14068 tracks the remaining halves, with #14677 (no approver
   identity, no replay protection in the remote-approval schema) as a blocker to close first.
   Listed here because the external material independently confirms the cost of leaving it
   unfinished — not because it was an undiscovered defect.
2. **Declared limits with no enforcement** (`MCPBridgeManifest.resource_limits`) — adopt
   item 1 above. Small, contained, closes a real honesty gap in the registry response.
3. **Structured failure to the model** — adopt item 3. Cheapest change with the most direct
   effect on agent recovery quality.
4. **Closed-loop parameter search is absent, and it is MHS's strongest published result.**
   QuEra PID tuning: 15.7 mV → 1.55 mV over 363 experiments; laser relock 58 % → 99.3 %
   over 700 trials (S2). This is an agent iterating against a *measurable objective*, and
   nothing about it is physical. AutoBot's nearest equivalent is workflow retry with
   budgets ([`services/workflow_automation/safety_limits.py`](../../autobot-backend/services/workflow_automation/safety_limits.py):
   step timeouts, token and cost ceilings) — retry, not search. The pattern ports directly
   to LLM parameter tuning, NPU dispatch tuning
   ([`autobot-npu-worker/workers/openvino_dispatch.py`](../../autobot-npu-worker/workers/openvino_dispatch.py))
   and hardware-backend selection ([`llm_shared/hardware.py`](../../autobot-backend/llm_shared/hardware.py),
   whose priority list is static). *Highest-upside idea in the source; entirely
   software-implementable.*
5. **No physical device layer** — correctly so. MHS's device categories (microscopes,
   centrifuges, pipette robots, spectrometers) have no counterpart in AutoBot and no
   demand. **Do not adopt.** Revisit only if AutoBot ever drives instrumented hardware.
6. **Natural-language capability tags as durable tacit knowledge** — MHS's genuine novelty
   is storing "what this machine is and must not do" next to the control surface, in
   language, so the model reads it. AutoBot's analogue would be operational constraints on
   fleet nodes and workers; today that knowledge lives in docs and operator heads. Lower
   priority than 1–4, but it is the idea most worth stealing conceptually.

## Specific Code/Files Affected

| File | Change |
|---|---|
| [`autobot-backend/services/mcp_bridge_manifest.py`](../../autobot-backend/services/mcp_bridge_manifest.py) + [`services/mcp_isolation_config.py`](../../autobot-backend/services/mcp_isolation_config.py) | Reconcile the two limit authorities; make the declared manifest ceiling the input to `BridgePolicy`, or drop the field |
| [`autobot_shared/tool_sdk/base.py`](../../autobot_shared/tool_sdk/base.py) | `ToolMetadata`: add a `CommandRisk` grade + optional declared bounds. `ToolResult`: add `category` / `recovery`, filled from `classify_error` |
| [`autobot_shared/tool_sdk/registry.py`](../../autobot_shared/tool_sdk/registry.py) | Surface the new metadata through `to_openapi_spec()` |
| [`autobot-backend/api/self_capabilities.py`](../../autobot-backend/api/self_capabilities.py) + [`api/schemas_agent.py`](../../autobot-backend/api/schemas_agent.py) | Carry per-route risk grade alongside the endpoint inventory |
| [`autobot-backend/services/remote_approval*.py`](../../autobot-backend/services/), [`services/slack_approval_integration.py`](../../autobot-backend/services/slack_approval_integration.py) | **Wire in** — give `approval_gate_service` an out-of-band routing path so an approval reaches a human who is not at the screen |
| [`autobot-backend/llm_shared/hardware.py`](../../autobot-backend/llm_shared/hardware.py), [`autobot-npu-worker/workers/openvino_dispatch.py`](../../autobot-npu-worker/workers/openvino_dispatch.py) | Candidate hosts for closed-loop measured tuning in place of the static priority list |

## Bottom Line

MHS is not adoptable — there is no spec — and its device domain is not AutoBot's. Its
*doctrine* is worth taking, in four parts: declared limits that bind, capability descriptors
that state their own bounds, structured failure the model can act on, and closed-loop tuning
against a measured objective. The first three map onto code AutoBot already has and only
partially finished; the fourth is absent and is the highest-upside idea in the source. A fifth
candidate — a declared state contract for the desktop actuation surface — is examined above and
**rejected on hidden cost**: a stale state contract is a confidently wrong agent driving a real
screen, where pixels are slow but self-correcting.

The most useful thing the source did was not supply a pattern at all. It independently confirms
the cost of an approval nobody can answer — a problem AutoBot has already diagnosed, half-built
and tracked in #14068. External corroboration of a known priority, rather than a new import.
