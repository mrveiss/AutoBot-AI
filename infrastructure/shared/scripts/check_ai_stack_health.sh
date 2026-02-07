#!/bin/bash
# Check AI Stack container health and data access

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
        echo "❌ Missing: $prompt"
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
    echo "❌ Knowledge base index missing"
fi

# Test prompt loading
echo ""
echo "🧪 Testing prompt loading..."
docker exec autobot-ai-stack python -c "
import sys
sys.path.insert(0, '/app')
sys.path.insert(0, '/app/src')

try:
    from src.prompt_manager import PromptManager
    pm = PromptManager()
    prompts = pm.list_prompts()
    print(f'✅ Successfully loaded {len(prompts)} prompts')

    # Test specific prompts
    test_prompts = [
        'reflection.agent.system.main.role',
        'default.agent.system.main'
    ]
    for prompt_key in test_prompts:
        try:
            content = pm.get_prompt(prompt_key)
            print(f'✅ Loaded {prompt_key}: {len(content)} chars')
        except:
            print(f'❌ Failed to load {prompt_key}')

except Exception as e:
    print(f'❌ Error loading prompts: {e}')
    import traceback
    traceback.print_exc()
"

# Check API health
echo ""
echo "🌐 Checking API health..."
if curl -s -f http://localhost:8080/health > /dev/null; then
    echo "✅ AI API is responding"
    curl -s http://localhost:8080/health | python -m json.tool
else
    echo "❌ AI API is not responding"
    echo "   Check logs: docker logs autobot-ai-stack"
fi

echo ""
echo "📊 Health check complete!"
