# Webhook Authentication Security (GH#9657)

## Overview

AutoBot webhooks implement fail-closed authentication to prevent unauthorized request processing. This document describes the security requirements and implementation for all webhook endpoints.

## Security Principle: Fail-Closed Authentication

**Fail-closed** means that when authentication cannot be performed (e.g., secret not configured), the system REJECTS the request rather than processing it.

**Fail-open** (❌ INSECURE) would mean processing the request when authentication fails — this was the vulnerability fixed in GH#9657.

## Webhook Endpoints

### 1. Telegram Bot Webhook (`/api/telegram/webhook`)

**Purpose:** Receives incoming messages from Telegram servers.

**Authentication Method:** Custom header validation

**Configuration:**
```bash
# Stored in Redis via /api/telegram/config endpoint
# Retrieved via get_telegram_webhook_secret()
```

**Authentication Header:**
```
X-Telegram-Bot-Api-Secret-Token: <secret_token>
```

**Security Behavior:**

| Condition | HTTP Status | Behavior |
|-----------|-------------|----------|
| Secret not configured | `503 Service Unavailable` | Fail-closed — reject request |
| Header missing | `401 Unauthorized` | Reject request |
| Header invalid | `403 Forbidden` | Reject request |
| Header valid | `200 OK` | Process webhook |

**Implementation:**
```python
# autobot-backend/api/telegram_bot.py:264-280

stored_secret = await get_telegram_webhook_secret()
if not stored_secret:
    logger.error("Telegram webhook secret not configured - failing closed")
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Webhook authentication not configured",
    )

request_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
if not request_secret:
    logger.warning("Telegram webhook authentication failed - missing secret header")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing authentication header",
    )

if request_secret != stored_secret:
    logger.warning("Telegram webhook authentication failed - invalid secret token")
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
```

### 2. AlertManager Webhook (`/api/webhook/alertmanager`)

**Purpose:** Receives alerts from Prometheus AlertManager.

**Authentication Method:** Custom header validation

**Configuration:**
```bash
# Environment variable
export ALERTMANAGER_WEBHOOK_SECRET="your-secret-here"
```

**Authentication Header:**
```
X-AlertManager-Secret: <secret_value>
```

**Security Behavior:**

| Condition | HTTP Status | Behavior |
|-----------|-------------|----------|
| ALERTMANAGER_WEBHOOK_SECRET not set | `503 Service Unavailable` | Fail-closed — reject request |
| Header missing | `401 Unauthorized` | Reject request |
| Header invalid | `403 Forbidden` | Reject request |
| Header valid | `200 OK` | Process webhook |

**Implementation:**
```python
# autobot-backend/api/alertmanager_webhook.py:42-65

webhook_secret = os.environ.get("ALERTMANAGER_WEBHOOK_SECRET")
if not webhook_secret:
    logger.error("AlertManager webhook secret not configured - failing closed")
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Webhook authentication not configured",
    )

request_secret = request.headers.get("X-AlertManager-Secret")
if not request_secret:
    logger.warning("AlertManager webhook authentication failed - missing secret header")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing authentication header",
    )

if request_secret != webhook_secret:
    logger.warning("AlertManager webhook authentication failed - invalid secret")
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid authentication credentials",
    )
```

## Deployment Requirements

### Telegram Webhook Setup

1. Configure bot token via `/api/telegram/config` endpoint (requires admin auth)
2. Secret is auto-generated (32-byte URL-safe token) and stored in Redis
3. Secret is automatically registered with Telegram API
4. Telegram servers include the secret in `X-Telegram-Bot-Api-Secret-Token` header

### AlertManager Webhook Setup

1. Set `ALERTMANAGER_WEBHOOK_SECRET` environment variable on AutoBot backend
2. Configure AlertManager to include the secret in webhook requests:

```yaml
# alertmanager.yml
receivers:
  - name: 'autobot-alerts'
    webhook_configs:
      - url: 'http://autobot-backend:8001/api/webhook/alertmanager'
        http_config:
          headers:
            X-AlertManager-Secret: '<your-secret-here>'
```

## Security Testing

Comprehensive tests in `autobot-backend/api/webhook_authentication_security_test.py`:

- ✅ Fail-closed when secret not configured (503)
- ✅ Reject when header missing (401)
- ✅ Reject when header invalid (403)
- ✅ Accept when header valid (200)
- ✅ Regression tests to prevent re-introduction of fail-open vulnerability

## Threat Model

### Attacks Prevented

1. **Unauthenticated Webhook Injection**
   - Attacker forges Telegram/AlertManager payloads
   - Prevented by: Required authentication headers

2. **Misconfiguration Exploitation**
   - Webhook deployed without secret configured
   - Prevented by: Fail-closed behavior (503 response)

3. **Replay Attacks**
   - Attacker captures and replays valid webhook
   - Mitigation: Secrets should be rotated regularly (Telegram auto-rotates)

### Known Limitations

1. **No Rate Limiting**
   - Failed authentication attempts are not rate-limited
   - Future enhancement: Add rate limiting per IP/source

2. **No Timestamp Validation**
   - Webhooks don't validate request timestamps
   - Replay attacks are possible within secret rotation window

3. **Secrets in Transit**
   - Secrets transmitted in HTTP headers (HTTPS required)
   - Deployment requirement: TLS/HTTPS for webhook endpoints

## Incident Response

### If Webhook Secret is Compromised

**Telegram:**
1. Regenerate via `/api/telegram/config` with new bot token or webhook URL
2. Old secret becomes invalid immediately
3. Monitor Redis logs for unauthorized attempts

**AlertManager:**
1. Rotate `ALERTMANAGER_WEBHOOK_SECRET` environment variable
2. Update AlertManager configuration with new secret
3. Restart both AutoBot backend and AlertManager
4. Audit logs for timeframe when secret was compromised

### Monitoring

Check logs for authentication failures:

```bash
# Telegram webhook auth failures
grep "Telegram webhook authentication failed" /var/log/autobot/backend.log

# AlertManager webhook auth failures
grep "AlertManager webhook authentication failed" /var/log/autobot/backend.log

# Misconfiguration (fail-closed)
grep "webhook secret not configured" /var/log/autobot/backend.log
```

## Compliance

- **CWE-285:** Improper Authorization (FIXED)
- **CWE--306:** Missing Authentication for Critical Function (FIXED)
- **OWASP A07:2021:** Identification and Authentication Failures (MITIGATED)

## References

- GitHub Issue: #9657 - security(llc): GitHub webhook authentication fails open when secret unset
- Original vulnerability: Telegram webhook returned 200 OK when secret unset
- Security fix: Fail-closed authentication with comprehensive test coverage
- Related: MVA-2074 (Telegram webhook security requirement)
