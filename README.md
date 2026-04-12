# AutoBot

**Self-hosted AI platform for infrastructure automation. One dashboard. Your infrastructure. Complete control.**

[![Docker Smoke Test](https://github.com/mrveiss/AutoBot-AI/actions/workflows/docker-smoke-test.yml/badge.svg)](https://github.com/mrveiss/AutoBot-AI/actions/workflows/docker-smoke-test.yml) [![GitHub Stars](https://img.shields.io/github/stars/mrveiss/AutoBot-AI?style=social)](https://github.com/mrveiss/AutoBot-AI) 

---

## Table of Contents

- [What is AutoBot?](#what-is-autobot)
- [Quick Start (3 Steps)](#quick-start-3-steps)
- [Key Features](#key-features)
- [Why Self-Hosted?](#why-self-hosted)
- [Architecture](#architecture)
- [System Requirements](#system-requirements)
- [Full Deployment Guide](#full-deployment-guide)
- [Contributing](#contributing)
- [Support](#support)
- [Technology Stack](#technology-stack)
- [Roadmap](#roadmap)

---

## What is AutoBot?

AutoBot is a **self-hosted AI platform that turns your infrastructure into a conversational partner**. Instead of juggling multiple tools, SSH sessions, and documentation—ask AutoBot what you need to know, and it executes the actions.

- **Conversational Interface** — Chat with your infrastructure in natural language
- **Fleet Management** — Manage 1 server or 100+ servers equally
- **Knowledge Bases** — Upload your runbooks, ask questions about your own docs
- **Vision Processing** — Analyze screenshots, diagrams, infrastructure visuals
- **Workflow Automation** — Trigger complex deployments with a message
- **Privacy First** — Everything stays on your hardware. No external APIs. No data leaks.

### For DevOps & SysAdmins

Spend less time context-switching. More time solving problems. AutoBot is built for teams managing distributed infrastructure, from small fleets to enterprise scale.

### For Developers

Infrastructure shouldn't require a specialized language. Ask AutoBot in English. It translates to Ansible, Terraform, Docker, or custom integrations.

---

## Quick Start (3 Steps)

### Step 1: Clone the Repository

```bash
git clone https://github.com/mrveiss/AutoBot-AI.git
cd AutoBot-AI
cp .env.example .env
```

### Step 2: Start with Docker Compose

```bash
docker compose up -d
```

This starts AutoBot with all default services: FastAPI backend, Vue.js frontend, ChromaDB knowledge base, Redis cache, and the AI engine.

### Step 3: Open Your Browser

```
http://localhost:8000
```

You'll see the AutoBot dashboard. Click around, try a chat message. That's it—AutoBot is running.

**Expected output:** Dashboard loads, chat interface ready, backend logs show `INFO: Application startup complete`.

> **New to Docker?** We provide native installation instructions and development setup further down. [Jump to full deployment guide](#full-deployment-guide).

---

## Key Features

### 🎯 Natural Language Control

Skip the command line. Talk to your infrastructure.

```
You: "How many containers are running?"
AutoBot: "I found 14 containers. 12 are running, 2 are exited."

You: "Deploy version 2.1.0 to production."
AutoBot: "Deploying... Stage 1 complete. Stage 2 in progress..."
```

### 📚 Knowledge Bases (RAG)

Upload your runbooks, deployment guides, incident playbooks. AutoBot indexes them and answers questions using your own documentation—not generic training data.

- Supports PDF, Markdown, text files
- Automatically vectorized for semantic search
- Cached for instant retrieval

### 🖥️ Fleet Management

One-command deployments to 50+ servers. Health checks, dependency management, rollback procedures.

- Manage servers across multiple data centers
- Rolling deployments, canary releases, blue-green patterns
- Real-time status visibility

### 👁️ Vision Processing

AutoBot can analyze screenshots, system diagrams, and infrastructure visuals.

- Diagnose problems from error screenshots
- Parse architecture diagrams
- Understand visual infrastructure layouts

### ⚙️ Workflow Automation

Complex multi-step deployments become one message.

- Conditional logic (if service A fails, do X)
- Dependency chains (service B waits for A)
- Rollback triggers and incident automation

### 🔒 Privacy & Compliance

Everything runs on your hardware. No external APIs. No SaaS fees.

- HIPAA/SOC2 compatible deployments
- Air-gapped network support
- Full audit trails of all actions

---

## Why Self-Hosted?

When you send infrastructure data to cloud AI services:
- Your runbooks and secrets travel over the internet
- Processed by models you didn't train
- Stored on vendor infrastructure
- Subject to terms you didn't write

**Self-hosted AutoBot:** Everything stays in your VPC. No external dependencies. Full compliance control.

| Feature | AutoBot (Self-Hosted) | Cloud AI Services |
|---------|----------------------|-------------------|
| **Data Privacy** | Your servers only | Vendor's cloud |
| **Cost** | Free + hardware | SaaS subscription |
| **Compliance** | HIPAA/SOC2 ready | Limited guarantees |
| **Vendor Lock-in** | None—it's open source | High—API dependent |
| **Customization** | Full source access | Limited options |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Browser / Client                        │
└────────────────┬────────────────────────────────────────────┘
                 │ HTTPS
                 │
┌────────────────▼────────────────────────────────────────────┐
│              Vue.js Frontend (Port 8000)                     │
│         Dashboard • Chat • Fleet Mgmt • Settings             │
└────────────────┬────────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────────┐
│       FastAPI Backend (Port 8001 - Internal)                │
│  • Chat Processing  • Action Execution  • Knowledge Mgmt    │
└────────────────┬───────────────────┬──────────────────┬─────┘
                 │                   │                  │
      ┌──────────▼────┐   ┌─────────▼─────┐  ┌────────▼──────┐
      │  ChromaDB     │   │   Redis Cache │  │  Ansible      │
      │  Knowledge    │   │   (Sessions)  │  │  Executor     │
      │  Bases        │   └───────────────┘  └───────────────┘
      └───────────────┘
           │
      ┌────▼───────────────────────────────────────┐
      │  AI Engine (Claude / Local LLM)            │
      │  • Reasoning  • Planning  • Action Gen     │
      └──────────────────────────────────────────┘
           │
      ┌────▼───────────────────────────────────────┐
      │  Fleet Orchestration Layer                 │
      │  • Ansible Playbooks  • Terraform  • CLI   │
      └──────────────────────────────────────────┘
           │
      ┌────▼───────────────────────────────────────┐
      │  Target Infrastructure                     │
      │  • Linux Servers  • Kubernetes  • Networking
      └──────────────────────────────────────────┘
```

---

## System Requirements

### Minimum (Single Server Setup)

- **CPU:** 4 cores
- **RAM:** 8 GB
- **Storage:** 50 GB SSD
- **OS:** Linux (Ubuntu 20.04+, Debian 11+, CentOS 8+)
- **Docker:** 20.10+

### Recommended (Production)

- **CPU:** 8+ cores
- **RAM:** 16 GB
- **Storage:** 200+ GB SSD (for knowledge base growth)
- **OS:** Ubuntu 22.04 LTS or later
- **Docker:** 24.0+
- **Docker Compose:** 2.0+

### For Fleet Management (50+ servers)

- Add dedicated ChromaDB instance (separate hardware for knowledge bases)
- Redis cluster for multi-instance deployments
- Dedicated Ansible execution server

---

## Full Deployment Guide

### Option 1: Docker Compose (Easiest)

```bash
git clone https://github.com/mrveiss/AutoBot-AI.git
cd AutoBot-AI
cp .env.example .env
docker compose up -d
```

**Ports:** Frontend on `8000`, Backend on `8001`.

### Option 2: Native Installation

For production or development without Docker:

```bash
# Prerequisites
sudo apt-get update
sudo apt-get install python3.10 python3.10-venv nodejs npm

# Clone & setup
git clone https://github.com/mrveiss/AutoBot-AI.git
cd AutoBot-AI

# Backend setup
cd backend
python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8001

# Frontend (in new terminal)
cd frontend
npm install
npm run dev
```

### Option 3: Development Mode

For contributing and local testing:

```bash
make dev  # Runs all services with live reload
```

See [CONTRIBUTING.md](./CONTRIBUTING.md) for full development setup.

---

## Core Services

| Service | Port | Purpose |
|---------|------|---------|
| **Frontend** | 8000 | Vue.js dashboard and chat interface |
| **Backend API** | 8001 | FastAPI REST + WebSocket (internal) |
| **ChromaDB** | 8002 | Vector database for knowledge bases |
| **Redis** | 6379 | Session cache and job queue (internal) |

All internal ports (8001+) are firewalled by default. Only port 8000 is exposed to the network.

---

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# AI Model Configuration
LLM_PROVIDER=anthropic  # or openai, local
LLM_MODEL=claude-opus-4-6
ANTHROPIC_API_KEY=your_key_here

# Infrastructure Access
ANSIBLE_INVENTORY=/etc/ansible/hosts
TERRAFORM_PATH=/usr/local/bin/terraform

# Knowledge Base
CHROMA_DB_PATH=/data/chroma
CHROMA_ANONYMIZED_TELEMETRY=false

# Security
ENABLE_AUTH=true
JWT_SECRET=your_random_secret_here
```

For full configuration options, see `.env.example` and [docs/configuration.md](./docs/configuration.md).

---

## Contributing

We welcome contributions! Whether you're fixing bugs, adding features, or improving documentation:

1. **Pick an issue** — [Browse good-first-issue labels](https://github.com/mrveiss/AutoBot-AI/issues?q=label%3Agood-first-issue)
2. **Read guidelines** — See [CONTRIBUTING.md](./CONTRIBUTING.md) for process and setup
3. **Open a PR** — We review within 48 hours

### Get Help

- **Questions?** Start a [GitHub Discussion](https://github.com/mrveiss/AutoBot-AI/discussions)
- **Found a bug?** [Open an issue](https://github.com/mrveiss/AutoBot-AI/issues)
- **Want to chat?** Join our [community Discord](https://discord.gg/your-discord-link) (coming soon)

---

## Support & Sponsorship

AutoBot is free and open source. To support the project:

[![GitHub Sponsors](https://img.shields.io/badge/GitHub-Sponsor-ea4aaa?logo=github&style=for-the-badge)](https://github.com/sponsors/mrveiss)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-Tip-blue?logo=ko-fi&style=for-the-badge)](https://ko-fi.com/mrveiss)

---

## Technology Stack

### Frontend
- **Vue 3** — Progressive JavaScript framework
- **TypeScript** — Type safety
- **Vite** — Next-generation build tool
- **Tailwind CSS** — Utility-first styling

### Backend
- **FastAPI** — Modern Python API framework
- **SQLAlchemy** — ORM for database queries
- **Pydantic** — Data validation
- **Claude API / LLM** — AI reasoning engine

### Infrastructure & Orchestration
- **Ansible** — Configuration management
- **Docker** — Container orchestration
- **Kubernetes** support (via Ansible)
- **Terraform** — Infrastructure as code integration

### Data & Search
- **ChromaDB** — Vector database for knowledge bases
- **Redis** — Caching and job queue
- **PostgreSQL** — Primary database (optional)

---

## Roadmap

### Current (v1.5.0)

- ✅ Conversational interface
- ✅ Knowledge base indexing (RAG)
- ✅ Fleet management with Ansible
- ✅ Vision processing
- ✅ Custom workflow creation

### Q2 2026 (v2.0 - Planned)

- 🚀 Web-based workflow editor (drag-and-drop)
- 🚀 Multi-user RBAC (role-based access control)
- 🚀 Incident response automation
- 🚀 Real-time alerting and notifications
- 🚀 Terraform integration (full provider support)

### Under Consideration

- Kubernetes-native operator
- GraphQL API
- Mobile app companion
- Git-based configuration sync
- Advanced telemetry and analytics

---

## License

AutoBot is open source under the [MIT License](./LICENSE).

---

## Status

**Current Version:** v1.5.0  
**Maintenance:** Active development  
**Production Ready:** Yes, for small-to-medium deployments (1-50 servers)  
**Enterprise Ready:** In progress (v2.0 roadmap)

**Use Cases:**
- ✅ DevOps automation for teams
- ✅ SysAdmin efficiency boost
- ✅ Compliance-required self-hosted deployments
- ✅ Air-gapped / offline infrastructure
- 🟡 Enterprise multi-team deployments (v2.0+)

---

## Questions?

- **Docs:** [github.com/mrveiss/AutoBot-AI](https://github.com/mrveiss/AutoBot-AI)
- **Issues:** [Open an issue](https://github.com/mrveiss/AutoBot-AI/issues)
- **Discussions:** [Start a discussion](https://github.com/mrveiss/AutoBot-AI/discussions)

**Built with ❤️ for infrastructure automation.**
