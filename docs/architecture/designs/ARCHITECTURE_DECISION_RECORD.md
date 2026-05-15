# Architecture Decision Record: Industry-Standard Agent Patterns

**Issue**: #645 - Implement Industry-Standard Agent Architecture Patterns
**Author**: mrveiss
**Date**: 2025-12-28
**Status**: Approved

---

## ADR Summary

This document records the architectural decisions made to align AutoBot's agent system with industry-leading patterns from Manus, Cursor, Devin, and Windsurf.

---

## Decision 1: Event Stream Architecture

### Context

AutoBot currently uses direct call/response patterns without a persistent event stream. This makes it difficult to:
- Track multi-step task progression
- Debug agent behavior
- Enable iteration control
- Provide visibility into agent operations

### Decision

**Implement a Redis-based Event Stream System** with typed events.

### Rationale

- **Manus Pattern**: Uses chronological event stream with typed events
- **Observability**: Events provide audit trail and debugging capability
- **Integration**: Redis already used for other AutoBot components
- **Performance**: Redis Streams support 100k+ events/second

### Consequences

| Positive | Negative |
|----------|----------|
| Full task visibility | Additional Redis storage |
| Debug capability | New abstraction layer |
| Enables Planner integration | Learning curve |
| WebSocket streaming to frontend | Event pruning needed |

### Implementation

See: [EVENT_STREAM_SYSTEM_DESIGN.md](EVENT_STREAM_SYSTEM_DESIGN.md)

---

## Decision 2: Planner Module

### Context

AutoBot lacks explicit task planning. Tasks are executed ad-hoc without:
- Numbered step tracking
- Progress visibility
- Plan updates based on new information
- Dependency management between steps

### Decision

**Implement an LLM-powered Planner Module** that generates numbered pseudocode steps.

### Rationale

- **Manus Pattern**: Separate Planner module with step tracking
- **Devin Pattern**: Dual-mode (Planning vs Execution)
- **User Visibility**: Users can see task progress
- **Quality**: Explicit planning improves task completion

### Consequences

| Positive | Negative |
|----------|----------|
| Clear task progression | Additional LLM calls |
| Better error recovery | Plan generation latency |
| TodoWrite integration | Plan update complexity |
| Parallel step identification | |

### Implementation

See: [PLANNER_MODULE_DESIGN.md](PLANNER_MODULE_DESIGN.md)

---

## Decision 3: Parallel Tool Execution

### Context

AutoBot executes tools sequentially, even when operations are independent. This results in:
- 3-5x slower task completion
- Inefficient resource utilization
- Poor user experience for multi-file operations

### Decision

**Implement automatic parallel execution** with dependency analysis.

### Rationale

- **Cursor Pattern**: "DEFAULT TO PARALLEL unless output of A is input to B"
- **Performance**: 3-5x faster execution documented by Cursor
- **Resource Efficiency**: Better CPU/IO utilization
- **User Experience**: Faster task completion

### Consequences

| Positive | Negative |
|----------|----------|
| 3-5x faster execution | Dependency analysis overhead |
| Better resource use | More complex error handling |
| Cursor pattern alignment | Race condition risks |
| Batch operation support | |

### Implementation

See: [PARALLEL_TOOL_EXECUTION_DESIGN.md](PARALLEL_TOOL_EXECUTION_DESIGN.md)

---

## Decision 4: Enhanced Knowledge Module

### Context

AutoBot's current knowledge retrieval lacks:
- Scoped knowledge with adoption conditions
- Priority-based source ordering
- Quality rating system
- Event stream integration

### Decision

**Enhance the Knowledge Module** with scoping, conditions, and rating.

### Rationale

- **Manus Pattern**: Scoped knowledge with adoption conditions
- **Cursor Pattern**: 1-5 quality rating system
- **Relevance**: Scoped knowledge is more applicable
- **Quality Control**: Rating improves retrieval quality

### Consequences

| Positive | Negative |
|----------|----------|
| More relevant knowledge | Schema changes |
| Quality control | Rating overhead |
| Priority ordering | Migration needed |
| Event integration | |

### Implementation

See: [KNOWLEDGE_MODULE_ENHANCEMENTS_DESIGN.md](KNOWLEDGE_MODULE_ENHANCEMENTS_DESIGN.md)

---

## Decision 5: Agent Loop Formalization

### Context

AutoBot's agent execution is implicit without a formal loop structure. Industry agents use explicit iteration patterns.

### Decision

**Formalize a 6-step Agent Loop** based on Manus architecture.

### Agent Loop Steps

```
1. ANALYZE EVENTS    → Understand state from event stream
2. SELECT TOOLS      → Choose based on plan + knowledge
3. WAIT FOR EXECUTION → Sandbox executes tool
4. ITERATE           → One tool per iteration, repeat
5. SUBMIT RESULTS    → Deliver via message tools
6. ENTER STANDBY     → Idle state, await new tasks
```

