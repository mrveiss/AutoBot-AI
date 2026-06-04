---
tags:
  - user-guide
  - chat
  - reasoning
  - ai-settings
aliases:
  - Reasoning Effort Guide
---

# Reasoning Effort Guide

Control how deeply AI reasoning models think before responding. Adjusting **reasoning effort** lets you trade response speed and cost against reasoning depth.

---

## What Is Reasoning Effort?

Modern AI reasoning models (OpenAI o3/o4-mini, Google Gemini 2.5, Anthropic Claude with extended thinking) can spend more or fewer compute cycles "thinking" before generating an answer. AutoBot exposes this as a single **Reasoning Effort** selector with four levels:

| Level | Hint | Best For |
|-------|------|----------|
| **Low** | ⚡ 2× faster, ~60% cheaper | Factual lookups, summaries, routine tasks |
| **Medium** | ⚙️ Balanced speed & quality | General-purpose chat, code review |
| **High** | 🧠 Deepest reasoning, higher cost | Complex debugging, multi-step planning |
| **Auto** | 🤖 Provider default | Let the model decide (safe default) |

---

## Setting Reasoning Effort

### Per-Conversation (in ChatSettingsModal)

1. Open a chat session.
2. Click the **settings gear** icon in the chat toolbar to open **Chat Settings**.
3. Under **Reasoning Effort**, select your preferred level.
4. Optionally check **Set as my default** to save this level for future conversations.
5. Click **Apply** — the setting takes effect immediately for all new messages in this session.

> **Note:** Changing the effort level mid-conversation affects only messages sent after the change.

### Persistent Default (Preferences)

1. Navigate to **Preferences** (top navigation → Preferences, or `/preferences`).
2. Scroll to **AI Behavior → Reasoning Effort**.
3. Choose your default level.
4. Click **Save Preferences**.

All new chat sessions will start with this effort level. You can still override it per conversation.

---

## Provider Behavior

The same effort level maps to different provider parameters depending on the model you are using:

### OpenAI (o3, o4-mini)

OpenAI accepts `reasoning_effort` natively:

| Level | Parameter sent |
|-------|---------------|
| Low | `reasoning_effort: "low"` |
| Medium | `reasoning_effort: "medium"` |
| High | `reasoning_effort: "high"` |
| Auto | Not sent (provider default) |

### Google Gemini 2.5

Gemini uses a `thinking_mode` parameter:

| Level | Parameter sent |
|-------|---------------|
| Low | `thinking_mode: "low"` |
| Medium | `thinking_mode: "medium"` |
| High | `thinking_mode: "high"` |
| Auto | Not sent (provider default) |

### Anthropic Claude (Extended Thinking)

Claude uses a token budget for extended thinking:

| Level | Thinking tokens |
|-------|----------------|
| Low | 10,000 tokens |
| Medium | 30,000 tokens |
| High | 63,000 tokens |
| Auto | Extended thinking disabled (standard response) |

> **Backward compatibility:** If you have existing AutoBot configurations that set `thinking_mode_enabled` and `thinking_budget_tokens` directly, those still work. The `reasoning_effort` selector is additive — it fills in sensible defaults when you haven't manually configured thinking.

---

## Cost & Speed Tradeoffs

Reasoning costs vary by provider and model. Use this table as a rough guide:

| Level | Typical latency | Typical cost vs. Auto |
|-------|----------------|----------------------|
| Low | Fastest | ~40% of Auto |
| Medium | Moderate | ~70% of Auto |
| High | Slowest | ~150% of Auto |
| Auto | Varies | Baseline (1×) |

Exact costs depend on your model, provider, and input/output token counts. Check your provider's current pricing for precise figures.

---

## Unsupported Models

If the selected model does not support reasoning effort (e.g., standard GPT-4o, Gemini Flash, older Claude models), AutoBot silently ignores the setting and responds normally — no error is shown. The reasoning effort badge in the UI is greyed out for unsupported models.

---

## Frequently Asked Questions

**Q: Does reasoning effort affect the quality of non-reasoning tasks?**  
A: For models that support it, Low effort can occasionally miss nuance on complex tasks. For simple Q&A or summaries, Low is usually indistinguishable from High.

**Q: Will my reasoning effort preference apply to all my chats?**  
A: Yes, once you set a default in Preferences. Per-conversation overrides apply only to that conversation.

**Q: Can I see the model's reasoning steps?**  
A: Enable **Include Reasoning** in Chat Settings (a separate toggle from effort level). This shows the chain-of-thought before the final answer.

**Q: What happens if I switch models mid-conversation?**  
A: The effort level remains set, but it takes effect on the new model according to that model's mapping (see provider tables above).

---

## Related Documentation

- [Preferences Guide](05-preferences.md) — Set defaults for all AI behavior settings
- [Chat Configuration](03-configuration.md) — Advanced chat configuration options
- [API: reasoning_effort parameter](../api/chat-reasoning-effort.md) — Developer API reference
