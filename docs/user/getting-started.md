# Getting Started with AutoBot

This guide walks you through installing AutoBot and completing your first-run
setup. By the end, you will have a running instance and be ready to chat.

## What is AutoBot?

AutoBot is an AI-powered automation platform. It provides:

- **AI Chat** -- Converse with an AI assistant that can answer questions, run
  commands, and coordinate specialized agents.
- **Knowledge Base** -- Upload documents so the AI can reference them in
  conversations.
- **Workflow Automation** -- Build visual workflows that automate repetitive
  tasks.
- **Analytics** -- View codebase analytics, conversation insights, and more.

## System Requirements

| Requirement | Minimum |
|-------------|---------|
| Disk space | 5 GB free |
| Memory (RAM) | 2 GB |
| Operating system | Linux (Ubuntu 22.04+ recommended) |
| Browser | Any modern browser (Chrome, Firefox, Edge, Safari) |

## Installation

AutoBot ships with a single installer script. Your system administrator will
typically run this for you. If you are setting it up yourself:

1. Open a terminal on the server where AutoBot will run.
2. Run the installer:

   ```
   sudo ./install.sh
   ```

   Alternatively, install directly from the repository:

   ```
   curl -fsSL https://raw.githubusercontent.com/mrveiss/AutoBot-AI/main/install.sh | bash
   ```

3. The installer will check requirements, download dependencies, and configure
   the platform. This may take several minutes.
4. When the installer finishes, note the URL it prints -- this is how you will
   access AutoBot in your browser.

### Unattended Installation

For automated deployments, pass the `--unattended` flag:

```
sudo ./install.sh --unattended
```

## First-Run Setup

1. **Open AutoBot in your browser.** Navigate to the URL provided by the
   installer (for example, `https://your-server:8443`).

<!-- Screenshot: Login page -->

2. **Log in.** Enter the credentials created during installation. If AutoBot is
   running in single-user mode, you will be logged in automatically.

3. **Explore the navigation bar.** The main sections are:
   - **AI Assistant** (`/chat`) -- your primary workspace for conversations.
   - **Knowledge Base** (`/knowledge`) -- manage documents and data sources.
   - **Workflow Automation** (`/automation`) -- build and run automated workflows.
   - **Analytics** (`/analytics`) -- dashboards for code and business insights.

4. **Send a test message.** Click **AI Assistant** in the navigation bar, type a
   greeting such as "Hello, AutoBot!" and press **Enter**. If you receive a
   reply, everything is working.

<!-- Screenshot: First message in chat -->

## Next Steps

- [Quick Start: Your First Conversation](quick-start-chat.md)
- [Quick Start: Knowledge Base](quick-start-knowledge.md)
- [Full User Guide Index](README.md)
