# TEMPORARY PATCH: Redis timeout fix for deadlock prevention
# This fixes socket_timeout from 30s to 2s as per CLAUDE.md documentation

import os

# Set Redis timeout to 2 seconds to prevent blocking
os.environ["REDIS_SOCKET_TIMEOUT"] = "2"
os.environ["REDIS_CONNECTION_TIMEOUT"] = "2"

# Import the original module after setting environment variables
from src.utils.redis_database_manager import *