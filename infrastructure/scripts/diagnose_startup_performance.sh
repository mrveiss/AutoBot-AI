#!/bin/bash
# Backend Startup Performance Diagnosis Script
# Analyzes what's causing slow startup times

echo "🔍 AutoBot Backend Startup Performance Analysis"
echo "=============================================="
echo "Investigating ~1 minute startup delay..."
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Step 1: Check current backend status
echo -e "${BLUE}📊 Step 1: Current Backend Status${NC}"
if pgrep -f "python.*main.py\|uvicorn\|fastapi" > /dev/null; then
    echo -e "  ${YELLOW}Backend is currently running${NC}"
    echo "  Checking memory usage..."
    ps aux | grep -E "python.*main.py|uvicorn|fastapi" | grep -v grep | awk '{print "  Memory: " $6/1024 " MB, CPU: " $3 "%, PID: " $2}'
else
    echo -e "  ${GREEN}Backend is stopped - good for testing${NC}"
fi

# Step 2: Analyze startup script
echo -e "\n${BLUE}🚀 Step 2: Startup Script Analysis${NC}"
if [ -f "run_agent.sh" ]; then
    echo "  Analyzing run_agent.sh..."

    # Check for blocking operations
    BLOCKING_OPS=$(grep -E "sleep|wait|docker.*pull|pip install|npm install|git clone" run_agent.sh | wc -l)
    echo "  Potential blocking operations found: $BLOCKING_OPS"

    # Check Docker operations
    DOCKER_OPS=$(grep -c "docker" run_agent.sh)
    echo "  Docker operations: $DOCKER_OPS"

    if [ $DOCKER_OPS -gt 0 ]; then
        echo -e "  ${YELLOW}⚠️  Docker operations detected - these can be slow${NC}"
        grep -n "docker" run_agent.sh | head -5 | sed 's/^/    /'
    fi
else
    echo -e "  ${RED}❌ run_agent.sh not found${NC}"
fi

# Step 3: Check Python imports and dependencies
echo -e "\n${BLUE}🐍 Step 3: Python Dependency Analysis${NC}"
echo "  Analyzing main.py and app_factory.py..."

# Check main.py imports
if [ -f "backend/main.py" ]; then
    IMPORT_COUNT=$(grep -c "^import\|^from" backend/main.py)
    echo "  Main.py imports: $IMPORT_COUNT"

    # Check for slow imports
    SLOW_IMPORTS=$(grep -E "tensorflow|torch|transformers|chromadb|sentence_transformers" backend/main.py | wc -l)
    if [ $SLOW_IMPORTS -gt 0 ]; then
        echo -e "  ${YELLOW}⚠️  Heavy ML libraries detected: $SLOW_IMPORTS${NC}"
        grep -E "tensorflow|torch|transformers|chromadb|sentence_transformers" backend/main.py | sed 's/^/    /'
    fi
else
    echo -e "  ${RED}❌ backend/main.py not found${NC}"
fi

# Check app_factory.py
if [ -f "backend/app_factory.py" ]; then
    APP_IMPORTS=$(grep -c "^import\|^from" backend/app_factory.py)
    echo "  App factory imports: $APP_IMPORTS"

    # Check for database initialization
    DB_INIT=$(grep -E "database|db|chroma|redis|sqlite" backend/app_factory.py | wc -l)
    echo "  Database operations: $DB_INIT"
fi

# Step 4: Check for heavy initialization
echo -e "\n${BLUE}🔄 Step 4: Initialization Bottlenecks${NC}"

# Check for model loading
MODEL_LOADING=$(find . -name "*.py" -path "*/backend/*" -o -path "*/src/*" | xargs grep -l "load_model\|SentenceTransformer\|embedding" | wc -l)
echo "  Files with model loading: $MODEL_LOADING"

if [ $MODEL_LOADING -gt 0 ]; then
    echo -e "  ${YELLOW}⚠️  Model loading detected - major startup delay cause${NC}"
    find . -name "*.py" -path "*/backend/*" -o -path "*/src/*" | xargs grep -l "SentenceTransformer" | head -3 | sed 's/^/    Model in: /'
