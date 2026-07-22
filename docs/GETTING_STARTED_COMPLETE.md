---
title: Getting Started
nav_order: 2
---

# Getting Started with AutoBot

**Your data. Your AI.** AutoBot is a self-hosted, agentic AI platform you own: a small,
solid core, a management layer that runs the hard infrastructure for you, and modules you
install on top. Everything — your data, memory, agents, and knowledge graph — runs on
*your* infrastructure, pointed at any brain you choose.

New here? Start with [The AutoBot Platform Model](architecture/PLATFORM_MODEL.md) for the
core → SLM → modules picture, then follow the quick start below.

## Quick Start (Docker, ~5 minutes)

### Prerequisites

- Linux or WSL2 (Ubuntu 22.04 LTS recommended)
- Docker and Docker Compose
- Python 3.12 and Node.js 20 are installed automatically by the installer for bare-metal setups
- 16 GB+ RAM recommended

For bare-metal (systemd) installs and full system requirements, see the
[Installation Guide](user-guide/01-installation.md).

### Install

```bash
# 1. Clone the repository
git clone https://github.com/mrveiss/AutoBot-AI.git
cd AutoBot-AI

# 2. Configure and start with Docker
cp .env.example .env
docker compose up -d
```

### Open your dashboard

Visit **http://localhost** in your browser. AutoBot is ready to use.

For a guided first run, see the [Quick Start](user-guide/02-quickstart.md) and
[Configuration Guide](user-guide/03-configuration.md).

## What You Can Do

AutoBot is agentic — it talks, sees, and acts, all on hardware you control:

- **Chat and voice** — converse in text or hands-free voice against your own models
- **Browser and desktop control** — vision-in-the-loop browser automation and computer
  control, with human takeover
- **Human-in-the-loop approvals** — pause the agent on a proposed plan and resume only
  after you confirm
- **Visual workflow builder** — compose multi-step agent workflows on a drag-and-drop canvas
- **Knowledge graph** — institutional memory built from every conversation, document, and node
- **Multi-user + RBAC** — role-based access control for teams
- **Modules** — install AutoBot LLC (agents that work together as a company), Transcriber,
  and Codebase Analytics *(work in progress)* on the core
- **Service Lifecycle Manager (SLM)** — deploys, operates, and scales the underlying
  infrastructure for you

The full, code-verified feature registry lives in the
[Feature Catalog](features/CATALOG.md).

## Learn More

### Understand the platform

- [The AutoBot Platform Model](architecture/PLATFORM_MODEL.md) — core → SLM → modules
- [Agent System Architecture](architecture/AGENT_SYSTEM_ARCHITECTURE.md) — how agents work
- [Visual Architecture](architecture/VISUAL_ARCHITECTURE.md) — system diagrams
- [Glossary](GLOSSARY.md) — terms and definitions (including what SLM actually means)

### Install and operate

- [Installation Guide](user-guide/01-installation.md) — bare-metal and Docker
- [Configuration Guide](user-guide/03-configuration.md) — environment and settings
- [Troubleshooting Guide](user-guide/04-troubleshooting.md) — common issues
- [Browser + VNC Quick Start](QUICK_START_BROWSER_VNC.md) — desktop/browser worker setup

### Deploy at scale

- [Hybrid Deployment Guide](deployment/HYBRID_DEPLOYMENT_GUIDE.md) — multi-container setup
- [Docker Architecture](deployment/DOCKER_ARCHITECTURE.md) — container patterns
- [Security Implementation Summary](security/SECURITY_IMPLEMENTATION_SUMMARY.md) — RBAC and hardening
- [Session Takeover User Guide](security/SESSION_TAKEOVER_USER_GUIDE.md) — human oversight

### Build with it

- [Workflow API Documentation](workflow/WORKFLOW_API_DOCUMENTATION.md) — workflow integration
- [Advanced Workflow Features](workflow/ADVANCED_WORKFLOW_FEATURES.md) — complex automation
- [API Reference](developer/03-api-reference.md) — REST API for external systems
- [Contributing](../CONTRIBUTING.md) — help build AutoBot

---

*Explore the complete [Documentation Index](INDEX.md) for everything else.*
