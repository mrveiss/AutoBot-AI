# CVE Monitoring - Unpatched Transitive Dependencies

This document tracks CVEs in transitive dependencies where no upstream fix is available. Each entry records the current status, action to take when a fix lands, and the 90-day escalation date.

---

## diskcache — Deserialization Vulnerability

| Field | Value |
|---|---|
| Package | `diskcache` |
| Role | Transitive dependency (pulled in by LlamaIndex/llama-index-core) |
| Vulnerable range | All published releases as of 2026-04-08 (latest: 5.6.3) |
| Dependabot alert | #278 — deserialization of untrusted data |
| Severity | Medium — exploitable only if attacker can write to cache directory |
| First observed | 2026-03-11 (security remediation plan) |
| Dismissed | 2026-04-04 (tolerable_risk) |
| 90-day escalation | 2026-07-07 |
| Tracking issue | https://github.com/mrveiss/AutoBot-AI/issues/3446 |

### Exposure Assessment

`diskcache` is **not imported anywhere** in AutoBot Python source code. It is pulled in transitively (e.g., by LlamaIndex). AutoBot does not pass attacker-controlled data into a diskcache `Cache` object. Exploitation requires write access to the cache directory, which is restricted by OS permissions on deployment VMs.

### Action When Fix Published

1. Identify the first patched version on the [diskcache PyPI page](https://pypi.org/project/diskcache/#history)
2. Add explicit floor pin to `requirements.txt`:
   ```
   diskcache>=<patched_version>
   ```
3. Run `pip install -r requirements.txt` in dev environment, confirm no conflicts with LlamaIndex
4. Close issue #3446

### Escalation Path (No Fix by 2026-07-07)

Audit whether LlamaIndex still requires diskcache. If it does and no patch exists:
- Evaluate replacing the affected LlamaIndex component
- OR: Implement custom cache backend avoiding vulnerable serialization path