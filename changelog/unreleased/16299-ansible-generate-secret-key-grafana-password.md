---
type: security
scope: deploy
issue: 16299
pr: 0000
---
Generate `backend_secret_key` and `grafana_admin_password` once on first SLM-managed install, replacing the guessable `change-me-in-production`/`admin` role defaults; existing and standalone deployments are unaffected, matching the pattern already used for the DB password and other SLM-generated secrets.
