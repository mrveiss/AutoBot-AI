# Getting Started with AutoBot

The canonical getting-started guide is [INSTALL.md](../../INSTALL.md). It holds the
requirements table ([Requirements](../../INSTALL.md#requirements)), the one-line installer,
the Docker quickstart and the Setup Wizard. This page does not repeat them.

- **Dedicated Ubuntu host:** the one-line installer, see
  [Quick Start](../../INSTALL.md#quick-start).
- **Anything else:** Docker, see [Docker Deployment](../../INSTALL.md#docker-deployment).
- **README overview:** [README Quick Start](../../README.md#quick-start), including
  [First login](../../README.md#first-login).

## What is AutoBot?

AutoBot is a self-hosted AI platform. It provides:

- **AI Chat** -- converse with an AI assistant that can answer questions, run
  commands, and coordinate specialized agents.
- **Knowledge Base** -- upload documents so the AI can reference them in
  conversations.
- **Workflow Automation** -- build visual workflows that automate repetitive
  tasks. Workflows live inside a Company OS company, see the
  [Workflows guide](guides/workflows.md).
- **Analytics** -- view codebase analytics, conversation insights, and more.

## After You Log In

The header navigation holds **Home**, **Chat**, **Knowledge**, **Company OS** and
**Analytics**. **Automation** sits in the overflow menu and is hidden in Minimal UI mode.

To check that everything works, open **Chat**, type a greeting such as "Hello, AutoBot!"
and press **Enter**. If you receive a reply, a model is connected. If not, see the LLM step
in the [README Quick Start](../../README.md#quick-start): in Docker the bundled model server
only starts with `--profile ollama`.

## Next Steps

- [Quick Start: Your First Conversation](quick-start-chat.md)
- [Quick Start: Knowledge Base](quick-start-knowledge.md)
- [Full User Guide Index](README.md)
