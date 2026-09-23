---
type: security
scope: infra
issue: 15661
pr: 0000
---
`docs/guides/requirements-local.txt` and `autobot-npu-worker/resources/windows-npu-worker/requirements.txt` now state the same fastapi/uvicorn (and redis/structlog) floors every shipped manifest states — both had fallen behind the fastapi security floor (requires starlette ≥0.52.1, the O(n²) Range-header DoS fix). A new guard (`repo_tests/requirements_floor_pairs_15661_test.py`) compares these two known-risky pairs directly, since neither the ansible/requirements parity guard nor the `constraints/shared.txt` drift guard covers either file.
