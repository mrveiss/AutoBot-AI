# Research: encoder-based typed decision head ("System 1" classifier)

Status: Phase 1 and Phase 2 complete (2026-10-20); filed as #18985–#18990.
Related prior research: `docs/research/llm-gateway-signal-driven-routing.md`,
`docs/research/confidence-gated-decision-loop-harness.md`.

## Source Analysis: an open-source non-autoregressive decision engine (Apache-2.0)

### What It Is
A Python library plus released checkpoints that answer typed questions about a piece of text
in a single encoder forward pass instead of generating tokens. Three question types:
`choice` (pick one label), `score` (ordinal level, expected value) and a boolean type (P(true) for a
statement). One call can ask many questions about one state; the state may be a string, dict
or list. Ships three checkpoints (an English large encoder, a multilingual base encoder, and a
variant fine-tuned on one benchmark), a script/language router that picks a checkpoint per
request, an HTTP server, an MCP stdio server, ONNX export, and SDKs in five other languages.
Roughly one month old, very fast-moving (releases in the 0.4.x line), heavily documented, with
an unusually candid "honest limits" section. The star count is very high for a one-month-old
repo and was not treated as evidence of anything.

### Architecture & Key Patterns
- **Model:** a pretrained bidirectional encoder → add a question-type embedding → 2 extra
  transformer layers ("head") → gather hidden states at one marker token per option → small
  MLP scorer → one logit per option → softmax. A second small "act" head reads pooled CLS +
  (top-1 prob, top-1 − top-2 margin, normalised entropy, option count) and emits a learned
  act/abstain signal.
- **Sequence layout:** a token budget split between a question "head" (instructions + rendered
  options, capped by `head_max_len`) and the serialised state. An optional "parallel" layout
  gives every option the same positions and masks options from each other so logits are
  permutation-equivariant.
- **Training:** reinforcement-style objective rewarding a *strictly proper scoring rule*
  (log score + spherical score, minus ranked probability score for ordinal questions), with
  TD(λ) targets for multi-turn trajectories. Distilled from a teacher model's distributions.
- **Calibration:** per-(question type, option-count bucket) temperatures, fit on held-out
  data; clamped to [0.5, 5.0] at load with a warning.
- **Router:** pure-Python Unicode script profiling + Latin-language heuristics (diacritic rate,
  word lists) decides English vs multilingual checkpoint in <1 ms; returns a `reason` and the
  detection evidence; LRU keeps two checkpoints resident; callers can plug in their own
  language-ID callable.
- **Extension surface:** a hook registry (`on_predict_start/end`, `on_route`, `on_load`,
  `on_evict`, `on_error`); a start hook may rewrite input or short-circuit with a cached answer.
- **Schema front-end:** a JSON Schema or pydantic model is compiled into typed questions
  (enum → choice, bounded int → score, boolean → yes/no) and the answers projected back.
- Tech: PyTorch, Hugging Face transformers encoders, optional custom GPU kernels,
  `torch.compile`/AOTI, ONNX Runtime.

### Notable Implementation Details
- **Opt-in abstention with an explicit tri-state.** `min_confidence` (scalar or per-bucket map
  over 12 keys = 3 types × 4 option bands) gates on `max(p)`, not entropy. When a gate runs,
  every answer carries `abstention ∈ {passed, abstained, unevaluated}` plus the threshold used,
  so a log distinguishes "gate cleared" from "no gate ran" from "gate could not decide". With
  no gate, output is byte-identical to before. Thresholds are *fit* from held-out records by
  a provided function, not picked.
- **Option-position bias measured and mitigated.** With five identical options the logits
  vary by ~3.6 by position alone. `option_order` lets a caller permute presentation and average
  across rotations in one forward pass; probabilities always come back in the caller's order.
- **Defensive numerics documented in code:** `ece_score` refuses `bins < 1` because it would
  silently return a perfect 0.0 ECE; temperature clamp warns instead of failing.
- **Token-budget arithmetic published honestly:** shows `max_len − head_max_len` is wrong in
  both directions and gives the real formula, including where many-option heads overflow.

### Strengths
- Latency: ~33–40 ms per call on a T4 GPU for *all* questions at once; batching gives 1.6–3.6×.
- Many decisions per pass amortise cost — ideal for triage/guard/route fan-out.
- Calibration and abstention treated as first-class, observable policy.
- Fully local, no hosted dependency (an explicit project rule).
- Router returns its reasoning, not just a choice.

### Weaknesses / Limitations
- **Near chance zero-shot** on its own headline benchmark (0.36 / 0.35 vs 0.318 random,
  0.461 majority). The 0.766 figure is a checkpoint fine-tuned on that benchmark's training
  split. It is a base to fine-tune, not a drop-in classifier.
- Both base checkpoints are over-confident as shipped; the multilingual one ships with no fitted
  temperatures.
- Fails on negation in documented cases (selected "cancel_account" for negated requests, one at
  p≈0.9998).
- Weak on high-cardinality choices (0.425 on a 77-label intent set vs 0.870 for a closed API);
  options share a fixed token budget.
