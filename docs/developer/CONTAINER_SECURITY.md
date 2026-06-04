# AutoBot Container Security

Issue #6596: Hardened docker-compose variant
Issue #6597: Semgrep rules + cosign-signed images

---

## Hardened docker-compose (Issue #6596)

`docker-compose.hardened.yml` is an overlay that adds production-grade hardening on top of the default `docker-compose.yml`. It is not used for local development.

### What it adds

| Feature | Base compose | Hardened overlay |
|---------|-------------|-----------------|
| `cap_drop: [ALL]` + minimal `cap_add` | all services | inherited |
| `security_opt: no-new-privileges` | all services | inherited |
| `read_only: true` on filesystem | frontend only | all services |
| Docker Secrets for credentials | plain env vars | postgres password, SLM admin + JWT secret |
| `pids_limit` cap | none | per service |
| Tighter resource limits | base defaults | ~75% of base |

### Prerequisites

Create secret files before first `up`:

```bash
mkdir -p secrets/
printf '%s' "$(openssl rand -hex 32)" > secrets/postgres_password.txt
printf '%s' "$(openssl rand -hex 32)" > secrets/slm_admin_password.txt
printf '%s' "$(openssl rand -hex 32)" > secrets/slm_jwt_secret.txt
chmod 600 secrets/*.txt
echo 'secrets/' >> .gitignore
```

### Usage

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.hardened.yml \
  --env-file docker/.env.docker \
  up -d
```

---

## Cosign container signing (Issue #6597)

AutoBot releases sign each container image so deployers can verify the image
was built by CI and has not been tampered with.

### One-time setup (repo admin)

```bash
# Install cosign
brew install cosign  # or: go install github.com/sigstore/cosign/v2/cmd/cosign@latest

# Generate key pair
cosign generate-key-pair
# writes cosign.key (PRIVATE — never commit) and cosign.pub (commit to repo)

# Add to GitHub Actions secrets:
#   COSIGN_PRIVATE_KEY = $(base64 -w0 cosign.key)
#   COSIGN_PASSWORD    = <passphrase you entered above>

# Commit the public key
git add cosign.pub && git commit -m "chore(security): add cosign public key (#6597)"
```

### Verification (deployers)

```bash
cosign verify --key cosign.pub ghcr.io/mrveiss/autobot-backend:v1.2.3
cosign verify --key cosign.pub ghcr.io/mrveiss/autobot-slm:v1.2.3
cosign verify --key cosign.pub ghcr.io/mrveiss/autobot-frontend:v1.2.3
```

A successful verification prints a JSON payload with the signing certificate and
image digest, confirming the image is authentic.

### CI workflow

`.github/workflows/image-sign.yml` runs on every `v*` tag push:

1. Builds each image (backend, slm, frontend)
2. Pushes to `ghcr.io/mrveiss/<service>:<tag>`
3. Signs the pushed digest with cosign using the private key from Actions secrets
4. Self-verifies the signature using `cosign.pub` from the repo

---

## Semgrep static analysis (Issue #6597)

AutoBot-specific Semgrep rules live in `.semgrep/rules.yaml` and run on every
PR via the Security Scanning CI workflow (`.github/workflows/security.yml`).

### Rules overview (17 total)

The first 12 rules cover general security patterns (injection, deserialization,
JWT misuse, CORS). The 5 new AutoBot-specific rules (added in Issue #6597):

| Rule ID | Severity | What it catches |
|---------|----------|----------------|
| `autobot-direct-aioredis-client-access` | ERROR | Bypasses connection-pool via `_aioredis_client` |
| `autobot-no-print-in-backend` | WARNING | `print()` instead of logger |
| `autobot-pydantic-settings-path-field` | ERROR | Field named `path` reads OS PATH env var |
| `autobot-hardcoded-model-name` | WARNING | Hardcoded LLM model names instead of SSOT constants |
| `autobot-no-console-log-frontend` | WARNING | `console.log` instead of createLogger |

### Adding new rules

Add a new rule block to `.semgrep/rules.yaml`. Follow the existing pattern:
`id`, `pattern`/`patterns`, `message`, `languages`, `severity`, `metadata`.

Run locally:

```bash
python3 -m semgrep --config=.semgrep/rules.yaml autobot-backend/
```
