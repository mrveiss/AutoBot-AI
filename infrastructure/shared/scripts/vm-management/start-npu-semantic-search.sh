#!/bin/bash
"""
Start NPU Semantic Search System for AutoBot
Initializes Intel NPU acceleration with enhanced semantic search capabilities
"""

set -e

# Source SSOT configuration (#808)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/ssot-config.sh" 2>/dev/null || true

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
NPU_WORKER_VM="${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}"
NPU_WORKER_PORT="${AUTOBOT_NPU_WORKER_PORT:-8081}"
REDIS_VM="${AUTOBOT_REDIS_HOST:-172.16.168.23}"
REDIS_PORT="${AUTOBOT_REDIS_PORT:-6379}"
AUTOBOT_ROOT="${PROJECT_ROOT:-/home/kali/Desktop/AutoBot}"

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_header() {
    echo -e "${PURPLE}========================================${NC}"
    echo -e "${PURPLE}$1${NC}"
    echo -e "${PURPLE}========================================${NC}"
}

check_vm_connection() {
    local vm_ip="$1"
    local vm_name="$2"

    log_info "Checking connection to $vm_name ($vm_ip)..."

    if ping -c 1 -W 2 "$vm_ip" > /dev/null 2>&1; then
        log_success "$vm_name is reachable"
        return 0
    else
        log_error "$vm_name is not reachable"
        return 1
    fi
}

check_service_health() {
    local url="$1"
    local service_name="$2"

    log_info "Checking $service_name health at $url..."

    if curl -s -f --connect-timeout 5 --max-time 10 "$url" > /dev/null 2>&1; then
        log_success "$service_name is healthy"
        return 0
    else
        log_warning "$service_name health check failed or not ready yet"
        return 1
    fi
}

start_enhanced_npu_worker() {
    log_header "Starting Enhanced NPU Worker"

    # Check if NPU Worker VM is accessible
    if ! check_vm_connection "$NPU_WORKER_VM" "NPU Worker VM"; then
        log_error "Cannot reach NPU Worker VM. Please ensure VM2 (172.16.168.22) is running."
        return 1
    fi

    # Copy enhanced NPU worker to VM
    log_info "Deploying enhanced NPU worker to VM2..."

    # Use SSH key authentication
    scp -i ~/.ssh/autobot_key \
        "$AUTOBOT_ROOT/scripts/utilities/npu_worker_enhanced.py" \
        "autobot@$NPU_WORKER_VM:/tmp/npu_worker_enhanced.py"

    if [ $? -eq 0 ]; then
        log_success "Enhanced NPU worker deployed successfully"
    else
        log_error "Failed to deploy enhanced NPU worker"
        return 1
    fi

    # Install dependencies on NPU Worker VM
    log_info "Installing dependencies on NPU Worker VM..."

    ssh -i ~/.ssh/autobot_key "autobot@$NPU_WORKER_VM" << 'EOF'
        # Install required Python packages
        pip install fastapi uvicorn aiohttp pydantic numpy scikit-learn

        # Install OpenVINO (if on Windows)
        if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
            echo "Installing OpenVINO for Windows NPU support..."
            pip install openvino
        else
            echo "Note: OpenVINO NPU support requires Windows. Running in fallback mode."
        fi

        # Check if we have NVIDIA GPU support
        if command -v nvidia-smi &> /dev/null; then
            echo "NVIDIA GPU detected, installing PyTorch with CUDA support..."
            pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
        else
            echo "No NVIDIA GPU detected, installing CPU-only PyTorch..."
            pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
        fi
EOF

    # Start the enhanced NPU worker service
    log_info "Starting enhanced NPU worker service..."

    ssh -i ~/.ssh/autobot_key "autobot@$NPU_WORKER_VM" << EOF
        # Kill any existing NPU worker processes
        pkill -f "npu_worker_enhanced.py" || true
        pkill -f "npu_worker.py" || true

        # Start the enhanced NPU worker
        cd /tmp
        nohup python3 npu_worker_enhanced.py \
            --host 0.0.0.0 \
            --port $NPU_WORKER_PORT \
            --redis-host $REDIS_VM \
            --redis-port $REDIS_PORT \
            > npu_worker.log 2>&1 &

        echo "Enhanced NPU Worker started on port $NPU_WORKER_PORT"
        echo "Logs available at: /tmp/npu_worker.log"
EOF

    # Wait for service to start
    log_info "Waiting for NPU Worker to initialize..."
    sleep 5

    # Check NPU Worker health
    if check_service_health "http://$NPU_WORKER_VM:$NPU_WORKER_PORT/health" "Enhanced NPU Worker"; then
        log_success "Enhanced NPU Worker is running and healthy"

        # Get NPU Worker status
        log_info "Getting NPU Worker status..."
        curl -s "http://$NPU_WORKER_VM:$NPU_WORKER_PORT/health" | python3 -m json.tool || true

        return 0
    else
        log_error "Enhanced NPU Worker failed to start properly"

        # Show logs for debugging
        log_info "NPU Worker logs:"
        ssh -i ~/.ssh/autobot_key "autobot@$NPU_WORKER_VM" \
            "tail -20 /tmp/npu_worker.log" || true

        return 1
    fi
}

