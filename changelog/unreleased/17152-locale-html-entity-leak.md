---
type: fix
scope: frontend
issue: 17152
pr: 0
---
`autobot-slm-frontend/src/locales/en.json` stored 11 values across 9 keys with raw HTML entities
(`&mdash;`, `&amp;`, `&nbsp;`, `&rarr;`, `&times;`, `&lt;`, `&gt;`) instead of the characters they
name -- every consumer renders through `{{ $t(...) }}`, which escapes its output, so users saw the
literal entity text. Decoded all 11 to real characters; none moved to `v-html`. Added
`repo_tests/locale_html_entity_leak_test.py`, a guard scanning both locale trees (SLM and main
frontend) for any HTML entity in a locale value, with a negative control confirming it catches a
reintroduced one.
