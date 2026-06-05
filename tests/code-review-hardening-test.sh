#!/usr/bin/env bash
# Test script for code-review hardening (MVA-2619 / GH#9605)
# Verifies that the updated skill enforces diff-grounded findings

set -euo pipefail

SKILL_FILE="/home/martins/.claude/plugins/marketplaces/claude-plugins-official/plugins/code-review/commands/code-review.md"
AGENT_FILE="/home/martins/.claude/plugins/marketplaces/claude-plugins-official/plugins/pr-review-toolkit/agents/code-reviewer.md"

echo "=== Code Review Hardening Test ==="
echo

# Test 1: Verify mandatory diff fetch step exists
echo "[1/6] Checking for mandatory diff fetch step..."
if grep -q "MANDATORY DIFF FETCH" "$SKILL_FILE"; then
    echo "✅ PASS: Mandatory diff fetch step present"
else
    echo "❌ FAIL: Mandatory diff fetch step missing"
    exit 1
fi

# Test 2: Verify citation requirement in skill
echo "[2/6] Checking for citation requirement in skill..."
if grep -q "Citation requirement" "$SKILL_FILE" && \
   grep -q "exact file path" "$SKILL_FILE" && \
   grep -q "line number range" "$SKILL_FILE" && \
   grep -q "verbatim text" "$SKILL_FILE"; then
    echo "✅ PASS: Citation requirement fully specified"
else
    echo "❌ FAIL: Citation requirement incomplete"
    exit 1
fi

# Test 3: Verify scope restriction requirement
echo "[3/6] Checking for scope restriction..."
if grep -q "Use Read on these paths only" "$SKILL_FILE" && \
   grep -q "Do NOT Glob for other files" "$SKILL_FILE"; then
    echo "✅ PASS: Scope restriction enforced"
else
    echo "❌ FAIL: Scope restriction missing"
    exit 1
fi

# Test 4: Verify verifier agent phase exists
echo "[4/6] Checking for verification phase..."
if grep -q "VERIFICATION PHASE" "$SKILL_FILE" && \
   grep -q "Re-reads the cited file:line from actual disk" "$SKILL_FILE" && \
   grep -q "Rejects the finding" "$SKILL_FILE"; then
    echo "✅ PASS: Verification phase implemented"
else
    echo "❌ FAIL: Verification phase missing"
    exit 1
fi

# Test 5: Verify exploit confirmation for security blockers
echo "[5/6] Checking for exploit confirmation..."
if grep -q "EXPLOIT CONFIRMATION" "$SKILL_FILE" && \
   grep -q "Traces the vulnerable path end-to-end" "$SKILL_FILE" && \
   grep -q "concrete attack scenario" "$SKILL_FILE"; then
    echo "✅ PASS: Exploit confirmation implemented"
else
    echo "❌ FAIL: Exploit confirmation missing"
    exit 1
fi

# Test 6: Verify deduplication step
echo "[6/6] Checking for deduplication..."
if grep -q "DEDUPLICATION" "$SKILL_FILE" && \
   grep -q "deduplicate findings" "$SKILL_FILE"; then
    echo "✅ PASS: Deduplication step present"
else
    echo "❌ FAIL: Deduplication missing"
    exit 1
fi

# Verify agent file has grounding requirements
echo
echo "=== Agent File Verification ==="
echo "[1/2] Checking code-reviewer agent for grounding requirement..."
if grep -q "MANDATORY GROUNDING REQUIREMENT" "$AGENT_FILE"; then
    echo "✅ PASS: Agent has grounding requirement"
else
    echo "❌ FAIL: Agent missing grounding requirement"
    exit 1
fi

echo "[2/2] Checking agent for citation requirement..."
if grep -q "Citation requirement" "$AGENT_FILE" && \
   grep -q "Verbatim code snippet" "$AGENT_FILE"; then
    echo "✅ PASS: Agent has citation requirement"
else
    echo "❌ FAIL: Agent missing citation requirement"
    exit 1
fi

echo
echo "=== All Tests Passed ==="
echo "✅ Code review hardening successfully implemented"
echo "   - Mandatory diff fetch: ✓"
echo "   - Citation requirement: ✓"
echo "   - Scope restriction: ✓"
echo "   - Verification phase: ✓"
echo "   - Exploit confirmation: ✓"
echo "   - Deduplication: ✓"
