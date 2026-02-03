# Tiered Model Distribution Design

**Issue:** #748 - [HIGH] Tiered Model Distribution Implementation
**Date:** 2026-02-03
**Author:** mrveiss
**Status:** Design Complete

## Overview

Implement tiered model distribution to achieve 50-75% reduction in resource usage for simple tasks by routing requests to appropriately-sized models based on task complexity.

## Goals

- Route simple requests (complexity < 3) to lightweight model (`gemma2:2b`)
- Route complex requests (complexity >= 3) to capable model (`mistral:7b-instruct`)
- Achieve 50%+ reduction in compute resources for simple tasks
- Maintain response quality through intelligent routing

## Architecture

```
Request --> ComplexityScorer --> TieredModelRouter --> ModelProvider --> Response
                 |                      |
            Score (0-10)         gemma2:2b (simple, score < 3)
                                 mistral:7b (complex, score >= 3)
```

### Components

1. **TaskComplexityScorer** - Rule-based classifier (~5ms latency)
2. **TieredModelRouter** - Model selection based on complexity score
3. **Integration Layer** - Hooks into existing LLMInterface

## Complexity Scoring Algorithm

The scorer uses weighted heuristic factors:

| Factor | Weight | Score Logic |
|--------|--------|-------------|
| Message Length | 0.15 | <100 chars = 0, 100-500 = 1, 500-1000 = 2, >1000 = 3 |
| Code Detection | 0.25 | Code blocks/syntax patterns: 0-3 points |
| Technical Terms | 0.20 | Domain keywords (API, database, regex, etc.): 0-3 |
| Multi-step Indicators | 0.20 | "first...then", numbered steps, conditionals: 0-3 |
| Question Complexity | 0.20 | Simple (what/how) = 0, Why/explain = 1, Compare/design = 2-3 |

**Formula:** `score = sum(factor_score * weight) * 10/3` --> normalized to 0-10

### Example Classifications

| Request | Score | Tier |
|---------|-------|------|
| "What time is it?" | 0.5 | Simple (gemma2:2b) |
| "List Python string methods" | 1.8 | Simple (gemma2:2b) |
| "Explain async vs threads" | 4.2 | Complex (mistral:7b) |
| "Write a Python script that parses JSON, validates schema, stores in Redis" | 7.8 | Complex (mistral:7b) |

## File Structure

### New Files

```
src/llm_interface_pkg/tiered_routing/
    __init__.py              # Package exports
    complexity_scorer.py     # TaskComplexityScorer class
    tier_router.py           # TieredModelRouter class
    tier_config.py           # TierConfig dataclass
```

### Modified Files

1. `src/llm_interface_pkg/interface.py` - Add tiered routing in `_determine_provider_and_model()`
2. `src/constants/model_constants.py` - Add tier model constants
3. `config/ssot_config.yaml` - Add tiered routing configuration

## Configuration

```yaml
# config/ssot_config.yaml
tiered_routing:
  enabled: true
  complexity_threshold: 3
  models:
    simple: "gemma2:2b"
    complex: "mistral:7b-instruct"
  fallback_to_complex: true
  logging:
    log_scores: true
    log_routing_decisions: true
```

## Implementation Plan

### Phase 1: Core Implementation (3 days)
1. Create `tiered_routing/` package structure
2. Implement `TaskComplexityScorer`
3. Implement `TieredModelRouter`

### Phase 2: Integration (2 days)
4. Integrate with `LLMInterface`
5. Add configuration to SSOT
6. Add model tier constants

### Phase 3: Monitoring (2 days)
7. Implement metrics tracking
8. Add logging and observability
9. Write tests

### Phase 4: Validation (3 days)
10. Quality validation with sample requests
11. Performance benchmarking
12. Threshold tuning based on results

## Success Criteria

- [ ] Simple requests (< 3 complexity) handled by `gemma2:2b`
- [ ] Complex requests (>= 3 complexity) handled by `mistral:7b-instruct`
- [ ] 50%+ reduction in compute resources for simple tasks
- [ ] No degradation in response quality (validated by sampling)
- [ ] Metrics visible in system dashboard

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Quality degradation for mis-routed requests | High | Fallback to complex tier, quality monitoring |
| Scoring overhead impacts latency | Low | Rule-based scoring is <5ms |
| Model availability issues | Medium | Fallback chain, health checks |
| Threshold misconfiguration | Medium | Configurable thresholds, A/B testing |

## Related Issues

- Issue #717: Efficient Inference Design (optimization router)
- Issue #229: LLM Pattern Analyzer (usage tracking)
- Issue #551: L1/L2 Caching (cache integration)
