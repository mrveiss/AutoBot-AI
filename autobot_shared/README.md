# AutoBot Shared Utilities

Shared utilities deployed with each backend component.

## Deployment

This module is included in each backend's deployment:
- autobot-user-backend
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