fi

# Check for ChromaDB initialization
CHROMA_FILES=$(find . -name "*.py" | xargs grep -l "chromadb\|Chroma" | wc -l)
echo "  Files with ChromaDB: $CHROMA_FILES"

# Step 5: Check startup logs
echo -e "\n${BLUE}📜 Step 5: Startup Log Analysis${NC}"
if [ -f "logs/backend.log" ]; then
    echo "  Analyzing recent backend logs..."

    # Get last startup sequence
    LAST_STARTUP=$(grep -n "Starting\|Initializing\|Loading" logs/backend.log | tail -10)
    if [ ! -z "$LAST_STARTUP" ]; then
        echo "  Recent startup activities:"
        echo "$LAST_STARTUP" | sed 's/^/    /'
    fi

    # Check for errors during startup
    STARTUP_ERRORS=$(grep -E "ERROR\|CRITICAL\|Exception" logs/backend.log | tail -5)
    if [ ! -z "$STARTUP_ERRORS" ]; then
        echo -e "  ${RED}Recent errors found:${NC}"
        echo "$STARTUP_ERRORS" | sed 's/^/    /'
    fi
else
    echo "  No backend.log found - will create during next startup"
fi

# Step 6: Docker and container analysis
echo -e "\n${BLUE}🐳 Step 6: Docker Container Analysis${NC}"
if command -v docker &> /dev/null; then
    echo "  Checking Docker containers..."

    # List AutoBot containers
    CONTAINERS=$(docker ps -a --filter "name=autobot" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -v NAMES)
    if [ ! -z "$CONTAINERS" ]; then
        echo "  AutoBot containers:"
        echo "$CONTAINERS" | sed 's/^/    /'

        # Check for stuck containers
        STUCK_CONTAINERS=$(echo "$CONTAINERS" | grep -c "Exited\|Restarting")
        if [ $STUCK_CONTAINERS -gt 0 ]; then
            echo -e "  ${YELLOW}⚠️  Found $STUCK_CONTAINERS stuck containers${NC}"
        fi
    else
        echo "  No AutoBot containers found"
    fi
else
    echo "  Docker not available"
fi

# Step 7: Check system resources
echo -e "\n${BLUE}💾 Step 7: System Resource Check${NC}"
echo "  Available memory: $(free -h | awk '/^Mem:/{print $7}')"
echo "  Available disk: $(df -h . | awk 'NR==2{print $4}')"
echo "  CPU load: $(uptime | awk -F'load average:' '{print $2}')"

# Check for high CPU processes
HIGH_CPU=$(ps aux --sort=-%cpu | head -6 | tail -5 | awk '$3 > 50 {print "    High CPU: " $11 " (" $3 "%)";}')
if [ ! -z "$HIGH_CPU" ]; then
    echo -e "  ${YELLOW}High CPU processes:${NC}"
    echo "$HIGH_CPU"
fi

# Step 8: Test actual startup timing
echo -e "\n${BLUE}⏱️  Step 8: Startup Timing Test${NC}"
echo "  Testing backend startup performance..."

# Create a test script for timing in proper directory
mkdir -p tests/temp
cat > tests/temp/startup_test.py << 'EOF'
#!/usr/bin/env python3
import time
import sys
import os

print("Testing import times...")
start_time = time.time()

# Test major imports
imports_to_test = [
    "fastapi",
    "uvicorn",
    "pydantic",
    "asyncio",
    "logging"
]

for imp in imports_to_test:
    imp_start = time.time()
    try:
        exec(f"import {imp}")
        import_time = time.time() - imp_start
        print(f"  {imp}: {import_time:.3f}s")
    except ImportError as e:
        print(f"  {imp}: FAILED - {e}")

total_time = time.time() - start_time
print(f"Total basic imports: {total_time:.3f}s")

# Test heavy imports
print("\nTesting heavy imports...")
heavy_imports = [
    "sentence_transformers",
    "chromadb",
    "transformers",
    "torch"
]

