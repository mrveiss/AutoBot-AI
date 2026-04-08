# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Centralised API path and endpoint constants.

Issue #3531: Replace hardcoded path strings across the codebase with
named constants so all endpoint paths are defined in one place.
"""

# Health check endpoints
PATH_HEALTH = "/health"
PATH_API_HEALTH = "/api/health"

# Ollama inference endpoints
PATH_OLLAMA_GENERATE = "/api/generate"
PATH_OLLAMA_CHAT = "/api/chat"
PATH_OLLAMA_TAGS = "/api/tags"
