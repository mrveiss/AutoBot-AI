#!/bin/bash
#
# Script to create GitHub issues for centralization project
# Requires: gh CLI (GitHub CLI) - Install with: sudo apt install gh
#
# Usage: ./create_github_issues.sh
#

set -e

echo "🚀 Creating GitHub Issues for Centralization Project"
echo "=================================================="
echo ""

# Check if gh is installed
if ! command -v gh &> /dev/null; then
    echo "❌ Error: GitHub CLI (gh) is not installed"
    echo ""
    echo "Install with:"
    echo "  sudo apt update"
    echo "  sudo apt install gh"
    echo ""
    echo "Then authenticate:"
    echo "  gh auth login"
    exit 1
fi

# Check if authenticated
if ! gh auth status &> /dev/null; then
    echo "❌ Error: Not authenticated with GitHub"
    echo ""
    echo "Authenticate with:"
    echo "  gh auth login"
    exit 1
fi

echo "✅ GitHub CLI is installed and authenticated"
echo ""

# Issue #1: Redis Managers
echo "Creating Issue #1: Redis Managers..."
gh issue create \
  --title "🔴 P1: Consolidate Redis Managers (8-12 hours)" \
  --label "refactoring,technical-debt,priority: critical,component: redis" \
  --body "## ⚠️ CRITICAL: Feature Preservation & Code Management

**MANDATORY POLICY:**

### Feature Preservation:
- ✅ **Audit ALL 7 implementations thoroughly** - Each may have unique connection pooling, error handling, retry logic
- ✅ **Merge the BEST features** from all implementations - Do not arbitrarily pick one
- ✅ **Document feature sources** - Track which features came from which file
- ❌ **NEVER assume one implementation is superior** without analysis

