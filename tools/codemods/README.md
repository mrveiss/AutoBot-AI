# tools/codemods

One-shot code transformation scripts ("codemods") promoted from `/tmp` to
this directory so they can be reviewed, tested, and reused.

## When to add a codemod here

You're doing a bulk edit across N+ files with the same mechanical shape —
e.g. "replace every `parseApiResponse<T>(x)` wrapper with its inner
`apiClient.get<T>(url)` call". The Edit tool requires unique `old_string`,
which makes N-site rewrites per-Edit painful; a script is faster, and with
tests it's safer.

Put the script here (not `/tmp`) if **any** of these apply:

- The same transform will run more than once (e.g. a migration happening in
  batches across weeks)
- The pattern is non-trivial (multi-line, nested, shared subtleties)
- You want the diff to be reviewable as-code, not just as-output
- Future sessions (yours or a teammate's) will need the same tool

Discovered during session work — every session seems to need at least one
bulk-edit script, and they've all been thrown away. See #5150 for the
historical context.

## Structure

Each codemod is **two files** in this directory:

- `<transform>.py` — the transform itself. Takes one-or-more file paths as
  CLI args. Reads → transforms → writes in place. Prints a per-file count.
  Exit 0 always.
- `test_<transform>.py` — pytest tests with before/after fixture strings
  embedded as triple-quoted multi-line constants. Asserts the transform
  produces the exact expected output.

## Running

Transforms run directly as Python scripts (no install needed):

```bash
python3 tools/codemods/parse_api_response_vue_migration.py \
  $(grep -rln "parseApiResponse" autobot-frontend/src/components --include='*.vue')
```

Tests run with pytest:

```bash
cd tools/codemods
python3 -m pytest -xvs
```

## Future direction

For AST-aware transforms (not just regex), prefer
[ts-morph](https://ts-morph.com/) (TypeScript) or
[libcst](https://libcst.readthedocs.io/) (Python). Regex is fine for the
shallow migrations we've needed so far; add AST tooling when a regex
misfires — #5150 argued for this after two iterations on `cleanup_5092.py`.

## Reference codemods

- `parse_api_response_vue_migration.py` — removes `parseApiResponse<T>(x)`
  wrapper lines by typing the preceding `apiClient.METHOD(url)` call
  directly. Used in PR #5177 to migrate 49 call sites across 17 Vue files.
  Proven working on multi-line `apiClient.post(url, { ... })` bodies by
  patching only the opener line.