- Boolean-word labels in `choice` questions confuse it.
- English checkpoint collapses on non-Latin scripts while staying confident (0.000 accuracy at
  0.952 confidence on one script) — the router exists to hide this.
- Fine-tuning is 4–5 h on 2×T4 for ~30k questions.

### Visible vs Hidden Metrics
- **Visible (all self-reported, none independently verified here):** 33 ms latency; 48/51
  languages usable; beats a closed API on 3 of 4 public tasks; ECE 0.081 after temperature
  fitting; Apache-2.0, $0 self-hosted.
- **Hidden:**
  - A torch + transformers + ~0.4–1.5 GB checkpoint dependency per resident model, plus GPU
    memory to stay at the advertised latency (CPU numbers are much slower).
  - Value requires *our own* labelled data, a fine-tuning run, and a held-out calibration fit
    per task — an ongoing ML-ops loop (data, retrain, recalibrate, re-threshold on every
    checkpoint or dtype change; the README states thresholds shift with bf16 autocast).
  - Upstream churn: one-month-old project on a rapid release cadence; pinning and revalidating
    on each bump is mandatory, and model revisions must be pinned (our own HF pinning rule).
  - Silent-failure modes: confident wrong answers on negation and out-of-script input.
- **Weighing:** for a team that already has labelled decisions and a calibration harness, the
  hidden costs buy a large latency and cost win on high-volume, low-cardinality decisions. For
  zero-shot use the visible wins mostly evaporate — an LLM call is slower but far more accurate
  out of the box. The transferable value is the *patterns* (typed-question contract, proper
  scoring, observable abstention, position-bias control), which carry none of the model's
  hidden costs.

## AutoBot Comparison: the reference work → AutoBot

Audit base: `origin/main` @ `cc6a777633`, 2026-10-20. Key finding up front: AutoBot already has
the reference work's core contract. `autobot-backend/llm_shared/decisions.py` (#17308) is a
`decide(state, questions)` seam with the same three primitives (`ChoiceQuestion`,
`ScoreQuestion`, `BooleanQuestion`), schema-validated replies that raise instead of guessing,
a pluggable backend registry, and an honest `Calibration.SELF_REPORTED` tag. What remains is
the *measurement and gating* layer around that seam.

### What We Can Adopt

#### 1. An unparsable confidence must be "unevaluated", never a default — *adopt, trivial (defect)*
- **Audit:** `agent_loop/think_tool.py:417-429` `_extract_confidence` returns `0.7` when the
  section is missing or unparsable; `agent_loop/loop.py:1875-1884` abstains only when the last
  `confidence_window` (3, `types.py:251`) steps are all below `min_confidence_floor` (0.3).
  A model that never states a confidence therefore reads as 0.7 and can never trigger
  abstention. No issue found (`gh issue list --search "think_tool confidence default 0.7"`).
- **Visible:** the abstention gate stops being silently disabled by a format slip.
- **Hidden:** none material; `ThinkResult.confidence` becomes `Optional[float]` and consumers
  must handle `None`.
- **Verdict:** adopt. Same shape as the reference work's `unevaluated` state.

#### 2. Record every gate's outcome, not only its firing — *adopt, trivial–moderate*
- **Audit:** the agent loop records `_abstained` / `result["abstained"]=True` and an
  `agent_abstained` event (`loop.py:368-382`, `:2037-2038`, `events/event_types.py:26`); a
  sweep for a passed/ran record found none. `pre_action_verifier_guard.py:513` `_log_result`
  logs the verifier outcome but its thresholds (`:71-90`) are not echoed per decision (not
  read in full).
- **Delta:** a tri-state `gate_outcome ∈ {passed, abstained, unevaluated}` plus the threshold
  applied, on agent-loop results and on `DecisionAnswer` consumers that threshold
  (`agents/ac_verifier.py`, `services/claim_verifier.py`).
- **Visible:** logs can separate "gate cleared" from "no gate ran" from "gate could not decide".
- **Hidden:** one more field per result and an event-schema change (EVENT_STATE_DOCTRINE).
- **Verdict:** adopt. Pairs with honesty umbrella #17259.

#### 3. Real calibration metrics in the decision-backend benchmark — *adopt, moderate*
- **Audit:** `scripts/benchmark_decision_backends.py:19-23` measures "calibration" as mean
  reported probability on right vs wrong cases. A sweep for ECE / Brier / temperature scaling /
  reliability found nothing in `*.py` (excluding venvs).
- **Delta:** ECE (refusing `bins < 1`, which would return a perfect 0.0) and Brier score, split
  by (question type × option-count band), as the evidence that promotes an answer from
  `SELF_REPORTED` to `MEASURED`.
- **Visible:** the promotion criterion in `decisions.py`'s docstring becomes a number.
- **Hidden:** needs a labelled sample per decision site; still runs real model calls.
- **Verdict:** adopt. Prerequisite for item 4 and for `confidence-gated-decision-loop-harness.md`
  item 3.

