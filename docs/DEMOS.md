# AutoBot Demos & Visual Materials

Visual guides and demo walkthroughs for AutoBot's features.

---

## Quick Start Demo

The fastest way to see AutoBot in action is the 3-step Docker setup:

```
1. git clone https://github.com/mrveiss/AutoBot-AI.git
   └── Clone the repository

2. cp .env.example .env && docker compose up -d
   └── Configure and start all services (~2 minutes)

3. Open http://localhost
   └── AutoBot dashboard is ready
```

From first command to working dashboard: **under 5 minutes** on a modern machine.

---

## Feature Walkthroughs

### Chat Interface

```
Open dashboard → Click "New Chat" → Type a message

Example queries:
  "What's the status of my fleet?"
  "Summarize the deployment runbook"
  "Help me write an Ansible playbook for nginx restart"
```

AutoBot streams responses in real-time. Attach a knowledge base via the KB icon
to ground answers in your own documentation.

---

### Knowledge Base Setup

```
Sidebar → Knowledge Bases → New Knowledge Base
  → Name it (e.g. "Production Runbooks")
  → Upload documents (PDF, Markdown, text, code files)
  → Documents are indexed in seconds

Then in Chat:
  → Click KB icon → Select "Production Runbooks"
  → Ask questions about your documents
```

---

### Fleet Management

```
Sidebar → Fleet → Add Node
  → Enter hostname / IP and SSH user
  → Copy AutoBot's SSH public key to the node
  → AutoBot tests connection and enrolls the node

Once enrolled:
  → View real-time CPU / RAM / disk per node
  → Run playbooks: update packages, restart services, check disk
  → Or use Chat: "Restart nginx on all web servers"
```

---

### Workflow Builder

```
Sidebar → Workflows → New Workflow
  → Add steps (chat prompt, fleet op, KB query, delay)
  → Connect steps in sequence
  → Save with a name and optional cron schedule

Example — Weekly Health Check:
  Step 1: Fleet → Run "check-disk-usage" on all nodes
  Step 2: Chat → "Summarize disk usage, flag nodes above 80%"
  Step 3: Chat → "Write a Slack-ready status summary"
```

---

## Architecture Diagrams

Full Mermaid diagrams covering system overview, data flows, and deployment topologies:

- [System Diagrams](architecture/system-diagram.md)

Key diagrams:
- **System Overview** — All components and how they connect
- **Chat Data Flow** — Sequence diagram from user message to streamed response
- **Fleet Operation Flow** — How a chat command becomes an Ansible playbook run
- **Single-node topology** — Standard Docker Compose layout
- **Multi-node HA topology** — Production high-availability setup

---

## Recording Your Own Demo

To create a terminal recording (e.g. for a blog post or PR description):

```bash
# Install tools
sudo apt install asciinema
pip install agg  # or: npm install -g @asciinema/agg

# Record
asciinema rec demo.cast

# Inside the recording:
git clone https://github.com/mrveiss/AutoBot-AI.git
cd AutoBot-AI
cp .env.example .env
docker compose up -d
curl http://localhost/api/v1/health

# Exit recording (Ctrl+D or exit)

# Convert to GIF
agg demo.cast demo.gif
```

Suggested recording script for a clean quickstart demo:

```bash
echo "=== AutoBot Quickstart Demo ===" && sleep 1
git clone https://github.com/mrveiss/AutoBot-AI.git && sleep 0.5
cd AutoBot-AI && sleep 0.5
cp .env.example .env && echo "Config ready" && sleep 0.5
docker compose up -d && sleep 2
docker compose ps && sleep 1
curl -s http://localhost/api/v1/health | python3 -m json.tool
echo "✓ AutoBot is running at http://localhost"
```

---

## Screenshots

To take clean screenshots for documentation or social media:

1. Start AutoBot: `docker compose up -d`
2. Open `http://localhost` in a browser
3. Recommended views to capture:
   - Chat interface with a sample conversation
   - Knowledge Base document list
   - Fleet dashboard with nodes
   - Workflow builder canvas
4. Use browser devtools to set viewport to 1440×900 for consistent sizing

---

## Embedding in README or Docs

To embed a GIF in a markdown file:

```markdown
![AutoBot Quickstart](docs/demos/quickstart-demo.gif)
```

To embed a Mermaid diagram (renders on GitHub):

```markdown
​```mermaid
graph TB
    ...
​```
```

---

## Contributing Demos

Have a demo or screenshot that showcases AutoBot well? Contributions welcome:

1. Add your demo file to `docs/demos/` (GIF, MP4, or PNG)
2. Add a description to this file under the appropriate section
3. Open a PR targeting `Dev_new_gui`
