# Quick Start Guide

Get started with AutoBot after you have completed the [Installation Guide](01-installation.md). AutoBot runs as a service once installed: there is nothing to launch by hand.

## Open AutoBot

### Bare-metal install (`install.sh`)

1. Open `https://<server>/slm/` in your browser, where `<server>` is the host you installed on.
2. Accept the self-signed certificate warning.
3. Log in as `admin` with the password the installer printed (also saved in `/root/autobot-credentials.txt`).
4. On first login the Setup Wizard starts. Follow it to add nodes and assign roles; see [INSTALL.md - Setup Wizard](../../INSTALL.md#setup-wizard).

### Docker install

1. Check that the containers are up: `docker compose --env-file docker/.env.docker --env-file docker/.env.secrets ps`.
2. Open http://localhost for the main app, or http://localhost/slm/ for SLM Admin.
3. Log in as `admin`. The password is `AUTOBOT_ADMIN_PASSWORD` in `docker/.env.secrets`:

   ```bash
   grep '^AUTOBOT_ADMIN_PASSWORD=' docker/.env.secrets
   ```

   Change it after the first login.

If you started only the SLM GUI (`--profile slm`), http://localhost/slm/ is the only page; add the rest from the Setup Wizard.

## Check Health

| Install mode | Command | What it reaches |
|--------------|---------|-----------------|
| Bare-metal | `curl -sk https://127.0.0.1/slm/api/health` | SLM backend, through nginx |
| Bare-metal | `curl -sk https://127.0.0.1/api/system/health` | Main backend, once the Setup Wizard has provisioned it |
| Docker (full stack) | `curl -s http://localhost/api/system/health` | Backend, through the frontend proxy |
| Docker (`--profile slm`) | `curl -s http://localhost/slm/api/health` | SLM backend |

Do not use `localhost:8001` on a Docker host: the backend publishes no host port, and host port 8001 is RedisInsight.

Service status and logs on bare-metal: `systemctl status autobot-slm-backend`, `journalctl -u autobot-slm-backend -f`. On Docker: `docker compose --env-file docker/.env.docker --env-file docker/.env.secrets logs -f --tail=50`.

## Find Your Way Around

The top navigation of the main app has **Home**, **Chat**, **Knowledge** and **Company OS**; **Automation** and **Analytics** appear with the advanced views. **Preferences** (appearance, language, voice) is the cog icon at the right of the header; see the [Preferences guide](05-preferences.md).

Infrastructure and admin settings (LLM providers, nodes, security, users) live in SLM Admin, not in the main app. See the [Configuration Guide](03-configuration.md).

## Your First Conversation

Open **Chat** and try:

```text
Hello! What can you help me with?
```

```text
Remember that Python is my preferred programming language
```

```text
What do you know about Python?
```

When AutoBot wants to run a system command that needs approval, the chat shows the command in an approval card; review it before approving.

More: [Chat Interface guide](../user/guides/chat-interface.md), [Working with Agents](../user/guides/working-with-agents.md).

## Knowledge Base

Open **Knowledge** to browse (Knowledge Browser), add and edit entries (Manage Knowledge), read System Docs, and run Research. Guide: [Knowledge Management](../user/guides/knowledge-management.md) and the [Knowledge quick start](../user/quick-start-knowledge.md).

## Getting Help

- Troubleshooting: [04-troubleshooting.md](04-troubleshooting.md)
- Install problems: [INSTALL.md - Troubleshooting](../../INSTALL.md#troubleshooting)
- Report bugs: https://github.com/mrveiss/AutoBot-AI/issues

## Next Steps

1. [Configuration Guide](03-configuration.md): choose an LLM provider and where settings live
2. [User guides](../user/README.md): chat, knowledge, workflows, Company OS and more
