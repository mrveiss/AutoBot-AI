# Token-Based Budget Mode (GH#8997)

## Overview

The LLC budget system now supports **two budget modes** to accommodate different user scenarios:

1. **DOLLARS mode** (default): Track spend in USD, enforce dollar limits
2. **TOKENS mode**: Track spend in token counts, enforce token limits

This allows users on subscription plans (Claude Max, ChatGPT Plus) or free-tier models to set monthly token allowances instead of dollar budgets.

## Features

### Dual Tracking
- **Both modes track both metrics:**
  - Dollar spend (always calculated for cost analytics)
  - Token consumption (for usage analytics)
- Only the **active mode** is enforced for hard-stop budget limits

### Mode-Aware Enforcement
- **DOLLARS mode**: Hard stop at `budget_limit` (USD)
- **TOKENS mode**: Hard stop at `token_limit` (token count)
- Alert thresholds work in both modes (default: 80%)

## API Changes

### BudgetResponse

```json
{
  "agent_id": "agent-123",
  "budget_mode": "tokens",
  
  // Dollar fields (always present)
  "budget_limit": "100.00",
  "budget_spent": "42.50",
  
  // Token fields (GH#8997)
  "token_limit": 1000000,
  "tokens_spent": 450000,
  
  "alert_threshold": 0.8,
  "remaining": "550000",  // In active mode (tokens here)
  "is_over_limit": false,
  "alert_triggered": false
}
```

### Update Budget Mode

**PATCH /api/llc/budget/{agent_id}/limit**

```json
{
  "budget_mode": "tokens",
  "token_limit": 1000000,
  "alert_threshold": 0.8
}
```

Switch back to dollars mode:
```json
{
  "budget_mode": "dollars",
  "budget_limit": "100.00"
}
```

## Database Schema

### New Columns (llc_agent_budgets)

- `budget_mode` (String): 'dollars' or 'tokens' (default: 'dollars')
- `token_limit` (BigInteger, nullable): Monthly token allowance for TOKENS mode
- `tokens_spent` (BigInteger): Token consumption counter (tracked in both modes)

### Migration

Migration `20260604_036_budget_token_mode.py` adds these columns with safe defaults:
- Existing rows default to `budget_mode='dollars'`
- `tokens_spent` initialized to 0
- `token_limit` is NULL for DOLLARS mode agents

## Use Cases

### Subscription Plans (Claude Max, ChatGPT Plus)
```python
# User pays fixed monthly fee, wants to track token usage
await budget_service.update_limit(
    agent_id="agent-123",
    budget_mode="tokens",
    token_limit=5_000_000,  # 5M tokens/month
    alert_threshold=0.9
)
```

### Free-Tier Models
```python
# Free tier allows X tokens/month before switching to paid
await budget_service.update_limit(
    agent_id="agent-456",
    budget_mode="tokens",
    token_limit=100_000,  # 100k tokens/month
    alert_threshold=0.8
)
```

### Pay-Per-Use (Default)
```python
# Traditional dollar-based budgets for API usage
await budget_service.update_limit(
    agent_id="agent-789",
    budget_mode="dollars",
    budget_limit=Decimal("50.00"),
    alert_threshold=0.8
)
```

## Backend Implementation

### BudgetService

**ingest_cost_event()**:
- Calculates dollar cost from MODEL_PRICING_PER_1M_TOKENS
- Atomically updates BOTH `budget_spent` AND `tokens_spent`
- Enforces limits based on `budget_mode`

**check_budget()**:
- Returns remaining budget in the active mode
- TOKENS mode: remaining tokens
- DOLLARS mode: remaining dollars

### AgentBudgetTracker

**AgentBudgetState** now includes:
- `budget_mode`
- `tokens_spent`
- `token_limit`

Computed properties (`remaining`, `is_over_limit`, `alert_triggered`) are mode-aware.

## Frontend Integration (TODO)

### CostDashboard
- Show token consumption alongside dollar spend
- Display mode selector: "Track by Dollars" / "Track by Tokens"
- Mode-appropriate charts ($ vs token counts)

### Agent Settings
- Budget mode toggle in agent configuration
- Conditional input: dollar amount OR token count
- Clear labeling: "Monthly Token Allowance" vs "Monthly Dollar Limit"

## Testing

### Manual Testing

1. **Create a token-mode budget:**
   ```bash
   curl -X PATCH http://localhost:8001/api/llc/budget/test-agent/limit \
     -H "Content-Type: application/json" \
     -d '{
       "budget_mode": "tokens",
       "token_limit": 100000,
       "alert_threshold": 0.8
     }'
   ```

2. **Ingest some token usage:**
   ```bash
   curl -X POST http://localhost:8001/api/llc/budget/test-agent/ingest \
     -H "Content-Type: application/json" \
     -d '{
       "tokens_in": 1000,
       "tokens_out": 500,
       "model": "claude-sonnet-4-6"
     }'
   ```

3. **Check budget status:**
   ```bash
   curl http://localhost:8001/api/llc/budget/test-agent
   ```

   Should show `tokens_spent: 1500`, `remaining: 98500`

4. **Test hard stop:**
   Ingest tokens until `tokens_spent > token_limit`
   → Should get 402 BudgetExhausted error

### Unit Tests (TODO)

- Test mode switching (dollars → tokens → dollars)
- Test enforcement in both modes
- Test alert thresholds in both modes
- Test cache invalidation on mode change

## Related Issues

- GH#8215: Original per-agent budget implementation (dollar-based)
- Paperclip #1756: 8👍 Token-based budget mode request
- Paperclip #339: 13👍 Token tracking for subscription users
- GH#6630: AgentBudgetTracker SharedRuntimeBag integration
- GH#8551: CostDashboard integration

## Migration Path

Existing deployments:
1. Run migration `20260604_036` — safe, adds columns with defaults
2. All existing agents remain in DOLLARS mode (no behavior change)
3. Operators can switch agents to TOKENS mode via API as needed
4. Frontend updates can be deployed independently (feature flag)