#### 4. Fitted, per-bucket thresholds instead of hand-picked ones — *adopt-with-conditions, moderate*
- **Audit:** verifier thresholds are env defaults (`pre_action_verifier_guard.py:71-90`: 0.5 /
  0.6), abstention floor 0.3 (`types.py:249-250`); none are fitted.
- **Visible:** thresholds that mean a measured accuracy at a given coverage.
- **Hidden:** a refit on every backend/model/quantisation change; meaningless on self-reported
  LLM probabilities until item 3 shows they carry information.
- **Verdict:** adopt-with-conditions — blocked on item 3 showing a backend's probabilities
  separate right from wrong.

#### 5. Option-order control on `ChoiceQuestion` — *adopt-with-conditions, moderate*
- **Audit:** no option shuffling or permutation averaging anywhere in `autobot-backend`
  (searched `random.shuffle|permut|position.bias|swap.*order`); `ChoiceQuestion.describe()`
  (`decisions.py:~127`) always lists options in declaration order; the judges in
  `judges/*.py` do not rotate either.
- **Delta:** an optional `option_order` on `ChoiceQuestion`, probabilities mapped back to the
  caller's order, plus a benchmark probe with identical-text options to measure the bias.
- **Visible:** removes a position effect the reference work measured at ~3.6 logits.
- **Hidden:** for an LLM backend each extra rotation is a full extra call (the reference work
  gets rotations free inside one encoder pass); 2–3× cost on rotated sites.
- **Verdict:** adopt-with-conditions — add the probe first; rotate only at sites where it
  measures a bias.

### Rejected by hidden metrics
- **A local encoder decision backend** (register via `register_decision_backend`): the visible
  win is ~35 ms vs a local LLM call, but the base checkpoints are near chance zero-shot; value
  needs a labelled corpus per site, a multi-hour fine-tune, a calibration refit per release,
  torch + GPU memory, and pinning against a one-month-old fast-moving upstream. Revisit only
  if item 3 yields a labelled corpus large enough to fine-tune on.
- **A model-based prompt-injection guard:** `decisions.py:55-70` records a ruling that a
  steerable model is the wrong direction for injection detection and the pre-action verifier,
  enforced by `llm_shared/decisions_exclusions_test.py`. Not re-proposed.
- **Unicode-script language routing:** no consumer — no per-language model fork exists to
  route between; voice already uses `lingua` (`voice_processing/language_detection.py`).

### What We Already Do Better
- **Malformed answers raise** (`decisions.py` via `validated_llm.complete_validated`); no path
  turns an unreadable reply into an answer.
- **An explicit do-not-use list with a test** (`decisions_exclusions_test.py`) — the
  reference work offers guard/router presets on a model it documents as over-confident and
  negation-blind.
- **Model provenance:** `autobot_shared/pinned_model_registry.py` pins a 40-hex revision *and*
  SHA-256 of the weight files; the reference work pins revisions/digests via env.
- **Honest calibration labelling by type** (`Calibration` enum) rather than prose caveats.

### Gaps & Opportunities (by impact)
1. Item 1 — a live defect disabling abstention on format drift.
2. Item 3 — unblocks every probability-consuming decision.
3. Item 2 — observability of every gate.
4. Items 4, 5 — conditional on 3.

### Specific Code/Files Affected
| Item | File | Change |
|---|---|---|
| 1 | `autobot-backend/agent_loop/think_tool.py`, `agent_loop/loop.py`, `agent_loop/types.py` | `None` instead of 0.7; abstention treats `None` as unevaluated |
| 2 | `agent_loop/loop.py`, `events/event_types.py`, `agents/ac_verifier.py`, `services/claim_verifier.py` | tri-state gate outcome + threshold echo |
| 3 | `scripts/benchmark_decision_backends.py` | ECE + Brier per type × option band |
| 4 | `autobot_shared/pre_action_verifier_guard.py`, `agent_loop/types.py` | thresholds from a fitted map |
| 5 | `autobot-backend/llm_shared/decisions.py` | `option_order` on `ChoiceQuestion`; bias probe in benchmark |

## Filed (2026-10-20)
| Item | Issue | Relationship |
|---|---|---|
| 1. Unparsed confidence defaults to 0.7 | #18985 | sub-issue of #17259 |
| Umbrella: decision confidence | #18986 | sub-issue of #17259 |
| 2. Gate outcome tri-state | #18987 | sub-issue of #18986 |
| 3. ECE + Brier in benchmark | #18988 | sub-issue of #18986 |
| 4. Fitted thresholds | #18989 | sub-issue of #18986, blocked by #18988 |
| 5. Option-order control | #18990 | sub-issue of #18986, blocked by #18988 |

## Linked issues

Issues this research produced or is the analysis for (#18967). Each one links back to this document.

- #18985 — Unparsed confidence defaults to 0.7
- #18986 — Umbrella: decision confidence
- #18987 — Gate outcome tri-state
- #18988 — ECE + Brier in benchmark
- #18989 — Fitted thresholds
- #18990 — Option-order control
