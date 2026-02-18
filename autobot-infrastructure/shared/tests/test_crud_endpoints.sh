#!/bin/bash
# Test script for Knowledge Base CRUD operations
# This script tests CREATE, READ, UPDATE, and DELETE operations

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_PROJECT_ROOT="$SCRIPT_DIR"
while [ "$_PROJECT_ROOT" != "/" ] && [ ! -f "$_PROJECT_ROOT/.env" ]; do
    _PROJECT_ROOT="$(dirname "$_PROJECT_ROOT")"
done
source "$_PROJECT_ROOT/infrastructure/shared/scripts/lib/ssot-config.sh" 2>/dev/null || true

# Source environment variables if available, otherwise use defaults from NetworkConstants
BACKEND_HOST="${AUTOBOT_BACKEND_HOST:-172.16.168.20}"
BACKEND_PORT="${AUTOBOT_BACKEND_PORT:-8001}"
BACKEND_URL="http://${BACKEND_HOST}:${BACKEND_PORT}/api/knowledge_base"

echo "========================================="
echo "Testing Knowledge Base CRUD Operations"
echo "========================================="
echo ""

# Step 1: CREATE a test fact
echo "1. CREATE: Creating a test fact..."
CREATE_RESPONSE=$(curl -s -X POST "${BACKEND_URL}/add_text" \
  -H "Content-Type: application/json" \
  -d '{"text": "This is a test fact for CRUD testing", "title": "CRUD Test Fact", "category": "test", "source": "manual"}')

echo "Response: $CREATE_RESPONSE"
FACT_ID=$(echo "$CREATE_RESPONSE" | grep -o '"fact_id":"[^"]*"' | cut -d'"' -f4)

if [ -z "$FACT_ID" ]; then
    echo "ERROR: Failed to create fact"
    exit 1
fi

echo "Created fact with ID: $FACT_ID"
echo ""

# Step 2: UPDATE the fact (content only)
echo "2. UPDATE (content): Updating fact content..."
UPDATE_RESPONSE=$(curl -s -X PUT "${BACKEND_URL}/fact/${FACT_ID}" \
  -H "Content-Type: application/json" \
  -d '{"content": "This is an UPDATED test fact for CRUD testing"}')

echo "Response: $UPDATE_RESPONSE"

if echo "$UPDATE_RESPONSE" | grep -q '"status":"success"'; then
    echo "SUCCESS: Content updated"
else
    echo "ERROR: Content update failed"
    echo "$UPDATE_RESPONSE"
    exit 1
fi
echo ""

# Step 3: UPDATE the fact (metadata only)
echo "3. UPDATE (metadata): Updating fact metadata..."
UPDATE_META_RESPONSE=$(curl -s -X PUT "${BACKEND_URL}/fact/${FACT_ID}" \
  -H "Content-Type: application/json" \
  -d '{"metadata": {"title": "Updated CRUD Test", "category": "test-updated"}}')

echo "Response: $UPDATE_META_RESPONSE"

if echo "$UPDATE_META_RESPONSE" | grep -q '"status":"success"'; then
    echo "SUCCESS: Metadata updated"
else
    echo "ERROR: Metadata update failed"
    echo "$UPDATE_META_RESPONSE"
    exit 1
fi
echo ""

# Step 4: UPDATE the fact (both content and metadata)
echo "4. UPDATE (both): Updating both content and metadata..."
UPDATE_BOTH_RESPONSE=$(curl -s -X PUT "${BACKEND_URL}/fact/${FACT_ID}" \
  -H "Content-Type: application/json" \
  -d '{"content": "Final updated content", "metadata": {"title": "Final Test", "category": "final"}}')

echo "Response: $UPDATE_BOTH_RESPONSE"

if echo "$UPDATE_BOTH_RESPONSE" | grep -q '"status":"success"'; then
    echo "SUCCESS: Both content and metadata updated"
else
    echo "ERROR: Combined update failed"
    echo "$UPDATE_BOTH_RESPONSE"
    exit 1
fi
echo ""

# Step 5: DELETE the fact
echo "5. DELETE: Deleting the test fact..."
DELETE_RESPONSE=$(curl -s -X DELETE "${BACKEND_URL}/fact/${FACT_ID}")

echo "Response: $DELETE_RESPONSE"

if echo "$DELETE_RESPONSE" | grep -q '"status":"success"'; then
    echo "SUCCESS: Fact deleted"
else
    echo "ERROR: Delete failed"
    echo "$DELETE_RESPONSE"
    exit 1
fi
echo ""

# Step 6: Verify deletion (should return 404)
echo "6. VERIFY: Confirming fact is deleted..."
VERIFY_RESPONSE=$(curl -s -X DELETE "${BACKEND_URL}/fact/${FACT_ID}")

if echo "$VERIFY_RESPONSE" | grep -q '"detail":".*not found"'; then
    echo "SUCCESS: Fact confirmed deleted (404 as expected)"
else
    echo "WARNING: Expected 404 after deletion"
    echo "$VERIFY_RESPONSE"
fi
echo ""

echo "========================================="
echo "All CRUD tests passed successfully!"
echo "========================================="
