# TTS real-time factor — live host measurement (#12460)

Measured 2026-08-09 against the running `autobot-tts-worker` (pocket-tts,
model_loaded, sample_rate 24000, engine_degraded false), via `POST /tts/synthesize`
with the `alba` voice. Real-time factor = audio-seconds produced / wall-seconds.

## Host load

| | 2026-08-04 (reopen) | 2026-08-09 (now) |
|---|---|---|
| load average | 19.50 / 21.28 / 22.65 | 1.85 / 1.93 / 1.63 |
| cores | 22 | 22 |

The sustained load that starved the worker is gone.

## Real-time factor

| sample | chars | audio (s) | wall (s) | RTF |
|---|---|---|---|---|
| 1 | 12 | 1.12 | 1.15 | 0.97x |
| 2 | 81 | 4.64 | 4.42 | **1.05x** |
| 3 | 192 | 10.00 | 9.54 | **1.05x** |
| 4 | 12 | 1.20 | 1.57 | 0.76x |
| 5 | 81 | 4.08 | 4.19 | 0.97x |
| 6 | 192 | 10.80 | 10.34 | **1.04x** |

Earlier pair, same session: 56 chars → 0.51x; 147 chars → 1.05x.

Compare the reopen: 19 of 19 syntheses between 0.09x and 0.83x, none at or above 1.0x.

## Reading

- **Sentence-length utterances now run at or about real time** (0.97x-1.05x for
  81 and 192 chars). That is the regime chat replies actually use, since the
  frontend dispatches sentence by sentence.
- **Very short utterances sit below 1.0x** (0.76x-0.97x at 12 chars, 0.51x at
  56 chars on a cold worker) because model warm-up dominates a one-second clip.
  This is why the merged backend telemetry measures the factor on steady-state
  generation and reports warm-up separately as time-to-first-audio — a cold
  short clip is not a throughput problem.
- The throughput collapse was **load-driven**, as the reopen hypothesised: the
  TTS process was at ~6.3% CPU, so it was losing the scheduler contest rather
  than saturating. With the host at ~1.9/22 it keeps up.

## Not verified here

The deployed backend still runs pre-merge code — `autobot_tts_realtime_factor`
is absent from its metrics endpoint and the Prometheus query returns empty. So
the merged pre-roll and the `TTSSynthesisBelowRealTime` alert are **not yet
live**; deploying needs the builtin code-sync, which requires credentials this
session does not hold.
