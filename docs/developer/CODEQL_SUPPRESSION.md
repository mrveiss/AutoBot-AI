# Static-Analysis False-Positive Suppression — How It Actually Works

> Covers **CodeQL** (most of this file) and **Semgrep** (see the second-engine
> section near the end). The filename stays `CODEQL_SUPPRESSION.md` because
> `.github/codeql/codeql-config.yml` links to it by path.

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

## Semgrep is a second engine, and it ignores CodeQL suppressions (#13519)

The 2026-08-03 batch made this concrete. Six `filesystem_mcp.py` sites carried
`# codeql[py/path-injection]` markers, and a **Semgrep** rule ("Path Manipulation
with aiofiles via fastapi") reported them anyway.

That is expected — CodeQL suppression syntax means nothing to Semgrep — but it
means **a suppression strategy that covers only one engine looks like it is
working while doing nothing.** Any decision to suppress must state which engine
it applies to.

Semgrep in CI runs **only** `.semgrep/rules.yaml`
([`security.yml`](../../.github/workflows/security.yml)); the community and Pro
configs need `SEMGREP_APP_TOKEN` and are unavailable there. So a batch citing
rule names absent from that file did **not** come from this repo's CI, and cannot
be tuned by editing anything in this repo. Tuning belongs in the platform policy
that produced it.

### Known systematic misfire: FastAPI SQL-injection rules vs SQLAlchemy Core

**33 of 33 findings in the 2026-08-03 SQLi batch were false positives.** Every
site executed a SQLAlchemy 2.0 Core/ORM construct — `select()` / `update()` /
`delete()` assembled with `.where()`, `.order_by()`, `.offset()`, `.limit()`. No
site built SQL by concatenation or f-string; all request-derived values arrive as
**bound parameters** via the SQLAlchemy compiler.

The rule fires on the shape `value_from_Query(...) → … → db.execute(var)`. Because
the query is assembled across several statements (`query = select(...)`, then
`query = query.where(...)`), the taint tracker loses the fact that the sink is a
typed expression tree rather than a string, and reports the `db.execute(query)`
line. **This codebase uses that idiom almost universally**, so the rule produces a
full batch of false positives on every scan.

The clearest evidence it matches on *shape* rather than on SQL construction:
`autobot-backend/api/database_mcp.py` is the only file in either backend that
genuinely builds SQL by string interpolation on a raw `sqlite3` cursor — and it
was **absent** from the 33. 33 reports on safe ORM code, zero on the one
string-SQL file.

**Triage this rule family as a batch, not site by site.** A finding against it is
only interesting if the sink receives a `str`/f-string rather than a construct —
which is the one thing to check before spending time on it.

### Point scans at `Dev_new_gui`, not `main`

The same batch was scanned against `main`, then ~682 commits behind
`Dev_new_gui`, so **every line number had to be re-located by content search**.
Three `code_sync.py` findings landed on a function signature, a `return False`
and a docstring — lines with no path expression at all. `main` is a strict
ancestor of `Dev_new_gui`; scanning it reports on code no one is running.

## References

- GitHub Docs — *Resolving code scanning alerts* (dismiss via UI/REST API).
- GitHub Docs — *Customizing your advanced setup for code scanning* (`query-filters`, `paths-ignore`).
- GitHub Changelog — *LGTM.com deprecation and shutdown* (December 2022).