### Rationale

- **Manus Pattern**: Clear 6-step loop with iteration control
- **Predictability**: Formal loop is easier to debug
- **Control**: Explicit iteration enables plan following
- **Modularity**: Each step can be monitored/modified

### Consequences

| Positive | Negative |
|----------|----------|
| Clear execution model | Code restructuring |
| Better debugging | Behavior changes |
| Plan integration | Testing effort |
| Event visibility | |

---

## Decision 6: Think Tool / Reasoning Scratchpad

### Context

Agents sometimes make poor decisions on critical operations (git, deployment, task completion) without explicit reasoning.

### Decision

**Add a Think Tool** for mandatory reasoning before critical decisions.

### Mandatory Think Cases (from Devin)

1. Before critical git/GitHub decisions
2. When transitioning from exploring to making changes
3. Before reporting completion to user

### Rationale

- **Devin Pattern**: Mandatory reasoning at decision points
- **Quality**: Explicit reasoning improves decisions
- **Debugging**: Reasoning is recorded in event stream
- **User Trust**: Users can see agent reasoning

### Consequences

| Positive | Negative |
|----------|----------|
| Better decisions | Additional latency |
| Visible reasoning | Token overhead |
| Audit trail | Implementation complexity |

---

## Decision 7: Message Semantics

### Context

Current messages don't distinguish between:
- Blocking questions (need user response)
- Non-blocking notifications (progress updates)

### Decision

**Implement `notify` and `ask` message types** (Manus pattern).

### Message Types

| Type | Blocking | Use Case |
|------|----------|----------|
| `notify` | No | Progress updates, status changes |
| `ask` | Yes | Questions requiring user response |

### Rationale

- **Manus Pattern**: Clear message semantics
- **UX**: Users know when response is needed
- **Flow Control**: Agent waits appropriately

---

## Implementation Roadmap

### Phase 1: Foundation (Week 1-2)

| Component | Priority | Status |
|-----------|----------|--------|
| Event Stream System | P0 | Design Complete |
| Event Types Definition | P0 | Design Complete |
| Redis Integration | P0 | Design Complete |

### Phase 2: Planner & Tools (Week 2-4)

| Component | Priority | Status |
|-----------|----------|--------|
| Planner Module | P1 | Design Complete |
| Parallel Tool Executor | P1 | Design Complete |
| Dependency Analyzer | P1 | Design Complete |

### Phase 3: Knowledge & Agent Loop (Week 4-6)

| Component | Priority | Status |
|-----------|----------|--------|
| Knowledge Module Enhancements | P2 | Design Complete |
| Agent Loop Formalization | P2 | Pending |
| Think Tool | P2 | Pending |

### Phase 4: Integration & Testing (Week 6-8)

| Component | Priority | Status |
|-----------|----------|--------|
| Agent Prompt Updates | P1 | Pending |
| WebSocket Event Streaming | P2 | Pending |
| Performance Benchmarking | P2 | Pending |
| Documentation | P3 | Pending |

---

## Success Metrics

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| Task completion time | Baseline | 3-5x faster | Parallel execution |
| Task visibility | None | Full | Event stream coverage |
| Knowledge relevance | ~60% | >85% | User feedback |
| Error recovery rate | ~40% | >70% | Retry success |
| Step completion tracking | None | 100% | Planner integration |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Breaking existing behavior | Medium | High | Phased rollout, feature flags |
| Performance regression | Low | Medium | Benchmarking before/after |
| Increased complexity | High | Medium | Comprehensive documentation |
| Redis storage growth | Medium | Low | Event pruning, TTL |
| LLM cost increase | Medium | Medium | Efficient prompts, caching |

---

## Related Documents

1. [EVENT_STREAM_SYSTEM_DESIGN.md](EVENT_STREAM_SYSTEM_DESIGN.md)
2. [PLANNER_MODULE_DESIGN.md](PLANNER_MODULE_DESIGN.md)
3. [PARALLEL_TOOL_EXECUTION_DESIGN.md](PARALLEL_TOOL_EXECUTION_DESIGN.md)
4. [KNOWLEDGE_MODULE_ENHANCEMENTS_DESIGN.md](KNOWLEDGE_MODULE_ENHANCEMENTS_DESIGN.md)
5. [INDUSTRY_AGENT_PATTERNS_ANALYSIS.md](../INDUSTRY_AGENT_PATTERNS_ANALYSIS.md)

---

## Approval

| Role | Name | Date | Status |
|------|------|------|--------|
| Author | mrveiss | 2025-12-28 | Approved |
| Architect | mrveiss | 2025-12-28 | Approved |

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-12-28 | mrveiss | Initial design documents |