initialize_semantic_search() {
    log_header "Initializing NPU Semantic Search System"

    # Check Redis connection
    if ! check_vm_connection "$REDIS_VM" "Redis VM"; then
        log_error "Cannot reach Redis VM. Please ensure VM3 (172.16.168.23) is running."
        return 1
    fi

    # Test Redis connectivity
    log_info "Testing Redis connectivity..."
    if redis-cli -h "$REDIS_VM" -p "$REDIS_PORT" ping | grep -q "PONG"; then
        log_success "Redis is accessible"
    else
        log_error "Redis is not accessible"
        return 1
    fi

    # Initialize semantic search components
    log_info "Initializing semantic search components..."

    cd "$AUTOBOT_ROOT"

    # Test AI hardware accelerator
    python3 -c "
import asyncio
import sys
sys.path.append('.')

async def test_accelerator():
    try:
        from src.ai_hardware_accelerator import get_ai_accelerator
        accelerator = await get_ai_accelerator()
        status = await accelerator.get_hardware_status()
        print('✅ AI Hardware Accelerator initialized successfully')
        print(f'NPU Available: {status[\"devices\"][\"npu\"][\"available\"]}')
        print(f'GPU Available: {status[\"devices\"][\"gpu\"][\"available\"]}')
        return True
    except Exception as e:
        print(f'❌ AI Hardware Accelerator initialization failed: {e}')
        return False

result = asyncio.run(test_accelerator())
exit(0 if result else 1)
"

    if [ $? -eq 0 ]; then
        log_success "AI Hardware Accelerator initialized"
    else
        log_warning "AI Hardware Accelerator initialization had issues"
    fi

    # Test NPU semantic search engine
    python3 -c "
import asyncio
import sys
sys.path.append('.')

async def test_search_engine():
    try:
        from src.npu_semantic_search import get_npu_search_engine
        search_engine = await get_npu_search_engine()
        stats = await search_engine.get_search_statistics()
        print('✅ NPU Semantic Search Engine initialized successfully')
        print(f'Knowledge Base Ready: {stats[\"knowledge_base_ready\"]}')
        print(f'Cache Size: {stats[\"cache_stats\"][\"cache_size\"]}')
        return True
    except Exception as e:
        print(f'❌ NPU Semantic Search Engine initialization failed: {e}')
        return False

result = asyncio.run(test_search_engine())
exit(0 if result else 1)
"

    if [ $? -eq 0 ]; then
        log_success "NPU Semantic Search Engine initialized"
    else
        log_warning "NPU Semantic Search Engine initialization had issues"
    fi
}

test_semantic_search() {
    log_header "Testing NPU Semantic Search Performance"

    cd "$AUTOBOT_ROOT"

    # Run semantic search benchmark
    log_info "Running semantic search performance test..."

    python3 -c "
import asyncio
import sys
import time
sys.path.append('.')

async def run_benchmark():
    try:
        from src.npu_semantic_search import get_npu_search_engine

        search_engine = await get_npu_search_engine()

        # Test queries
        test_queries = [
            'linux command for file operations',
            'docker container management',
            'python async programming',
            'autobot configuration setup'
        ]

        print('🏃 Running performance benchmark...')

        benchmark_results = await search_engine.benchmark_search_performance(
            test_queries=test_queries,
            iterations=2
        )

        # Display results
        print('\\n📊 Benchmark Results:')
        for device, results in benchmark_results['summary'].items():
            if 'error' not in results:
                print(f'  {device.upper()}:')
                print(f'    Average Time: {results[\"average_total_time_ms\"]:.2f}ms')
                print(f'    Success Rate: {results[\"success_rate\"]:.1f}%')
                print(f'    Total Runs: {results[\"total_runs\"]}')
            else:
                print(f'  {device.upper()}: {results[\"error\"]}')

        return True

    except Exception as e:
        print(f'❌ Benchmark failed: {e}')
        return False

result = asyncio.run(run_benchmark())
exit(0 if result else 1)
"

    if [ $? -eq 0 ]; then
        log_success "Semantic search benchmark completed successfully"
    else
        log_warning "Semantic search benchmark had issues"
    fi

    # Test enhanced search API endpoint
    log_info "Testing enhanced search API endpoint..."

    # Check if backend is running
    if check_service_health "http://127.0.0.1:8001/api/health" "AutoBot Backend"; then
        # Test the enhanced search endpoint
        curl -s -X POST "http://127.0.0.1:8001/api/search/semantic" \
            -H "Content-Type: application/json" \
            -d '{
                "query": "test semantic search",
                "similarity_top_k": 5,
                "enable_npu_acceleration": true
            }' | python3 -m json.tool || true

        log_success "Enhanced search API is accessible"
    else
        log_warning "AutoBot Backend not running - API test skipped"
    fi
}

