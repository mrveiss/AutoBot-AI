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

*Phase 2 (AutoBot comparison) not run — awaiting approval.*
