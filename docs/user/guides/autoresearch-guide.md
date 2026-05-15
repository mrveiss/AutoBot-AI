---
tags:
  - user-guide
  - autoresearch
  - experiments
aliases:
  - AutoResearch Guide
---

# AutoResearch User Guide

## 1. What is AutoResearch

AutoResearch is AutoBot's self-improving experiment loop. It runs structured
hypothesis-driven experiments against a language model's validation score,
records every result, and uses those results to generate better hypotheses for
subsequent runs. Over time the system accumulates distilled insights in
ChromaDB, which inform future hypothesis generation automatically through RAG.

**When to use it:**

- You want to find optimal hyperparameters for a fine-tuning run without manual
  grid search.
- You want to benchmark the effect of a code or prompt change on model quality.
- You want to let the system propose and test its own improvement ideas with
  minimal oversight.

AutoResearch is not a general-purpose task runner. It is focused on quantitative
model-quality improvements measured through the val_bpb (validation
bits-per-byte) metric. For general workflow automation use the Workflows feature
instead.

---

## 2. Prerequisites

**Role:** Admin role is required. All AutoResearch API endpoints enforce
`check_admin_permission`. Regular users can view experiment results in the
Workflow History view but cannot create or manage experiments.

**Resources AutoResearch uses:**

| Resource | Purpose |
|----------|---------|
| Redis (main database) | Experiment state, approval queues, human review queues, optimizer sessions |
| ChromaDB | Per-experiment vector index and distilled insights collection |
| LLM service | Hypothesis generation, LLM-judge scoring, prompt mutation |
| ExperimentRunner | Executes benchmark tasks for each experiment |

Ensure the backend services are healthy before starting experiments. Check
`GET /autoresearch/status` — it returns `running: false` and a `baseline_val_bpb`
value when the system is ready.

---

## 3. Getting Started

### 3.1 Navigate to the Experiment Dashboard

Go to `/experiments` in the AutoBot frontend. This route is only linked in the
admin navigation. You will see a stats header and three panels: Experiment
Timeline, Prompt Optimizer, and Insights.

### 3.2 Set a Baseline

Before running experiments AutoResearch needs a reference score to compare
improvements against. If you have an existing val_bpb from a known-good
checkpoint, set it:

```http
POST /autoresearch/experiments/baseline
Content-Type: application/json

{ "val_bpb": 2.41 }
```

If you skip this step the system uses a sentinel baseline of `1.0`, which means
improvement percentages will be relative to that value rather than your actual
model.

### 3.3 Create Your First Experiment

In the dashboard click **New Experiment**, or call the API directly:

```http
POST /autoresearch/experiments
Content-Type: application/json

{
  "hypothesis": "Reducing learning rate from 3e-4 to 1e-4 will improve val_bpb",
  "description": "Standard LR warmup schedule with cosine decay",
  "hyperparams": {
    "learning_rate": 1e-4,
    "warmup_steps": 500,
    "scheduler": "cosine"
  },
  "tags": ["learning_rate", "scheduler"]
}
```

The response returns an `id` and `state: "pending"` immediately. The experiment
is queued as a background task — the API call does not block.

**Field reference:**

| Field | Required | Notes |
|-------|----------|-------|
| `hypothesis` | No | Human-readable statement of what you expect to happen (max 1000 chars) |
| `description` | No | Longer rationale or methodology notes (max 5000 chars) |
| `code_diff` | No | Optional unified diff of any code changes being tested (max 50000 chars) |
| `hyperparams` | No | Dict of hyperparameter name to value |
| `tags` | No | Up to 20 string tags for filtering |

Only one experiment can run at a time. If the runner is already busy the API
returns HTTP 409. Wait for the current experiment to complete or call
`POST /autoresearch/cancel`.

### 3.4 Poll for Status

```http
GET /autoresearch/experiments/{experiment_id}
```

The `state` field progresses: `pending` → `running` → `completed` / `kept` /
`discarded` / `failed`. The dashboard polls automatically every 15 seconds.

---

## 4. Experiment Types

AutoResearch experiments are scored in three ways. The scoring method is
determined by how the experiment is created and whether the Prompt Optimizer
is active.

### 4.1 LLM-Judge Scoring

The LLM judge evaluates the output of a prompt variant against three criteria:
hypothesis clarity, specificity of proposed changes, and actionability. Each
criterion is rated 0-10 by the scoring LLM and normalized to a 0.0-1.0 score.