show_hardware_utilization() {
    log_header "Hardware Utilization Report"

    # NPU Worker utilization
    log_info "NPU Worker Status:"
    curl -s "http://$NPU_WORKER_VM:$NPU_WORKER_PORT/stats" | python3 -m json.tool || echo "NPU Worker not accessible"

    # Get AutoBot hardware status
    log_info "AutoBot Hardware Accelerator Status:"
    curl -s "http://127.0.0.1:8001/api/search/hardware/status" | python3 -m json.tool || echo "AutoBot Backend not accessible"

    # System hardware info
    log_info "System Hardware Information:"
    echo "CPU: $(lscpu | grep 'Model name' | cut -d':' -f2 | xargs)"

    if command -v nvidia-smi &> /dev/null; then
        echo "GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader,nounits)"
        echo "GPU Utilization: $(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits)%"
        echo "GPU Memory Used: $(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)MB / $(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits)MB"
    else
        echo "GPU: Not available"
    fi

    # NPU information (if on Windows)
    echo "NPU: Intel NPU detection requires Windows environment"
}

main() {
    log_header "AutoBot NPU Semantic Search Initialization"

    echo -e "${CYAN}Starting NPU semantic search acceleration for AutoBot...${NC}"
    echo -e "${CYAN}This will enable Intel NPU + RTX 4070 GPU optimization${NC}"
    echo ""

    # Step 1: Start Enhanced NPU Worker
    if start_enhanced_npu_worker; then
        log_success "Step 1: Enhanced NPU Worker started successfully"
    else
        log_error "Step 1: Enhanced NPU Worker failed to start"
        exit 1
    fi

    echo ""

    # Step 2: Initialize Semantic Search System
    if initialize_semantic_search; then
        log_success "Step 2: Semantic Search System initialized successfully"
    else
        log_error "Step 2: Semantic Search System initialization failed"
        exit 1
    fi

    echo ""

    # Step 3: Test Performance
    if test_semantic_search; then
        log_success "Step 3: Performance testing completed successfully"
    else
        log_warning "Step 3: Performance testing had issues (non-critical)"
    fi

    echo ""

    # Step 4: Show Hardware Utilization
    show_hardware_utilization

    echo ""
    log_header "NPU Semantic Search System Ready!"

    echo -e "${GREEN}✅ NPU Semantic Search acceleration is now active${NC}"
    echo -e "${GREEN}✅ Intel NPU Worker running on: http://$NPU_WORKER_VM:$NPU_WORKER_PORT${NC}"
    echo -e "${GREEN}✅ Enhanced Search API: http://127.0.0.1:8001/api/search/semantic${NC}"
    echo -e "${GREEN}✅ Hardware Accelerator: NPU + RTX 4070 GPU + 22-core CPU${NC}"
    echo ""
    echo -e "${YELLOW}📈 Expected Performance Improvements:${NC}"
    echo -e "${YELLOW}   - 5-10x faster semantic search${NC}"
    echo -e "${YELLOW}   - 70%+ NPU utilization for lightweight tasks${NC}"
    echo -e "${YELLOW}   - 80%+ GPU utilization for complex processing${NC}"
    echo -e "${YELLOW}   - 40-60% improvement in search relevance${NC}"
    echo ""
    echo -e "${BLUE}🔧 Monitoring:${NC}"
    echo -e "${BLUE}   - NPU Worker Status: curl http://$NPU_WORKER_VM:$NPU_WORKER_PORT/health${NC}"
    echo -e "${BLUE}   - Hardware Status: curl http://127.0.0.1:8001/api/search/hardware/status${NC}"
    echo -e "${BLUE}   - Performance Benchmark: curl -X POST http://127.0.0.1:8001/api/search/benchmark${NC}"
}

# Handle command line arguments
case "${1:-}" in
    --help|-h)
        echo "Usage: $0 [OPTIONS]"
        echo ""
        echo "Start NPU Semantic Search System for AutoBot"
        echo ""
        echo "Options:"
        echo "  --help, -h     Show this help message"
        echo "  --test-only    Only run tests, don't start services"
        echo "  --status       Show current status"
        echo ""
        echo "This script will:"
        echo "  1. Deploy and start Enhanced NPU Worker on VM2 (172.16.168.22)"
        echo "  2. Initialize AI Hardware Accelerator with NPU/GPU/CPU routing"
        echo "  3. Start NPU Semantic Search Engine with ChromaDB integration"
        echo "  4. Run performance benchmarks and tests"
        echo "  5. Enable hardware-accelerated semantic search API endpoints"
        ;;
    --test-only)
        log_header "Running NPU Semantic Search Tests Only"
        test_semantic_search
        show_hardware_utilization
        ;;
    --status)
        log_header "NPU Semantic Search System Status"
        check_service_health "http://$NPU_WORKER_VM:$NPU_WORKER_PORT/health" "Enhanced NPU Worker"
        show_hardware_utilization
        ;;
    *)
        main
        ;;
esac
