# Telemetry and Privacy

**Issue #9035** — AutoBot collects anonymous usage data to improve the platform. You can opt out at any time.

## What Data is Collected?

When telemetry is **enabled** (the default), AutoBot collects:

### API Analytics
- **Endpoint paths** — which API endpoints are accessed
- **Response times** — how long requests take (performance monitoring)
- **Status codes** — success/error rates (reliability tracking)
- **Timestamps** — when features are used (usage patterns)

### Voice Session Telemetry
- **Session duration** — how long voice conversations last
- **Token counts** — input/output tokens for cost estimation
- **Audio duration** — seconds of audio input/output
- **Tool call counts** — which voice tools are invoked
- **Estimated costs** — per-session cost tracking

### Feature Usage
- **Which features are used** — analytics dashboards, knowledge base, workflows, etc.
- **Frequency of use** — how often features are accessed
- **Error patterns** — which operations fail and how often

## What We Do NOT Collect

AutoBot **never** collects:

- ❌ Personal information (usernames, emails, passwords)
- ❌ Authentication tokens or API keys
- ❌ Code content, prompts, or chat messages
- ❌ File paths, hostnames, or IP addresses
- ❌ Any data that could identify individual users
- ❌ Data from air-gapped or private deployments when opted out

## How to Opt Out

### Via Settings UI

1. Navigate to **Settings** → **Privacy** tab
2. Toggle **"Send Anonymous Usage Statistics"** to **Disabled**
3. Your preference is saved immediately

When telemetry is disabled:
- All API call tracking stops
- Voice session data is kept in-memory only (for cap enforcement) and never persisted
- No outbound analytics calls are made

### Via Environment Variable

Set the following in your `.env` file:

```bash
AUTOBOT_TELEMETRY_ENABLED=false
AUTOBOT_TELEMETRY_ANONYMOUS_USAGE_STATS=false
```

Restart the backend for the change to take effect.

### Via Configuration File

Edit `config/config.yaml`:

```yaml
telemetry:
  enabled: false
  anonymous_usage_stats: false
```

Restart the backend for the change to take effect.

## Technical Implementation

### Backend

When `config.telemetry.enabled` is `False`:

- **AnalyticsMiddleware** (`autobot-backend/middleware/analytics_middleware.py`) skips API call tracking
- **VoiceRealtimeTelemetry** (`autobot-backend/services/voice_realtime_telemetry.py`) uses in-memory session records only
- No data is written to the Redis analytics database
- Response headers indicate `X-Tracked-Analytics: false`

### Frontend

The telemetry settings panel (`autobot-frontend/src/components/settings/TelemetrySettingsPanel.vue`) provides:

- Toggle to enable/disable telemetry
- Detailed disclosure of what data is collected
- Immediate API call to persist the preference

## Privacy for Air-Gapped Deployments

For fully isolated, air-gapped deployments:

1. Set `AUTOBOT_TELEMETRY_ENABLED=false` in your deployment configuration
2. No telemetry data will be collected or transmitted
3. All features continue to work normally
4. Voice session caps still enforce (in-memory tracking only)

## Data Retention

When telemetry is enabled:

- **API analytics** — retained for 90 days in Redis
- **Voice sessions** — retained for configured TTL (default: 7 days)
- **Aggregated metrics** — retained indefinitely for platform improvements

## Questions?

For privacy-related questions or concerns, please open an issue on GitHub or contact the maintainer at the email listed in the repository.

## Related Issues

- [#9035](https://github.com/mrveiss/AutoBot-AI/issues/9035) — feat(admin): telemetry and analytics opt-out

---

**Last Updated:** 2026-06-04  
**Author:** mrveiss
