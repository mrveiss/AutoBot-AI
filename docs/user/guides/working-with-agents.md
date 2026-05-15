# Working with Agents

AutoBot uses specialized **agents** to handle different types of tasks. This
guide explains what agents are, how they work, and how you can interact with
them.

## What is an Agent?

An agent is a focused AI worker designed for a specific kind of task. Think of
agents like team members with different specialties:

- One agent is great at writing code.
- Another excels at reviewing code for bugs.
- A third specializes in managing your knowledge base.

When you send a message in the chat, AutoBot's **orchestrator** decides which
agent (or combination of agents) is best suited to handle your request. This
happens automatically -- you do not need to pick an agent yourself.

## How Agents Work Behind the Scenes

1. You send a message in the chat.
2. The **orchestrator** analyzes your message to understand what you need.
3. The orchestrator routes your request to one or more specialized agents.
4. Each agent processes its part of the task.
5. The results are combined and delivered back to you as a single response.

This all happens in seconds. From your perspective, it looks like a single
conversation.

## Types of Agents

AutoBot includes several categories of agents:

### Implementation Agents

These agents build and create things:

| Agent | What It Does |
|-------|--------------|
| Backend Engineer | Writes and modifies server-side code |
| Frontend Engineer | Works on user interface code |
| Database Engineer | Handles database design and queries |
| DevOps Engineer | Manages deployment and infrastructure |
| Documentation Engineer | Creates and updates documentation |
| Testing Engineer | Writes and runs tests |

### Analysis Agents

These agents review and evaluate:

| Agent | What It Does |
|-------|--------------|
| Code Reviewer | Checks code for quality and bugs |
| Performance Engineer | Finds and fixes performance issues |
| Security Auditor | Identifies security vulnerabilities |

### Specialized Agents

These agents handle unique tasks:

| Agent | What It Does |
|-------|--------------|
| Systems Architect | Designs system architecture |
| AI/ML Engineer | Works on machine learning components |
| Content Writer | Creates written content and documentation |

### Orchestrator

The orchestrator is a special agent that coordinates all the others. It
reads your message, decides which agents to involve, and assembles the final
response. You interact with the orchestrator whenever you use the chat.

## The Agent Registry

You can browse all available agents in the **Agent Registry**:

1. Navigate to `/agent-registry` from the navigation bar.
2. The registry has two tabs:
   - **Backend Agents** -- the built-in AutoBot worker agents.
   - **Specialized Agents** -- agents defined for specific project workflows.
3. Click any agent to see its description, capabilities, and current status.

<!-- Screenshot: Agent Registry with backend and specialized tabs -->

### Filtering Agents

Use the category filter to narrow the list. Categories include Implementation,
Analysis, and Specialized.

## When Do Agents Activate?

Agents activate based on what you ask. Here are some examples:

| Your Message | Agent(s) Used |
|-------------|---------------|
| "Summarize this document" | Knowledge retrieval agent, Chat agent |
| "Review this code for bugs" | Code Reviewer agent |
| "Deploy the latest changes" | DevOps Engineer agent |
| "What are the security risks?" | Security Auditor agent |
| "Write a unit test for this function" | Testing Engineer agent |

You do not need to remember agent names. Simply describe what you need, and
AutoBot will route it to the right agent.

## Approval Requests

Some agent actions require your approval before they execute. When this
happens, you will see an **approval card** in the chat:

1. Read the description of what the agent wants to do.
2. Click **Approve** to allow the action, or **Reject** to cancel it.

This ensures you stay in control of sensitive operations.

<!-- Screenshot: Approval request card in chat -->

## Tips

- Be specific about what you want. "Fix the login bug on line 42 of auth.py"
  gives the agent more to work with than "Fix the bug."
- If the response is not what you expected, rephrase your request with more
  context.
- Check the Agent Registry to learn what each agent can do before asking
  complex questions.

## Related Guides

- [Chat Interface](chat-interface.md) -- where you interact with agents
- [Workflows](workflows.md) -- agents can be part of automated workflows
- [Model Selection](model-selection.md) -- how the AI models behind agents are
  chosen
