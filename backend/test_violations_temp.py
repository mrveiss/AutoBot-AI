# Test file with hardcoded values (should be caught by pre-commit hook)

# Hardcoded VM IP (VIOLATION)
BACKEND_URL = "http://172.16.168.20:8001/api"

# Hardcoded port (VIOLATION)
REDIS_URL = "redis://localhost:6379"

# Magic number for limit (VIOLATION)
def search(query: str, limit: int = 10):
    pass

# Magic number for page_size (VIOLATION)
page_size = 50

# Hardcoded role (VIOLATION)
message = {"role": "user", "content": "hello"}

# Hardcoded category (VIOLATION)
category = "general"
search_mode = "hybrid"

# These should NOT be caught (using constants)
from src.constants.threshold_constants import QueryDefaults
limit = QueryDefaults.DEFAULT_SEARCH_LIMIT