### File Naming (PERMANENT NAMES):
- ✅ **Use permanent file name**: \`redis_client.py\` (DO NOT rename to \`redis_client_consolidated.py\`)
- ❌ **NO temporary qualifiers**: \`*_fix.py\`, \`*_refactored.py\`, \`*_new.py\`, \`*_v2.py\`

### Code Archival (NO DELETION):
- ✅ **ARCHIVE old code** to \`archives/2025-11-11_redis_consolidation/\` using \`git mv\`
- ✅ **Document archival** in archives README
- ❌ **NEVER delete** old implementations - always archive first

---

## Problem
7 different Redis manager implementations exist across the codebase, causing code duplication (~2,000 lines), inconsistent error handling, and maintenance burden.

## Files Affected
1. \`backend/utils/async_redis_manager.py\` (31,053 bytes) - Full async Redis wrapper
2. \`src/utils/async_redis_manager.py\` (11,182 bytes) - Duplicate async manager
3. \`src/utils/optimized_redis_manager.py\` (6,031 bytes) - Performance-optimized wrapper
4. \`src/utils/redis_database_manager.py\` (15,149 bytes) - Database-specific management
5. \`src/utils/redis_helper.py\` (5,604 bytes) - Utility functions
6. \`backend/services/redis_service_manager.py\` - Service-layer management
7. \`backend/utils/async_redis_manager_DEPRECATED.py\` - Already deprecated

## Canonical Pattern
\`src/utils/redis_client.py::get_redis_client()\` - Already used by 5 migrated files

## Recommended Approach
1. **AUDIT**: Create feature comparison matrix for all 7 implementations
2. **IDENTIFY**: Unique features (connection pooling, error handling, retry logic, circuit breakers)
3. **MERGE**: Best features into \`src/utils/redis_client.py\`
4. **DOCUMENT**: Which features came from which file in migration guide
5. Create migration guide showing before/after for each pattern
6. Update all consumers to use \`get_redis_client()\`
7. Mark old files as deprecated with runtime warnings
8. Schedule removal in future release

## Benefits
- Single source of truth for Redis connections
- Centralized circuit breaker, retry logic, metrics
- Consistent error handling across all components
- Reduced maintenance burden (update 1 file instead of 7)

## Acceptance Criteria
- [ ] **Feature comparison matrix created** for all 7 implementations
- [ ] **All unique features identified** and best features selected
- [ ] All unique features from 7 implementations merged into canonical
- [ ] **Canonical file uses permanent name** (\`redis_client.py\` - no \"_consolidated\", \"_refactored\", etc.)
- [ ] **Documentation of feature sources** (which features came from which file)
- [ ] Migration guide created (similar to REDIS_CENTRALIZATION_AUDIT.md)
- [ ] All consumers updated to use \`get_redis_client()\`
- [ ] **Old implementations archived** to \`archives/2025-11-11_redis_consolidation/\` using \`git mv\`
- [ ] **Archival documented** in archives README
- [ ] Tests passing for all migrated code
- [ ] Documentation updated with feature provenance

## Estimated Effort
8-12 hours

## Related
- ✅ Phase 1 Complete: 5 files already migrated (auth, llm, app_factory, knowledge_base)
- See: REDIS_CENTRALIZATION_AUDIT.md"

echo "✅ Issue #1 created"
echo ""

# Issue #2: Config Managers
echo "Creating Issue #2: Config Managers..."
gh issue create \
  --title "🔴 P2: Consolidate Configuration Managers (10-15 hours)" \
  --label "refactoring,technical-debt,priority: high,component: config" \
  --body "## ⚠️ CRITICAL: Feature Preservation & Code Management

**MANDATORY POLICY:**

### Feature Preservation:
- ✅ **Audit ALL 7 config systems** - Each may support different config sources (env, files, K8s, database)
- ✅ **Merge the BEST features** - Legacy config.py (42KB) likely has features not in newer versions
- ✅ **Document feature sources** - Track which capabilities came from which file
- ❌ **NEVER pick one arbitrarily** - Must preserve best from all

### File Naming (PERMANENT NAMES):
- ✅ **Use permanent file name**: Choose stable name like \`config_manager.py\` or \`unified_config.py\`
- ❌ **NO temporary qualifiers**: \`*_fix.py\`, \`*_refactored.py\`, \`*_new.py\`, \`*_v2.py\`, \`*_consolidated.py\`

### Code Archival (NO DELETION):
- ✅ **ARCHIVE old code** to \`archives/2025-11-11_config_consolidation/\` using \`git mv\`
- ✅ **Document archival** in archives README
- ❌ **NEVER delete** old implementations - always archive first

---

## Problem
7 different configuration systems exist, causing configuration drift (~3,000 duplicate lines), hard to maintain, and unclear which to use.

## Files Affected
1. \`src/config.py\` (41,985 bytes) - Legacy configuration system
2. \`src/unified_config.py\` (21,581 bytes) - Unified configuration interface
3. \`src/unified_config_manager.py\` (36,161 bytes) - Manager for unified config
4. \`src/config_consolidated.py\` (17,930 bytes) - Consolidated config attempt
5. \`src/async_config_manager.py\` (17,079 bytes) - Async configuration loading
6. \`src/config_helper.py\` (15,658 bytes) - Helper utilities for config
7. \`src/utils/config_manager.py\` - Utility-level config manager

## Recommended Approach
1. **AUDIT**: Create feature comparison matrix for all 7 config systems
2. **ANALYZE**: Which config sources, validation methods, caching strategies each supports
3. Team decision: Choose canonical BASE (recommend \`unified_config_manager.py\` as starting point)
4. **MERGE**: Best features from all 7 into canonical (config sources, validation, caching, reload)
5. **DOCUMENT**: Feature provenance (e.g., \"K8s support from config_consolidated.py\")
6. Create comprehensive migration guide
7. Update all config consumers across codebase
8. Deprecate old implementations
9. Schedule removal

## Benefits
- Single configuration API across entire codebase
- Easier to add new configuration sources (env, files, K8s, etc.)
- Consistent validation and defaults
- Reduced confusion about which config system to use

## Acceptance Criteria
- [ ] **Feature comparison matrix created** for all 7 config systems
- [ ] **All unique config sources, validation, caching identified**
- [ ] Team decides on canonical BASE config system
- [ ] **Best features from all 7 merged** into canonical implementation
- [ ] **Canonical file uses permanent name** (no \"_consolidated\", \"_refactored\", etc.)
- [ ] **Documentation of feature sources** (which capabilities came from which file)
- [ ] Migration guide created with examples
- [ ] All consumers updated
- [ ] **Old implementations archived** to \`archives/2025-11-11_config_consolidation/\` using \`git mv\`
- [ ] **Archival documented** in archives README
- [ ] Tests passing
- [ ] Documentation updated with feature provenance

## Estimated Effort
10-15 hours

## Related
- Affects ALL components (config is fundamental)"

echo "✅ Issue #2 created"
echo ""

# Issue #3: Cache Managers
echo "Creating Issue #3: Cache Managers..."
gh issue create \
  --title "🟠 P3: Consolidate Cache Managers (4-6 hours)" \
  --label "refactoring,technical-debt,priority: medium,component: cache" \
  --body "## Problem
3 different cache implementations exist (~950 duplicate lines), causing inconsistent caching behavior and duplicate logic.

## Files Affected
1. \`src/utils/advanced_cache_manager.py\` (15,848 bytes) - Advanced caching with TTL, LRU
2. \`backend/utils/cache_manager.py\` (10,246 bytes) - Backend-specific caching
3. \`src/utils/knowledge_cache.py\` (10,473 bytes) - Knowledge base specific caching

## Recommended Approach
1. Merge into single \`src/utils/cache_manager.py\`
2. Support different cache backends (Redis, in-memory, disk)
3. Unified cache key generation and invalidation
4. Support domain-specific caching (knowledge, LLM, etc.)
5. Add centralized metrics and monitoring

## Benefits
- Consistent cache behavior across components
- Easier to add distributed caching
- Unified metrics and monitoring
- Support for different cache backends

## Acceptance Criteria
- [ ] Single cache manager with pluggable backends
- [ ] All features from 3 implementations merged
- [ ] Domain-specific caching supported (knowledge, LLM, etc.)
- [ ] Migration guide created
- [ ] All consumers updated
- [ ] Tests passing
- [ ] Documentation updated

## Estimated Effort
4-6 hours"

echo "✅ Issue #3 created"
echo ""

# Issue #4: Memory Managers
echo "Creating Issue #4: Memory Managers..."
gh issue create \
  --title "🟠 P4: Consolidate Memory Managers (6-8 hours)" \
  --label "refactoring,technical-debt,priority: medium,component: memory" \
  --body "## Problem
5 different memory management systems exist (~2,550 duplicate lines), causing confusion about which to use and inconsistent behavior.

## Files Affected
1. \`src/memory_manager.py\` (27,566 bytes) - Base memory management
2. \`src/memory_manager_async.py\` (19,819 bytes) - Async memory management
3. \`src/enhanced_memory_manager.py\` (23,044 bytes) - Enhanced memory features
4. \`src/enhanced_memory_manager_async.py\` (21,468 bytes) - Enhanced + async
5. \`src/utils/optimized_memory_manager.py\` - Performance-optimized

## Recommended Approach
1. Create single \`MemoryManager\` class with async support
2. Merge enhanced features into single implementation
3. Use composition for different memory backends
4. Support both sync and async usage patterns

## Benefits
- Single memory management API
- Consistent behavior across codebase
- Easier to add new memory backends
- Reduced maintenance burden

## Acceptance Criteria
- [ ] Single MemoryManager class supporting async
- [ ] All enhanced features merged
- [ ] Composition pattern for different backends
- [ ] Migration guide created
- [ ] All consumers updated
- [ ] Tests passing
- [ ] Documentation updated

## Estimated Effort
6-8 hours"

echo "✅ Issue #4 created"
echo ""

# Issue #5: Chat/Conversation Managers
echo "Creating Issue #5: Chat/Conversation Managers..."
gh issue create \
  --title "🟡 P5: Consolidate Chat/Conversation Managers (8-10 hours)" \
  --label "refactoring,technical-debt,priority: low,component: chat" \
  --body "## Problem
7 different chat/conversation implementations exist (~5,000 duplicate lines), causing confusion about which to use and feature fragmentation.

## Files Affected
1. \`src/chat_workflow_manager.py\` (67,537 bytes) - Main chat workflow
2. \`src/chat_workflow_consolidated.py\` (35,730 bytes) - Consolidated attempt
3. \`src/async_chat_workflow.py\` (13,090 bytes) - Async workflow
4. \`src/simple_chat_workflow.py\` (12,608 bytes) - Simplified workflow
5. \`src/conversation.py\` (29,403 bytes) - Conversation management
6. \`src/conversation_performance_optimized.py\` (39,933 bytes) - Performance-optimized
7. \`src/conversation_file_manager.py\` (36,061 bytes) - File-based storage

## Recommended Approach
1. Identify active/primary implementation (likely \`chat_workflow_manager.py\`)
2. Audit all 7 for unique features
3. Merge features into primary implementation
4. Create migration guide
5. Deprecate unused implementations
6. Update all consumers

## Benefits
- Single chat workflow API
- Consistent conversation handling
- Easier to add new features
- Reduced confusion for developers

## Acceptance Criteria
- [ ] Team decides on primary implementation
- [ ] All features merged
- [ ] Migration guide created
- [ ] All consumers updated
- [ ] Old implementations deprecated
- [ ] Tests passing
- [ ] Documentation updated

## Estimated Effort
8-10 hours"

echo "✅ Issue #5 created"
echo ""

# Issue #6: HTTP Client
echo "Creating Issue #6: HTTP Client..."
gh issue create \
  --title "🟡 P6: Standardize HTTP Client Usage (3-4 hours)" \
  --label "refactoring,technical-debt,priority: low,component: http" \
  --body "## Problem
Inconsistent HTTP client usage across codebase - multiple places creating \`aiohttp.ClientSession\` directly without proper connection pooling, retry logic, or circuit breaker support.

## Current State
- \`src/utils/http_client.py\` exists but may not be used universally
- Multiple places creating ClientSession directly
- No centralized connection pooling
- No unified retry/timeout logic

## Recommended Approach
1. Audit all \`aiohttp.ClientSession\` creation:
   \`\`\`bash
   grep -r \"ClientSession\" --include=\"*.py\" src/ backend/
   \`\`\`
2. Create centralized HTTP client factory in \`src/utils/http_client.py\`
3. Implement connection pooling, retry logic, timeout management
4. Add circuit breaker support
5. Update all consumers

## Benefits
- Prevent connection pool exhaustion
- Consistent retry logic across HTTP calls
- Circuit breaker protection
- Centralized metrics and monitoring

## Acceptance Criteria
- [ ] All ClientSession creation uses centralized factory
- [ ] Connection pooling implemented
- [ ] Retry logic with exponential backoff
- [ ] Circuit breaker support
- [ ] Migration guide created
- [ ] Tests passing
- [ ] Documentation updated

## Estimated Effort
3-4 hours"

echo "✅ Issue #6 created"
echo ""

# Issue #7: Logging
echo "Creating Issue #7: Logging..."
gh issue create \
  --title "🟡 P7: Standardize Logging Configuration (2-3 hours)" \
  --label "refactoring,technical-debt,priority: low,component: logging" \
  --body "## Problem
Multiple logging configurations across codebase (~200 duplicate lines), causing inconsistent log formats and difficulty in centralized log management.

## Files Affected
1. \`src/utils/logging_manager.py\` (6,724 bytes) - Logging configuration
2. Multiple files configuring logging independently

## Recommended Approach
1. Centralize all logging configuration in \`src/utils/logging_manager.py\`
2. Standard log format across all components
3. Centralized log level management
4. Support different log outputs (file, console, Loki, etc.)
5. Update all components to use centralized logging

## Benefits
- Consistent log format across codebase
- Easier to integrate with log aggregation (Loki, ELK, etc.)
- Centralized log level management
- Structured logging support

## Acceptance Criteria
- [ ] Single logging configuration system
- [ ] All components use centralized logging
- [ ] Standard log format defined
- [ ] Support for multiple log outputs
- [ ] Migration guide created
- [ ] Tests passing
- [ ] Documentation updated

## Estimated Effort
2-3 hours"

echo "✅ Issue #7 created"
echo ""

echo "=================================================="
echo "✅ All 7 GitHub issues created successfully!"
echo ""
echo "Summary:"
echo "  🔴 P1: Redis Managers (8-12h)"
echo "  🔴 P2: Config Managers (10-15h)"
echo "  🟠 P3: Cache Managers (4-6h)"
echo "  🟠 P4: Memory Managers (6-8h)"
echo "  🟡 P5: Chat/Conversation (8-10h)"
echo "  🟡 P6: HTTP Client (3-4h)"
echo "  🟡 P7: Logging (2-3h)"
echo ""
echo "Total estimated effort: 41-58 hours"
echo ""
echo "View issues: gh issue list --label refactoring"
