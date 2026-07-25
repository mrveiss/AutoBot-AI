# CodeQL False-Positive Suppression — How It Actually Works

> **TL;DR:** Inline `# codeql[query-id]` / `# lgtm[query-id]` comments do **not**
> dismiss GitHub code-scanning alerts in this repository. They are non-functional.
> Reviewed false positives are suppressed by **dismissing the alert** (Security tab
> or REST API) or by a **`query-filters` / `paths-ignore` exclusion** in
> `.github/codeql/codeql-config.yml`. See #12307.

## Why the inline comments never worked

`// lgtm[...]` (and the newer `// codeql[...]`) inline suppression comments were a
feature of **LGTM.com**, which was retired in **December 2022**. GitHub code
scanning — the pipeline this repo runs via `github/codeql-action` in
[`.github/workflows/codeql.yml`](../../.github/workflows/codeql.yml) — does **not**
propagate inline-comment suppressions to alert state. The CodeQL CLI's
alert-suppression queries only affect alert state when you run
`codeql database analyze` and interpret the SARIF yourself; the hosted
code-scanning action does not.

Result: an alert whose sink line carries `# codeql[py/clear-text-logging-sensitive-data]`
still appears as **Open** on the Security tab. This was proven on alert #689
(`context_window_manager.py`) — it carried the comment yet stayed open. All 93
`py/clear-text-logging-sensitive-data` alerts were ultimately resolved by **API
dismissal** in #12280, not by the inline comments.

## The three mechanisms that DO work

| Granularity | Mechanism | Persists? | Suppresses future alerts? |
|---|---|---|---|
| Per-alert (one line) | Dismiss via Security tab or REST API | Yes — matched across runs by fingerprint | No — only that reviewed alert |
| Per-query / per-path | `query-filters` / `paths-ignore` in `codeql-config.yml` | Yes | **Yes** — also hides future alerts of that query in that path |
| Root cause | Fix the sink (don't log/store the sensitive value) | N/A | N/A |

### 1. Per-alert dismissal (use this for line-level FPs)

Use for `py/clear-text-logging-sensitive-data` false positives where the logged
value is not actually sensitive (a model name, a file path, a masked phone number,
a secret's *label* rather than its value, a generic message, a caught exception).

- **UI:** Security → Code scanning → the alert → **Dismiss alert → "Used in tests" /
  "Won't fix" / "False positive"**.
- **API:**

  ```bash
  gh api -X PATCH \
    /repos/{owner}/{repo}/code-scanning/alerts/{alert_number} \
    -f state=dismissed -f dismissed_reason="false positive" \
    -f dismissed_comment="Logged value is a model name, not sensitive. Reviewed <issue>."
  ```

Dismissals are matched to the same alert on later runs by CodeQL's location
fingerprint, so they **stick** while genuinely new/unreviewed alerts still surface.

### 2. `query-filters` / `paths-ignore` (use for whole-query or whole-file FPs)

Use only when the **entire** query is a FP for the **entire** path — e.g. a file
that centralizes validated I/O. See the existing entries in
[`.github/codeql/codeql-config.yml`](../../.github/codeql/codeql-config.yml) for
`py/full-ssrf` (`external_importer.py`) and `py/path-injection`
(`upload_security.py`). This is coarser: it also hides **future** alerts of that
query in that path, so document the justification inline in the config.

### 3. Fix the sink

If the data is genuinely sensitive, don't suppress — remove it from the log/store
or mask it.

## Workflow for a new false positive

1. Confirm it is a FP (the flagged value is not sensitive).
2. **Dismiss the alert** (API/UI) with a comment citing the reviewing issue/PR.
3. Do **not** add an inline `# codeql[...]` comment — it does nothing here.

## About the existing inline markers

~69 legacy inline `# codeql[...]` / `# lgtm[...]` markers remain across ~33 files.
They **do not suppress anything**; the corresponding alerts were dismissed via the
API in #12280. Treat them as historical human annotations only. **Do not add new
ones.** Removing an existing one is a deliberate follow-up task, not a drive-by
edit: altering or deleting a marked line changes the alert's location fingerprint
and can transiently **re-open** the dismissed alert until it is re-dismissed.

## References

- GitHub Docs — *Resolving code scanning alerts* (dismiss via UI/REST API).
- GitHub Docs — *Customizing your advanced setup for code scanning* (`query-filters`, `paths-ignore`).
- GitHub Changelog — *LGTM.com deprecation and shutdown* (December 2022).
