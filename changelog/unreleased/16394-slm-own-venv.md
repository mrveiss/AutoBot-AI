---
type: fix
scope: ci
issue: 16394
pr: 0000
---
`ci.yml`'s `python-shard` job now builds a second, parallel venv for `autobot-slm-backend`'s tests from `autobot-slm-backend/requirements.txt` instead of running them in the shared backend venv, so SLM's tests exercise the `websockets>=17.1,<18` it actually declares and runs in production instead of the `<16` cap `autobot-backend/requirements.txt`'s `langgraph-sdk` forces onto a shared venv. The strict dependency-floor gate is scoped per venv accordingly, and the named `websockets` exemption #16391 carried in `pipeline-scripts/check_dependency_floors.py`'s `KNOWN_CROSS_VENV_EXEMPTIONS` is removed and pinned empty by a test.
