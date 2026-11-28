# Prometheus Scrape Token — Record, Delivery, Rotation (#16375)

The trust boundary is stated in [`THREAT_MODEL.md`](THREAT_MODEL.md) §4: `/api/metrics/prometheus`
admits only this dedicated read-only bearer token, compared with `secrets.compare_digest`; an unset
token refuses every scrape. This page is the operational detail behind that invariant.

Enforcement: [`prometheus_scrape_auth.py`](../../autobot-backend/monitoring/prometheus_scrape_auth.py).

- **Record:** the SLM `SystemSecret` `prometheus_scrape_token`, generated once at SLM startup
  ([`generated_system_secrets.py`](../../autobot-slm-backend/services/generated_system_secrets.py)) and mirrored to the System vault. A
  mirror that failed (vault down at first boot) is retried on every SLM startup.
- **Delivery:** `fetch_deploy_secrets` -> backend role (`AUTOBOT_PROMETHEUS_SCRAPE_TOKEN` in
  `backend.env`) and monitoring role (a root:prometheus 0640 file named by `bearer_token_file`).
  A run that carries no token keeps the deployed one on both sides.
- **Rotation:** in the SLM Secrets UI, update `prometheus_scrape_token` (this also re-mirrors the
  vault copy), then redeploy the **backend** and **monitoring** roles on their nodes. Prometheus
  re-reads the file on each scrape; until both roles have run, scrapes return 401. Nothing
  rotates it automatically, and no agent rotates it on its own (#17038).
- **docker-compose exception (local/dev only):** compose does run an SLM, but nothing delivers SLM
  secrets into compose containers -- there is no ansible run against them. So
  `docker/secrets-init.sh` generates the token into the `autobot_secrets` volume, exports it to the
  backend, and writes Prometheus' copy beside it; the SLM's own `SystemSecret` is a different
  value there and is unused. Recorded in [`ARCHITECTURE_EXCEPTIONS.md`](ARCHITECTURE_EXCEPTIONS.md). To rotate in compose,
  delete the `_GEN_PROMETHEUS_SCRAPE_TOKEN` line from the volume's `autobot.env` and restart.