This is the default scorer for the built-in `autoresearch_hypothesis` prompt
optimization target and for any agent target you register without specifying a
scorer chain.

### 4.2 val_bpb Scoring

val_bpb (validation bits-per-byte) is the primary quality metric for
language model training experiments. Lower val_bpb indicates better model
compression and generalization.

The `ValBpbScorer` runs the experiment through the ExperimentRunner using the
prompt variant's output as the hypothesis, measures val_bpb improvement over
the stored baseline, and normalizes the score to 0.0-1.0. A positive score
means the variant improved on the baseline.

Use `scorer_chain: ["val_bpb"]` when registering optimization targets for
training-focused experiments.

### 4.3 Human Review

The `HumanReviewScorer` queues a variant for manual review. It pauses the
optimization loop and waits up to 300 seconds for a score submission via the
API. If no score is submitted within the timeout the variant is skipped.

Human review is typically the final stage in a multi-stage scorer chain, applied
only to the top-K candidates that passed automated filtering:

```json
{ "scorer_chain": ["llm_judge", "human_review"] }
```

Submit a score via:

```http
POST /autoresearch/prompt-optimizer/variants/{variant_id}/score?session_id={session_id}
Content-Type: application/json

{ "score": 8, "comment": "Clear hypothesis, actionable change" }
```

Scores are 0-10 integers. The `comment` field is optional but useful for the
knowledge synthesis step.

---

## 5. Running an Experiment

### 5.1 From Hypothesis to Result

The full lifecycle for a single experiment:

1. **Submit** — `POST /autoresearch/experiments` creates the experiment record
   and queues it as a background task.
2. **Pending** — The experiment waits in the queue if another experiment is
   running.
3. **Running** — ExperimentRunner executes the benchmark tasks defined by the
   hyperparams. Progress is logged; state transitions to `running`.
4. **Completed** — The runner finishes and records the raw val_bpb result.
5. **Evaluation** — The result is compared against the stored baseline.
   - If improvement exceeds the significance threshold and approval is required,
     state becomes `completed` and an approval request is created.
   - If improvement is below threshold or approval is not required, state
     transitions immediately to `kept` or `discarded`.
6. **Indexed** — The completed experiment is indexed in ChromaDB for future
   semantic search and insight synthesis.

### 5.2 Cancelling a Running Experiment

```http
POST /autoresearch/cancel
```

Returns `status: cancelled`. The in-progress experiment transitions to `failed`.

### 5.3 Concurrency Limit

Only one experiment runs at a time. Check `GET /autoresearch/status` before
submitting to avoid the 409 conflict error.

---

## 6. Interpreting Results

### 6.1 The Dashboard Stats Header

The stats header shows four counters:

| Counter | Meaning |
|---------|---------|
| Total Experiments | All experiments ever recorded |
| Kept | Experiments accepted as improvements |
| Discarded | Experiments rejected as regressions or neutral |
| Pending Approvals | Experiments awaiting human decision |

### 6.2 Understanding val_bpb

val_bpb is measured in bits per byte of validation text. Values typically range
from 1.0 (near-perfect compression) to 4.0+ (poor compression). A decrease in
val_bpb represents an improvement. AutoResearch reports improvement as an
absolute delta and a percentage relative to the baseline:

```
baseline:  2.41 val_bpb
experiment: 2.38 val_bpb
delta:      -0.03 (improvement of ~1.2%)
```

The `significant_improvement` threshold is configured in `AutoResearchConfig`.
Experiments that do not exceed this threshold are automatically discarded.

### 6.3 Experiment States

| State | Meaning |
|-------|---------|
| `pending` | Queued, not yet started |
| `running` | Actively executing |
| `completed` | Finished, awaiting approval decision |
| `kept` | Accepted as an improvement |
| `discarded` | Rejected — did not meet the improvement threshold |
| `failed` | Errored or cancelled before completion |

### 6.4 Filtering Experiments

The experiment list endpoint supports filtering by state:

```http
GET /autoresearch/experiments?state=kept&limit=20&offset=0
```

Valid state values: `pending`, `running`, `completed`, `kept`, `discarded`,
`failed`.

---

## 7. Approval Workflow

### 7.1 When Approval Is Required

An approval gate fires when an experiment achieves a "significant improvement"
over the baseline — meaning the val_bpb delta exceeds the configured threshold.
The idea is to give a human a final check before treating the change as
canonical.

