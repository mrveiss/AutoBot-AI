# Model Selection Guide

AutoBot uses AI language models to understand your messages and generate
responses. This guide explains how models are selected, what the tier system
means, and how it affects your experience.

## What is a Model?

A **model** is the AI engine that reads your messages and produces responses.
Different models have different strengths:

- **Smaller models** respond faster and use fewer resources, but may handle
  complex tasks less thoroughly.
- **Larger models** handle nuanced, multi-step tasks better, but take slightly
  longer to respond.

AutoBot manages model selection automatically so you do not need to choose a
model yourself.

## How AutoBot Chooses a Model

When you send a message, AutoBot evaluates its **complexity** -- how difficult
or nuanced your request is. Based on that score, it routes the request to the
most appropriate model. This process is called **tiered model routing**.

The flow looks like this:

1. You send a message.
2. AutoBot's complexity scorer analyzes the message (length, topic, required
   reasoning depth).
3. The message is routed to the model best suited for that complexity level.
4. The model generates a response.

This happens in the background and typically adds no noticeable delay.

## The Tier System

AutoBot organizes its AI capabilities into tiers. Each tier is optimized for a
different kind of workload.

### Agent Tiers

Agents are classified into four tiers based on how they share processing
resources:

| Tier | Name | Typical Agents | Cache Efficiency |
|------|------|----------------|-----------------|
| 1 | Default | Backend Engineer, Frontend Engineer, Database Engineer, Documentation Engineer, Testing Engineer, DevOps Engineer | Highest (90-95%) |
| 2 | Analysis | Code Reviewer, Performance Engineer, Security Auditor | High (70-80%) |
| 3 | Specialized | Systems Architect, AI/ML Engineer, Content Writer | Moderate (40-60%) |
| 4 | Orchestrator | Orchestrator (coordinates all agents) | Session-specific (50-70%) |

**Cache efficiency** means how effectively AutoBot reuses previous computations.
Higher efficiency means faster response times for you.

### Model Routing Tiers

Separately, messages are routed to models based on complexity:

| Complexity | Routed To | Example Tasks |
|------------|-----------|---------------|
| Simple | Lightweight model | Greetings, simple lookups, yes/no questions |
| Complex | Full-capability model | Multi-step analysis, code generation, research |

AutoBot may also use a **routing model** -- a lightweight model whose only job
is to decide which main model should handle the request.

## What This Means for You

- **You do not need to select a model.** AutoBot handles this automatically.
- **Simple questions get fast answers.** Straightforward requests are routed to
  fast, lightweight models.
- **Complex questions get thorough answers.** Detailed or multi-step requests
  are routed to more capable models.
- **Agents use the best model for their specialty.** A code reviewer uses a
  model optimized for code analysis, while a documentation writer uses one
  optimized for language.

## Failsafe System

If the primary model is unavailable (for example, during maintenance), AutoBot
has a multi-tier failsafe system:

1. **Primary** -- the preferred model for the task.
2. **Secondary** -- a backup model with similar capabilities.
3. **Basic** -- a simpler model that can still provide useful responses.
4. **Emergency** -- a minimal, rule-based system that ensures you always get
   some form of response.

You will rarely notice the failsafe activating. If it does, responses may be
simpler than usual until the primary model is restored.

## Frequently Asked Questions

**Can I choose which model to use?**
Model selection is managed by AutoBot's routing system. This ensures optimal
performance and resource usage. Administrators can configure which models are
available through the SLM admin settings.

**Why do some responses feel different from others?**
Different models have different writing styles. If your request was routed to
a different model (due to complexity or failover), the tone or level of detail
may vary slightly.

**Does model selection affect my knowledge base?**
No. Your documents and knowledge are stored independently. Model selection
only affects how AutoBot processes and responds to your messages.

## Related Guides

- [Working with Agents](working-with-agents.md) -- agents are assigned to
  tiers
- [Chat Interface](chat-interface.md) -- where you interact with models
- [Settings and Preferences](settings.md) -- configure your AutoBot experience
