# AutoResearch M3: Self-Improvement + Frontend Dashboard

**Issue:** #2600 (child of #1440)
**Date:** 2026-04-01
**Dependencies:** M1 (#2597, closed), M2 (#2599, closed)
**Priority:** Backend first, then frontend

---

## Summary

Build the self-improvement layer for AutoResearch: a generic prompt optimizer that
mutates agent prompts, benchmarks them via pluggable scorers, and keeps/discards
based on improvement. Enrich the existing ChromaDB experiment index and add a
distilled insights collection for RAG-informed future experiments. Expose
everything through new API endpoints and a Vue 3 frontend dashboard with inline
approval UI and notification integration.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Architecture | Layered services (B) | Matches existing codebase patterns; testable in isolation |
| Prompt scoring | Hybrid (LLM-judge + human review) | Automated bulk filtering with human quality gate for top candidates |
| Knowledge indexing | Enriched per-experiment + distilled insights | Raw data for search + synthesized lessons for hypothesis generation |
| Dashboard placement | Admin page + workflow integration | Full dashboard for admins; experiment results in workflow view for all users |
| Approval UX | Inline dashboard + notifications | Active monitoring + async awareness |
| Delivery order | Backend first | Prompt optimizer + knowledge indexer fully working before frontend |

---

## 1. Prompt Optimizer

### 1.1 Scorer Interface

```python
# services/autoresearch/scorers.py

class ScorerResult:
    score: float            # normalized 0.0-1.0
    raw_score: Any          # scorer-specific (val_bpb, 0-10 rating, etc.)
    metadata: dict          # extra context
    scorer_name: str

class PromptScorer(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def score(self, prompt_output: str, context: dict) -> ScorerResult: ...
```

### 1.2 Concrete Scorers

**`ValBpbScorer`** — For AutoResearch hypothesis optimization.
- Runs an experiment via `ExperimentRunner` using the prompt variant's output as the hypothesis
- Score = normalized val_bpb improvement over baseline (higher = better)
- Context: hyperparams, session info

**`LLMJudgeScorer`** — For general agent prompt optimization.
- Sends prompt output + evaluation criteria to a scoring LLM via `LLMService`
- Returns 0-10 quality rating, normalized to 0.0-1.0
- Criteria are configurable per target (relevance, specificity, actionability, etc.)

**`HumanReviewScorer`** — For top candidates after automated filtering.
- Queues variant in Redis (`autoresearch:prompt_review:pending:{session_id}:{variant_id}`)
- Polls for human score submission via API endpoint
- Configurable timeout (default 300s), returns None on timeout (variant skipped)

### 1.3 Optimization Loop

```python
# services/autoresearch/prompt_optimizer.py

@dataclass
class PromptOptTarget:
    agent_name: str           # e.g., "autoresearch_hypothesis"
    current_prompt: str       # template to optimize
    scorer_chain: list[str]   # e.g., ["llm_judge", "human_review"] or ["val_bpb"]
    benchmark_fn: Callable    # produces output from a prompt variant
    mutation_count: int = 5   # variants per round
    top_k: int = 2            # candidates passed to next scorer in chain

@dataclass
class OptimizationSession:
    id: str
    target: PromptOptTarget
    status: str               # pending | running | completed | cancelled | failed
    rounds_completed: int
    best_variant: Optional[PromptVariant]
    all_variants: list[PromptVariant]
    started_at: Optional[float]
    completed_at: Optional[float]

class PromptOptimizer:
    def __init__(self, config, store, scorers: dict[str, PromptScorer]): ...

    async def optimize(self, target: PromptOptTarget, max_rounds: int = 3) -> OptimizationSession:
        """
        For each round:
          1. Mutate current best prompt into N variants (via LLM)
          2. Run each variant through benchmark_fn to get output
          3. Score all variants via first scorer in chain (fast filter)
          4. Pass top-K to next scorer in chain (deeper evaluation)
          5. If best variant improves over baseline -> KEEP, update baseline
          6. Persist all results to ExperimentStore
        """

    def _mutate_prompt(self, base_prompt: str, n: int) -> list[str]:
        """Use LLM to generate N prompt variants via structured mutation strategies."""

    def cancel(self) -> None: ...
```

### 1.4 Agent Registration

AutoResearchAgent registers as the first optimization target:

```python
# In auto_research_agent.py
target = PromptOptTarget(
    agent_name="autoresearch_hypothesis",
    current_prompt=self._hypothesis_prompt_template,
    scorer_chain=["val_bpb"],
    benchmark_fn=self._generate_hypothesis_from_prompt,
)
```

Future agents register similarly with their own scorer chains (typically `["llm_judge", "human_review"]`).

### 1.5 Files

- `autobot-backend/services/autoresearch/prompt_optimizer.py` — optimizer, session, target, variant models, optimization loop
- `autobot-backend/services/autoresearch/scorers.py` — scorer interface + 3 concrete scorers

---

## 2. Knowledge Synthesizer

### 2.1 Enhanced Per-Experiment Indexing

Modify `ExperimentStore._build_document()` and `_build_metadata()` to include:

- Full hyperparams dict (not just result metrics)
- Search themes from the hypothesis
- Session context: iteration number, prior results trend direction
- Prompt variant ID (when optimizer is active)
- Explicit comparison text: "learning_rate 3e-4 → 1e-4: val_bpb improved by 0.03 (2.3%)"

This is a non-breaking change — existing experiments get the current minimal document, new experiments get the enriched version.

### 2.2 Distilled Insights Collection

```python
# services/autoresearch/knowledge_synthesizer.py

@dataclass
class ExperimentInsight:
    id: str
    statement: str              # "Dropout < 0.1 degrades val_bpb consistently"
    confidence: float           # 0.0-1.0, based on supporting experiment count
    supporting_experiments: list[str]  # experiment IDs
    related_hyperparams: list[str]     # ["dropout", "weight_decay"]
    synthesized_at: float
    session_id: Optional[str]

class KnowledgeSynthesizer:
    INSIGHTS_COLLECTION = "autoresearch_insights"

    def __init__(self, config, store, llm_service): ...

    async def synthesize_session(self, session_id: str) -> list[ExperimentInsight]:
        """
        Called after ExperimentSession completes:
          1. Query per-experiment collection for all experiments in session
          2. Send to LLM with structured prompt to extract patterns
          3. Parse LLM output into ExperimentInsight objects
          4. Upsert insights into autoresearch_insights collection
          5. Return generated insights
        """

    async def query_insights(self, query: str, limit: int = 5) -> list[ExperimentInsight]:
        """Semantic search over distilled insights."""

    async def get_relevant_context(self, topic: str) -> str:
        """
        Build RAG context string for hypothesis generation:
          - Top-K relevant insights
          - Formatted as actionable guidance
        """
```

### 2.3 RAG Integration with Hypothesis Generator

`AutoResearchAgent._generate_hypothesis()` gains a new step before theme-to-hyperparams mapping:

```python
# Query insights for relevant prior findings
insights_context = await self.synthesizer.get_relevant_context(session.topic)
# Inject into hypothesis rationale so future experiments learn from the past
```

This augments (not replaces) the existing rule-based logic — insights provide additional context, theme matching still drives hyperparameter selection.

### 2.4 Files

- `autobot-backend/services/autoresearch/knowledge_synthesizer.py` — synthesizer + insight model
- Modifications to `store.py` — enriched `_build_document()` / `_build_metadata()`
- Modifications to `auto_research_agent.py` — inject synthesizer, call after session completes, use insights in hypothesis generation

---

## 3. Backend API Extensions

All endpoints under the existing `/autoresearch` router, requiring admin auth.

### 3.1 Prompt Optimizer Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/prompt-optimizer/start` | Start optimization for a registered target |
| GET | `/prompt-optimizer/status` | Current optimization session status |
| POST | `/prompt-optimizer/cancel` | Cancel running optimization |
| GET | `/prompt-optimizer/variants/{session_id}` | List variants with scores |
| POST | `/prompt-optimizer/variants/{variant_id}/score` | Submit human score |

### 3.2 Approval Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/approvals/pending` | List pending approval requests |
| POST | `/approvals/{session_id}/{experiment_id}` | Submit approve/reject decision |

### 3.3 Knowledge Insights Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/insights` | List insights (paginated, filterable by confidence) |
| GET | `/insights/search` | Semantic search over insights |
| POST | `/insights/synthesize` | Manually trigger synthesis for a session |

### 3.4 Notification Integration

When `ApprovalGate.request_approval()` fires, also dispatch via the existing notification service using the `approval_needed` event type. This hooks into per-workflow notification config (#3139) so operators receive Slack/email/webhook alerts for significant improvements.

### 3.5 Files

- Modifications to `autobot-backend/services/autoresearch/routes.py` — new endpoints
- Small integration in `auto_research_agent.py` — fire notification on approval request

---

## 4. Frontend

### 4.1 Composable

```typescript
// composables/useAutoResearch.ts
// Built on useAsyncOperation + useApi patterns

interface UseAutoResearch {
  // Experiment data
  experiments: Ref<Experiment[]>
  stats: Ref<ExperimentStats | null>
  loading: Ref<boolean>
  error: Ref<string | null>

  // Actions
  fetchExperiments(params?: { limit?: number; offset?: number; state?: string }): Promise<void>
  fetchStats(): Promise<void>

  // Prompt optimizer
  optimizerStatus: Ref<OptimizationSession | null>
  startOptimization(targetName: string, maxRounds?: number): Promise<void>
  cancelOptimization(): Promise<void>
  variants: Ref<PromptVariant[]>
  scoreVariant(variantId: string, score: number): Promise<void>

  // Approvals
  pendingApprovals: Ref<ApprovalRequest[]>
  approveExperiment(sessionId: string, experimentId: string): Promise<void>
  rejectExperiment(sessionId: string, experimentId: string): Promise<void>

  // Insights
  insights: Ref<ExperimentInsight[]>
  searchInsights(query: string): Promise<void>

  // Polling
  startPolling(intervalMs?: number): void
  stopPolling(): void
}
```

### 4.2 Pinia Store

```typescript
// stores/useAutoResearchStore.ts
// Caches experiment data, active polling state, pending approvals
// Follows existing defineStore() pattern with persisted state
```

### 4.3 Components

| Component | Purpose |
|-----------|---------|
| `ExperimentDashboard.vue` | Admin page — stats header + 3 panels (timeline, optimizer, insights) |
| `ExperimentTimeline.vue` | Scrollable timeline grouped by session, state badges, val_bpb trend line |
| `PromptOptimizerPanel.vue` | Start/stop optimization, view variants, submit human scores |
| `InsightsPanel.vue` | Distilled insights list with confidence badges, semantic search |
| `ApprovalCard.vue` | Reusable approve/reject card with metrics comparison |
| `AutoResearchWorkflowAdapter.vue` | Lightweight experiment view for workflow history (non-admin) |

### 4.4 Route

```typescript
{
  path: '/experiments',
  component: ExperimentDashboard,
  meta: { title: 'Experiments', icon: 'BeakerIcon', requiresAuth: true }
}
```

### 4.5 Charts

ApexCharts (already in the project) for:
- Stats sparklines in the header (experiments over time, val_bpb trend)
- Improvement trend line in ExperimentTimeline

### 4.6 Files

- `autobot-frontend/src/composables/useAutoResearch.ts`
- `autobot-frontend/src/stores/useAutoResearchStore.ts`
- `autobot-frontend/src/views/ExperimentDashboard.vue`
- `autobot-frontend/src/components/autoresearch/ExperimentTimeline.vue`
- `autobot-frontend/src/components/autoresearch/PromptOptimizerPanel.vue`
- `autobot-frontend/src/components/autoresearch/InsightsPanel.vue`
- `autobot-frontend/src/components/autoresearch/ApprovalCard.vue`
- `autobot-frontend/src/components/autoresearch/AutoResearchWorkflowAdapter.vue`
- Route addition in `autobot-frontend/src/router/index.ts`

---

## 5. Testing

### 5.1 Backend Unit Tests

| Test File | Scope |
|-----------|-------|
| `prompt_optimizer_test.py` | Mutation logic, optimization loop with mock scorers |
| `scorers_test.py` | Each scorer in isolation (mocked LLM, Redis, runner) |
| `knowledge_synthesizer_test.py` | Document enrichment, insight generation with mocked LLM + ChromaDB |

### 5.2 Backend Integration Tests

| Test File | Scope |
|-----------|-------|
| `test_autoresearch_m3.py` | Full optimization loop → knowledge synthesis → insight query |

### 5.3 Route Tests

Extend existing `routes_test.py` with new endpoint coverage (optimizer, approvals, insights).

### 5.4 Frontend Tests

| Test File | Scope |
|-----------|-------|
| `useAutoResearch.spec.ts` | Composable with mocked API |
| `ExperimentDashboard.spec.ts` | Component mount + rendering with fixture data |
| `ApprovalCard.spec.ts` | Approve/reject actions emit correct events |

### 5.5 Not Tested

- LLM output quality (non-deterministic) — test that scorers call LLM and process response, not output quality
- ChromaDB embedding similarity — test upsert/query calls, not embedding relevance

---

## File Summary

### New Files (Backend)
- `autobot-backend/services/autoresearch/prompt_optimizer.py`
- `autobot-backend/services/autoresearch/scorers.py`
- `autobot-backend/services/autoresearch/knowledge_synthesizer.py`
- `autobot-backend/services/autoresearch/prompt_optimizer_test.py`
- `autobot-backend/services/autoresearch/scorers_test.py`
- `autobot-backend/services/autoresearch/knowledge_synthesizer_test.py`
- `autobot-backend/tests/test_autoresearch_m3.py`

### Modified Files (Backend)
- `autobot-backend/services/autoresearch/store.py` — enriched indexing
- `autobot-backend/services/autoresearch/auto_research_agent.py` — synthesizer integration, notification dispatch
- `autobot-backend/services/autoresearch/routes.py` — new endpoints
- `autobot-backend/services/autoresearch/__init__.py` — new exports

### New Files (Frontend)
- `autobot-frontend/src/composables/useAutoResearch.ts`
- `autobot-frontend/src/stores/useAutoResearchStore.ts`
- `autobot-frontend/src/views/ExperimentDashboard.vue`
- `autobot-frontend/src/components/autoresearch/ExperimentTimeline.vue`
- `autobot-frontend/src/components/autoresearch/PromptOptimizerPanel.vue`
- `autobot-frontend/src/components/autoresearch/InsightsPanel.vue`
- `autobot-frontend/src/components/autoresearch/ApprovalCard.vue`
- `autobot-frontend/src/components/autoresearch/AutoResearchWorkflowAdapter.vue`

### Modified Files (Frontend)
- `autobot-frontend/src/router/index.ts` — new route
