---
type: fix
scope: sdk
issue: 15528
pr: 0
---
The TypeScript SDK now matches the routes it calls: `sessions.list` sends `scope`/`team_id`, `knowledge.search` is a POST with a JSON body, `analytics.usage`/`performance` take no arguments, and several responses are modeled as the flat documents the backend actually returns rather than invented envelopes. It also gained the `/api` prefix every request needs, which it was missing entirely (#16495) — the same defect #15053 already found once in the Python package. `repo_tests/sdk_ts_request_contract_test.py` pins both packages' requests against the same backend-derived oracle `sdk_request_url_test.py` uses for Python.