for imp in heavy_imports:
    imp_start = time.time()
    try:
        exec(f"import {imp}")
        import_time = time.time() - imp_start
        print(f"  {imp}: {import_time:.3f}s")
    except ImportError:
        print(f"  {imp}: Not installed (good for startup)")

print(f"Import test completed in {time.time() - start_time:.3f}s")
EOF

python3 tests/temp/startup_test.py
rm tests/temp/startup_test.py

# Step 9: Recommendations
echo -e "\n${YELLOW}💡 Performance Recommendations:${NC}"

if [ $MODEL_LOADING -gt 0 ]; then
    echo "  1. 🎯 CRITICAL: Model loading is the likely culprit"
    echo "     - Consider lazy loading models on first use"
    echo "     - Use model caching or pre-loaded containers"
    echo "     - Move model initialization to background tasks"
fi

if [ $DOCKER_OPS -gt 0 ]; then
    echo "  2. 🐳 Docker optimization:"
    echo "     - Use pre-built images instead of building on startup"
    echo "     - Implement health checks to avoid restart delays"
    echo "     - Consider Docker layer caching"
fi

if [ $CHROMA_FILES -gt 0 ]; then
    echo "  3. 📊 Database optimization:"
    echo "     - Initialize ChromaDB asynchronously"
    echo "     - Use persistent volumes to avoid reindexing"
    echo "     - Consider database connection pooling"
fi

echo "  4. 🚀 General optimizations:"
echo "     - Profile startup with cProfile"
echo "     - Implement async initialization"
echo "     - Use environment-specific configs"
echo "     - Cache heavy computations"

# Step 10: Generate startup profile script
echo -e "\n${BLUE}📊 Step 10: Creating Startup Profiler${NC}"
cat > scripts/profile_startup.py << 'EOF'
#!/usr/bin/env python3
"""
Startup Performance Profiler
Profiles AutoBot backend startup to identify bottlenecks
"""
import cProfile
import pstats
import time
import sys
import os

def profile_startup():
    """Profile the startup sequence"""
    print("🔍 Starting backend startup profiling...")

    # Add the project root to Python path
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    profiler = cProfile.Profile()
    profiler.enable()

    start_time = time.time()

    try:
        # Import main components
        print("Importing main modules...")
        from backend import main, app_factory

        print("Creating FastAPI app...")
        app = app_factory.create_app()

        end_time = time.time()

    except Exception as e:
        print(f"Error during profiling: {e}")
        return
    finally:
        profiler.disable()

    print(f"Startup completed in {end_time - start_time:.3f} seconds")

    # Save and display results
    stats = pstats.Stats(profiler)
    stats.sort_stats('cumulative')

    print("\n🔝 Top 10 slowest functions:")
    stats.print_stats(10)

    # Save detailed report to proper directory
    from pathlib import Path
    reports_dir = Path(__file__).parent.parent / "reports" / "performance"
    reports_dir.mkdir(parents=True, exist_ok=True)

    profile_file = reports_dir / "startup_profile.txt"
    with open(profile_file, 'w') as f:
        stats.print_stats(file=f)

    print(f"\nDetailed profile saved to {profile_file}")

if __name__ == "__main__":
    profile_startup()
EOF

chmod +x scripts/profile_startup.py
echo "  ✅ Startup profiler created: scripts/profile_startup.py"

echo -e "\n${GREEN}🎯 Analysis Complete!${NC}"
echo "===================="
echo "Next steps:"
echo "1. Run: python scripts/profile_startup.py"
echo "2. Check startup logs during next ./run_agent.sh"
echo "3. Monitor system resources during startup"
echo "4. Consider implementing lazy loading for heavy components"

# Log this analysis
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "create_record", "arguments": {"table": "development_log", "data": {"project_id": 1, "log_entry": "Backend startup performance analysis completed", "log_level": "INFO", "details": "{\"analysis_timestamp\": \"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'\", \"model_files\": '$MODEL_LOADING', \"docker_ops\": '$DOCKER_OPS', \"chroma_files\": '$CHROMA_FILES'}"}}}}' | npx -y mcp-sqlite data/autobot.db 2>/dev/null >/dev/null

echo -e "\nAnalysis logged to database ✅"
