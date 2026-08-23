#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Check AI Stack container health and data access

# Every failed check increments this; the closing banner refuses to report a
# clean health check while it is non-zero (#14867).
FAILURES=0

echo "🔍 Checking AI Stack Health..."

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q '^autobot-ai-stack$'; then
    echo "❌ AI Stack container is not running"
    echo "   Run: docker-compose -f docker/compose/docker-compose.hybrid.yml up -d autobot-ai-stack"
    exit 1
fi

echo "✅ AI Stack container is running"

# Check prompts access
echo ""
echo "📝 Checking prompts access..."
docker exec autobot-ai-stack ls -la /app/prompts/ | head -5 || {
    echo "❌ Cannot access prompts directory"
    exit 1
}

# Check specific prompt files
echo ""
echo "📄 Checking critical prompt files..."
CRITICAL_PROMPTS=(
    "/app/prompts/reflection/agent.system.main.role.md"
    "/app/prompts/tool_interpreter_system_prompt.txt"
    "/app/prompts/default/agent.system.main.md"
)

for prompt in "${CRITICAL_PROMPTS[@]}"; do
    if docker exec autobot-ai-stack test -f "$prompt"; then
        echo "✅ Found: $prompt"
    else
        echo "❌ Missing: $prompt" >&2
        FAILURES=$((FAILURES + 1))
    fi
done

# Check knowledge base
echo ""
echo "📚 Checking knowledge base access..."
docker exec autobot-ai-stack ls -la /app/knowledge_base/ | head -5 || {
    echo "❌ Cannot access knowledge base directory"
    exit 1
}

# Check knowledge base index
if docker exec autobot-ai-stack test -f /app/knowledge_base/index.json; then
    echo "✅ Knowledge base index found"
    docker exec autobot-ai-stack python -c "
import json
with open('/app/knowledge_base/index.json') as f:
    data = json.load(f)
    categories = data.get('categories', {})
    print(f'   Categories: {list(categories.keys())}')
"
else
    echo "❌ Knowledge base index missing" >&2
    FAILURES=$((FAILURES + 1))
fi

# Test prompt loading
echo ""
echo "🧪 Testing prompt loading..."
# (#14867) There is no `src` package: the container puts /app and /app/src on
# sys.path (see docker/ai-stack/ai_container_main.py) and its own entry points
# import these modules top-level. PromptManager lives in prompt_manager.py.
if ! docker exec autobot-ai-stack python -c "
import sys
sys.path.insert(0, '/app')
sys.path.insert(0, '/app/src')

try:
    from prompt_manager import PromptManager
    pm = PromptManager()
    prompts = pm.list_prompts()
    print(f'✅ Successfully loaded {len(prompts)} prompts')

    # Test specific prompts
    test_prompts = [
        'reflection.agent.system.main.role',
        'default.agent.system.main'
    ]
    failed = []
    for prompt_key in test_prompts:
        try:
            content = pm.get_prompt(prompt_key)
            print(f'✅ Loaded {prompt_key}: {len(content)} chars')
        except Exception as exc:
            print(f'❌ Failed to load {prompt_key}: {exc}', file=sys.stderr)
            failed.append(prompt_key)

    if failed:
        sys.exit(1)

except Exception as e:
    # (#14867) This used to print and fall through with exit 0, so a prompt
    # loader that never ran was indistinguishable from one that passed.
    print(f'❌ Error loading prompts: {e}', file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)
"; then
    echo "❌ Prompt loading test failed - see the traceback above" >&2
    FAILURES=$((FAILURES + 1))
fi

# Check API health
echo ""
echo "🌐 Checking API health..."
if curl -s -f http://localhost:8080/health > /dev/null; then
    echo "✅ AI API is responding"
    curl -s http://localhost:8080/health | python -m json.tool
else
    echo "❌ AI API is not responding" >&2
    echo "   Check logs: docker logs autobot-ai-stack" >&2
    FAILURES=$((FAILURES + 1))
fi

echo ""
# (#14867) "Health check complete!" used to print with exit 0 no matter how many
# checks above had failed.
if [ "$FAILURES" -ne 0 ]; then
    echo "❌ Health check FAILED: $FAILURES problem(s) found" >&2
    exit 1
fi
echo "📊 Health check complete!"
