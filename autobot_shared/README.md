# AutoBot Shared Utilities

Shared utilities deployed with each backend component.

## Deployment

This module is included in each backend's deployment:
- autobot-backend
- autobot-slm-backend
- autobot-npu-worker
- autobot-browser-worker

## Usage

```python
from autobot_shared.redis_client import get_redis_client
from autobot_shared.ssot_config import config
```

## Contents

| File | Purpose |
|------|---------|
| `redis_client.py` | Redis connection management |
| `http_client.py` | HTTP client utilities |
| `logging_manager.py` | Centralized logging |
| `error_boundaries.py` | Error handling |
| `ssot_config.py` | SSOT configuration |

## Local Testing

`autobot_shared` uses the canonical pytest layout but the `from autobot_shared.X import Y`
imports inside test files require `autobot_shared` to be importable as a package — which
needs the **repo root** on `sys.path`.

### Recommended (matches CI):

```bash
# From repo root — autobot_shared resolves as a package via cwd
cd <repo-root>
python3 -m pytest autobot_shared/
```

### Editable install (run from anywhere):

```bash
pip install -e ./autobot_shared[test]
pytest autobot_shared/
```

### Common error and fix:

```
ImportError: cannot import name 'get_async_redis_client' from 'autobot_shared.redis_client'
```

This means pytest was invoked from inside `autobot_shared/` — pytest's rootdir doesn't put the
parent on `sys.path`, so `autobot_shared` is not importable as a package. Re-run from repo
root, or use the editable install above. (Tracked in #7175.)
