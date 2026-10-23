# User Configuration Guide

Where AutoBot's settings live and how to change them. Reference for every environment variable: [ENV_VARS.md](../developer/ENV_VARS.md).

## Where Settings Live

| What | Where |
|------|-------|
| Infrastructure and admin settings (LLM providers, nodes, security, users, secrets) | **SLM Admin > Settings** |
| Appearance, language, voice | **Preferences**, the cog icon in the main app header ([guide](05-preferences.md)) |
| Environment variables (ports, hosts, feature switches) | Env files, see [Environment files](#environment-files) |
| Backend defaults shipped with the code | `autobot-backend/config.yaml` in the source tree |

The main app's `/settings` address does not open a page in the main app: it sends you to **SLM Admin > Settings**. SLM Admin is at `https://<server>/slm/` on a bare-metal install and `http://localhost/slm/` on Docker (see [Installation](01-installation.md)).

## SLM Admin Settings

SLM Admin > Settings has these sections:

| Section | Covers |
|---------|--------|
| General | System configuration; re-run the Setup Wizard |
| Monitoring, Notifications | Monitoring and alert delivery |
| Security | MFA and API keys |
| API, Backend | API and backend settings |
| Disposal Policy, Findings Policy | Data disposal and findings policies |
| Users | User management (admin) |
| Cache, Prompts, Personality | Cache, prompt and personality settings (admin) |
| Secrets | System secrets (admin) |
| Log Forwarding | Log forwarding (admin) |
| LLM, LLM Fallbacks | LLM providers and their fallback order (admin) |
| Budget Audit, SSO / OIDC, Data Hygiene | Budget audit, single sign-on, data hygiene (admin) |

Admin-only sections need an admin account.

## Choose Your AI Provider

1. Open **SLM Admin > Settings > LLM**.
2. On **Providers**, add or select a provider and set its model, endpoint and API key. Use **Server Settings** for the local Ollama server and **Models** for the model list.
3. Open **LLM Fallbacks** to set what AutoBot tries when the active provider fails.

Ollama is the shipped default provider (`default_provider` and `active_provider` in `autobot-backend/config.yaml`). Cloud providers need only an API key. To run Ollama inside the Docker stack, see [INSTALL.md - Profiles](../../INSTALL.md#profiles).

How AutoBot picks a model per request: [Model Selection Guide](../user/guides/model-selection.md). Fallback behavior: [LLM Model Fallback](../developer/llm-fallback.md).

## GPU

`autobot-backend/config.yaml` ships GPU and Ollama GPU settings (`gpu_enabled`, `gpu_layers`) switched on, with the device priority cuda, openvino, cpu. Driver installation is host software: see [Installation - GPU Acceleration](01-installation.md#gpu-acceleration-optional). Provider and model choice stays in SLM Admin.

## Environment Files

Ports, hosts and feature switches are environment variables, set through env files:

- **Docker**: `docker/.env.docker` is the only Docker env file; per-host secrets go in `docker/.env.secrets` (created by `bash docker/generate-secrets.sh`). Pass both with `--env-file`, as in [INSTALL.md](../../INSTALL.md#docker-deployment).
- **Bare-metal**: the installer writes the real env files. `.env.example` is the annotated reference; `.env.base` plus one overlay (`.env.localhost`, `.env.native-vm`, `.env.network`) is the layout. Details: [ENV_VARS.md - Env-file family](../developer/ENV_VARS.md#env-file-family).
- Generated admin credentials and secrets for a bare-metal install: `/etc/autobot/slm-secrets.env` ([INSTALL.md - Post-Install Structure](../../INSTALL.md#post-install-structure)).

Host keys (`*_HOST`) take a bare host name or IP address with no scheme or port; ports go in the matching `*_PORT` key.

Keep API keys and passwords out of committed files and shared shell profiles: store them in **SLM Admin > Settings > Secrets** or the env files above.

## After Changing Settings

- After editing an env file: Docker, `docker compose ... up -d` again with the same `--env-file` flags; bare-metal, `sudo systemctl restart autobot-slm-backend`.
- Check health with the commands in [Quick Start - Check Health](02-quickstart.md#check-health).
- Problems: [Troubleshooting](04-troubleshooting.md).

## More

- [Environment variable reference](../developer/ENV_VARS.md)
- [Configuration section of the docs](../configuration/_index.md)
- [Port mappings](../guides/PORT_MAPPINGS.md)