When an approval is required:
- The experiment state is set to `completed` and held there.
- A record is written to Redis under `autoresearch:approval:pending:{session}:{experiment}`.
- A notification is dispatched via the notification service (Slack, email, or
  webhook depending on your configuration).
- The pending approval counter on the dashboard increments.

### 7.2 Reviewing Pending Approvals

List all pending approvals:

```http
GET /autoresearch/approvals/pending
```

Each entry includes the experiment ID, session ID, the measured improvement, and
the hyperparams that produced it.

### 7.3 Approving or Rejecting

```http
POST /autoresearch/approvals/{session_id}/{experiment_id}
Content-Type: application/json

{ "decision": "approved" }
```

Valid values for `decision`: `approved` or `rejected`.

- **Approved**: The experiment is marked `kept` and its results are treated as
  the new baseline candidate for future experiments.
- **Rejected**: The experiment is marked `discarded` and the improvement is not
  adopted.

In the dashboard, pending approvals appear as ApprovalCards inline in the
Experiment Timeline. Each card shows the before/after val_bpb, the hyperparams
diff, and approve/reject buttons.

### 7.4 What "Significant Improvement" Means

The threshold is set in `AutoResearchConfig.significant_improvement_threshold`
(default: `0.01`, representing a 1% relative improvement). You can adjust this
in your environment configuration. Setting it too low generates excessive
approvals; setting it too high risks missing genuine improvements.

---

## 8. Prompt Optimization

The Prompt Optimizer improves the system prompts used by AutoBot's agents by
running a mutation-and-scoring loop over prompt variants.

### 8.1 Using the PromptOptimizerPanel

The PromptOptimizerPanel in the dashboard exposes two main actions:

- **Start Optimization** — select an agent target and the maximum number of
  rounds (1-10), then click Start.
- **Cancel** — halts the current session after the active round finishes.

The panel displays the current session status, the best variant found so far,
and a table of all evaluated variants with their scores.

### 8.2 Registered Targets

The `autoresearch_hypothesis` target is pre-registered at startup. It optimizes
the system prompt used by the hypothesis-generation agent and scores variants
using the LLM judge.

List all registered targets:

```http
GET /autoresearch/prompt-optimizer/targets
```

### 8.3 Registering a Custom Target via API

For agents that use the default LLM-based benchmark you can register at runtime:

```http
POST /autoresearch/prompt-optimizer/register
Content-Type: application/json

{
  "agent_name": "my_agent",
  "current_prompt": "You are a helpful assistant...",
  "scorer_chain": ["llm_judge", "human_review"],
  "mutation_count": 5,
  "top_k": 2
}
```

Agents requiring a custom benchmark function must register programmatically via
`PromptOptimizer.register_optimization_target()` in Python — the API endpoint
covers the common case only.

### 8.4 Scoring Variants

Each optimization round generates `mutation_count` prompt variants, runs them
through the benchmark, then scores them through the scorer chain. The top-K
scoring variants from the first scorer are passed to the next scorer in the
chain. The variant with the highest final score becomes the new baseline for the
next round.

### 8.5 Starting an Optimization Run

```http
POST /autoresearch/prompt-optimizer/start
Content-Type: application/json

{ "agent_name": "autoresearch_hypothesis", "max_rounds": 3 }
```

Poll the status endpoint to track progress:

```http
GET /autoresearch/prompt-optimizer/status
```

When the session completes the `best_variant` field contains the winning prompt
text and its score. Applying the winner to your agent requires a code change to
the agent's system prompt — the optimizer does not automatically deploy prompts.

### 8.6 Retrieving Variants After a Session

```http
GET /autoresearch/prompt-optimizer/variants/{session_id}
```

Returns all variants with scores, comments, and parent IDs. Variants are stored
in Redis for 24 hours after session completion.

---

## 9. Insights and Knowledge Synthesis

### 9.1 How Insights Are Generated

After an experiment session completes, the KnowledgeSynthesizer queries all
experiments in that session and sends them to the LLM with a structured prompt.
The LLM extracts patterns — for example, "Dropout below 0.1 consistently
degrades val_bpb across learning rates" — and returns them as structured
`ExperimentInsight` objects.

Insights are stored in the `autoresearch_insights` ChromaDB collection with
confidence scores derived from the number of supporting experiments.

### 9.2 Browsing Insights

The InsightsPanel in the dashboard lists insights sorted by confidence. Each
insight shows:

- The insight statement
- Confidence score (0.0-1.0)
- Related hyperparameters
- Number of supporting experiments
- Synthesis timestamp

Filter by minimum confidence using the slider or the API:

```http
GET /autoresearch/insights?min_confidence=0.7&limit=20
```

### 9.3 Semantic Search

```http
GET /autoresearch/insights/search?q=learning+rate+warmup&limit=5
```

Uses ChromaDB embedding search to find semantically related insights.

### 9.4 Manual Synthesis Trigger

Synthesis runs automatically after session completion. To re-synthesize for an
existing session (for example, after adding more experiments to it):

```http
POST /autoresearch/insights/synthesize
Content-Type: application/json

{ "session_id": "session-abc123" }
```

### 9.5 RAG Integration

When the AutoResearch hypothesis agent generates a new hypothesis, it queries
the insights collection for relevant context and injects the top-K findings into
the reasoning chain. This means later experiments benefit from patterns
discovered in earlier sessions without any manual intervention.

---

## 10. Best Practices

**Experiment scope.** Each experiment should change one variable at a time.
Testing five hyperparameters simultaneously makes it impossible to attribute
improvements to a specific change. Use the `tags` field to group related
experiments.

**Baseline accuracy.** Set an accurate baseline before starting a session.
A misleading baseline causes the significance threshold calculation to fire on
noise or miss genuine improvements. Re-set the baseline whenever you switch to a
different model checkpoint or data distribution.

**Iteration budget.** Three to five rounds of optimization typically saturate
the improvement signal for a given prompt target. More rounds increase cost with
diminishing returns. Start with `max_rounds: 3`.

**Avoid overfitting.** val_bpb improvements on a narrow benchmark set may not
generalize. After a series of `kept` results, validate the adopted hyperparams
on a held-out evaluation set before committing them to production training runs.

**Scorer chain selection.** Use `val_bpb` when you have a meaningful baseline
and want objective scoring. Use `llm_judge` for prompt quality where there is no
numeric ground truth. Reserve `human_review` for top-K final candidates only —
do not put it first in the chain or you will be asked to score every generated
variant manually.

**Tag consistently.** Consistent tagging (e.g., `learning_rate`, `dropout`,
`batch_size`) makes filtering and insight synthesis more accurate, because the
synthesizer uses the enriched metadata including tags when extracting patterns.

---

## 11. Troubleshooting

### Experiment stuck in "running" state

The runner may have crashed without updating the state. Check
`GET /autoresearch/status` — if `running: true` but no progress has been made
for several minutes, call `POST /autoresearch/cancel` to reset the runner.

Backend errors during experiment execution are logged at WARNING level.
Check `/var/log/autobot/backend-error.log` for tracebacks.

### Approval never fires

Approval notifications require the notification service to be configured. If
you see `completed` experiments that never appear in the pending approvals list,
check:

1. That `GET /autoresearch/approvals/pending` returns them (the issue may be
   display-only).
2. That the notification service has an `approval_needed` event handler
   configured for your channel (Slack, email, or webhook).
3. That the experiment's val_bpb improvement actually exceeded the significance
   threshold. If it did not, the experiment transitions directly to `discarded`
   without creating an approval request.

### Cost runaway

Each experiment invocation calls the LLM service. With prompt optimization
enabled (`mutation_count: 5`, `max_rounds: 10`) a single session makes up to
50 benchmark calls plus scoring calls. To limit costs:

- Set `max_rounds` to 3 unless you have a specific reason for more.
- Keep `mutation_count` at 5 (default).
- Use `val_bpb` scorer instead of `llm_judge` for training experiments — it does
  not make an additional LLM call for scoring.
- Monitor costs with the Usage Metering dashboard at `/usage`.

### Human review timeout

The `HumanReviewScorer` waits 300 seconds by default. If you do not submit a
score within that window the variant is skipped (not failed). The optimization
loop continues with the remaining variants. If you are consistently missing the
window, increase the timeout in `AutoResearchConfig.human_review_timeout_seconds`
or remove `human_review` from the scorer chain for unattended runs.

### Optimization session 409 conflict

Only one optimization session can run at a time. If you see
`HTTP 409 Optimization already running`, call
`POST /autoresearch/prompt-optimizer/cancel` first, then retry. If the status
endpoint returns `running: false` but start still returns 409, restart the
backend service to clear the stale in-memory state.
