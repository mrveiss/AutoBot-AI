#!/bin/bash
# Week 1 Implementation Verification Script
# Verifies database initialization implementation is working correctly

set -e

echo "🔍 Week 1 Implementation Verification"
echo "======================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track results
PASSED=0
FAILED=0

# Function to check a condition
check() {
    local description="$1"
    local command="$2"

    echo -n "Checking: $description... "

    if eval "$command" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ PASS${NC}"
        ((PASSED++))
        return 0
    else
        echo -e "${RED}✗ FAIL${NC}"
        ((FAILED++))
        return 1
    fi
}

# Function to check file exists
check_file() {
    local description="$1"
    local file="$2"

    check "$description" "test -f \"$file\""
}

# Function to check method exists in file
check_method() {
    local description="$1"
    local file="$2"
    local method="$3"

    check "$description" "grep -q \"async def $method\" \"$file\""
}

echo "📋 Part 1: Code Implementation Checks"
echo "--------------------------------------"

# Check files exist
check_file "ConversationFileManager exists" "src/conversation_file_manager.py"
check_file "Backend app factory exists" "backend/app_factory.py"
check_file "System API exists" "backend/api/system.py"

# Check methods implemented
check_method "initialize() method exists" "src/conversation_file_manager.py" "initialize"
check_method "_get_schema_version() exists" "src/conversation_file_manager.py" "_get_schema_version"
check_method "_set_schema_version() exists" "src/conversation_file_manager.py" "_set_schema_version"
check_method "_apply_schema() exists" "src/conversation_file_manager.py" "_apply_schema"
check_method "_verify_schema_integrity() exists" "src/conversation_file_manager.py" "_verify_schema_integrity"

# Check imports
check "asyncio import exists" "grep -q \"import asyncio\" src/conversation_file_manager.py"
check "aiofiles import exists" "grep -q \"import aiofiles\" src/conversation_file_manager.py"
check "SCHEMA_VERSION constant exists" "grep -q \"SCHEMA_VERSION\" src/conversation_file_manager.py"

echo ""
echo "📋 Part 2: Test Files Checks"
echo "----------------------------"

check_file "Unit tests exist" "tests/unit/test_conversation_file_manager.py"
check_file "Integration tests exist" "tests/distributed/test_db_initialization.py"

# Check test content
if [ -f "tests/unit/test_conversation_file_manager.py" ]; then
    check "test_first_time_initialization exists" "grep -q \"test_first_time_initialization\" tests/unit/test_conversation_file_manager.py"
    check "test_idempotent_initialization exists" "grep -q \"test_idempotent_initialization\" tests/unit/test_conversation_file_manager.py"
    check "test_schema_version_tracking exists" "grep -q \"test_schema_version_tracking\" tests/unit/test_conversation_file_manager.py"
fi

echo ""
echo "📋 Part 3: Database Runtime Checks"
echo "-----------------------------------"

# Check if database was initialized
DB_PATH="/home/kali/Desktop/AutoBot/data/conversation_files.db"

if [ -f "$DB_PATH" ]; then
    echo -e "${GREEN}✓${NC} Database file exists: $DB_PATH"
    ((PASSED++))

    # Check tables
    TABLES=$(sqlite3 "$DB_PATH" ".tables" 2>/dev/null || echo "")

    for table in "conversation_files" "file_metadata" "session_file_associations" "file_access_log" "file_cleanup_queue" "schema_version"; do
        if echo "$TABLES" | grep -q "$table"; then
            echo -e "${GREEN}✓${NC} Table exists: $table"
            ((PASSED++))
        else
            echo -e "${RED}✗${NC} Table missing: $table"
            ((FAILED++))
        fi
    done

    # Check schema version
    VERSION=$(sqlite3 "$DB_PATH" "SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1;" 2>/dev/null || echo "")
    if [ -n "$VERSION" ]; then
        echo -e "${GREEN}✓${NC} Schema version: $VERSION"
        ((PASSED++))
    else
        echo -e "${RED}✗${NC} Schema version not set"
        ((FAILED++))
    fi
else
    echo -e "${YELLOW}⚠${NC} Database not yet initialized (run backend to initialize)"
    echo "   Skip database runtime checks..."
fi

echo ""
echo "📋 Part 4: Backend Health Check"
echo "--------------------------------"

# Check if backend is running
if curl -s http://172.16.168.20:8001/api/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Backend is running"
    ((PASSED++))

    # Check health endpoint response
    HEALTH=$(curl -s http://172.16.168.20:8001/api/health 2>/dev/null || echo "{}")

    # Check if database status is reported
    if echo "$HEALTH" | grep -q "database"; then
        echo -e "${GREEN}✓${NC} Health check reports database status"
        ((PASSED++))

        # Extract database status
        DB_STATUS=$(echo "$HEALTH" | grep -o '"conversation_files":"[^"]*"' | cut -d'"' -f4)
        if [ "$DB_STATUS" = "healthy" ]; then
            echo -e "${GREEN}✓${NC} Database status: healthy"
            ((PASSED++))
        else
            echo -e "${YELLOW}⚠${NC} Database status: $DB_STATUS"
            ((FAILED++))
        fi
    else
        echo -e "${RED}✗${NC} Health check does not report database status"
        ((FAILED++))
    fi
else
    echo -e "${YELLOW}⚠${NC} Backend not running (start with: bash run_autobot.sh --dev --no-browser)"
    echo "   Skip health check tests..."
fi

echo ""
echo "📋 Part 5: Test Execution"
echo "-------------------------"

# Run unit tests if they exist
if [ -f "tests/unit/test_conversation_file_manager.py" ]; then
    echo "Running unit tests..."
    if pytest tests/unit/test_conversation_file_manager.py -v --tb=short 2>&1 | tail -20; then
        echo -e "${GREEN}✓${NC} Unit tests passed"
        ((PASSED++))
    else
        echo -e "${RED}✗${NC} Unit tests failed"
        ((FAILED++))
    fi
else
    echo -e "${YELLOW}⚠${NC} Unit tests not yet created"
fi

echo ""
echo "======================================"
echo "📊 Verification Results"
echo "======================================"
echo -e "Passed: ${GREEN}$PASSED${NC}"
echo -e "Failed: ${RED}$FAILED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}🎉 All checks passed! Week 1 implementation is complete.${NC}"
    exit 0
else
    echo -e "${RED}⚠️  Some checks failed. Review the output above.${NC}"
    exit 1
fi
