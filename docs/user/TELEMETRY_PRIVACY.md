# Local Usage Metrics and Privacy

**Issue #9035** — AutoBot can record anonymous operational metrics **locally** to power your own
monitoring dashboards. This data stays entirely on your infrastructure and is **never transmitted
to AutoBot or any third party**. You can disable recording at any time.

## What Data is Recorded?

When recording is **enabled** (the default), AutoBot stores the following in your **local Redis**:

### API Analytics
- **Endpoint paths** — which API endpoints are accessed
- **Response times** — how long requests take (performance monitoring)
- **Status codes** — success/error rates (reliability tracking)
- **Timestamps** — when features are used (usage patterns)

### Voice Session Metrics
- **Session duration** — how long voice conversations last
- **Token counts** — input/output tokens for cost estimation
- **Audio duration** — seconds of audio input/output
- **Tool call counts** — which voice tools are invoked
- **Estimated costs** — per-session cost tracking

### Feature Usage
- **Which features are used** — analytics dashboards, knowledge base, workflows, etc.
- **Frequency of use** — how often features are accessed
- **Error patterns** — which operations fail and how often

## What is Never Recorded

AutoBot **never** records:

- ❌ Personal information (usernames, emails, passwords)
- ❌ Authentication tokens or API keys
- ❌ Code content, prompts, or chat messages
- ❌ File paths, hostnames, or IP addresses
- ❌ Any data that could identify individual users

And, regardless of this setting, AutoBot **never sends any of this data off your infrastructure** —
there are no outbound analytics calls at all.

## How to Disable Recording

### Via Settings UI

1. Navigate to **Settings** → **Privacy** tab
2. Toggle **"Record Local Usage Metrics"** to **Disabled**
3. Your preference is saved immediately

When recording is disabled:
- All API call tracking stops
- Voice session data is kept in-memory only (for cap enforcement) and never persisted
- Nothing is written to the local Redis analytics database

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

When enabled, all records are stored in the operator's **local Redis** (`analytics` database) with a
TTL. No component makes any outbound network call to transmit this data.

### Frontend

The local usage metrics panel (`autobot-frontend/src/components/settings/TelemetrySettingsPanel.vue`) provides:

- Toggle to enable/disable local recording
- Detailed disclosure of what is recorded locally
- Immediate API call to persist the preference

## Air-Gapped Deployments

Because nothing is ever transmitted, AutoBot's local metrics are fully compatible with air-gapped,
isolated deployments. To disable local recording entirely:

1. Set `AUTOBOT_TELEMETRY_ENABLED=false` in your deployment configuration
2. No metrics will be recorded
3. All features continue to work normally
4. Voice session caps still enforce (in-memory tracking only)

## Data Retention

When recording is enabled (all data is local):

- **API analytics** — retained for 90 days in your Redis
- **Voice sessions** — retained for configured TTL (default: 7 days)
- **Aggregated metrics** — retained for your own historical dashboards

## Questions?

For privacy-related questions or concerns, please open an issue on GitHub or contact the maintainer at the email listed in the repository.

## Related Issues

- [#9035](https://github.com/mrveiss/AutoBot-AI/issues/9035) — feat(admin): local usage metrics opt-out

---

**Last Updated:** 2026-06-08  
**Author:** mrveiss
