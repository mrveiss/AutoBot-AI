#!/bin/bash
"""
AutoBot Phase 9 Test Execution Script
=====================================

Automated test execution for all Phase 9 features with comprehensive reporting.

Usage:
    bash tests/run_phase9_tests.sh [OPTIONS]
    
Options:
    --quick         Quick test (core functionality only)
    --full          Full test suite including performance tests
    --integration   Integration tests only
    --performance   Performance tests only
    --ci            CI/CD mode (minimal output, JSON results)
    --verbose       Verbose output
    --help          Show this help message
"""

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default configuration
AUTOBOT_ROOT="/home/kali/Desktop/AutoBot"
TEST_MODE="full"
VERBOSE=false
CI_MODE=false
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="$AUTOBOT_ROOT/tests/results"

# Ensure results directory exists
mkdir -p "$RESULTS_DIR"

# Function to print colored output
print_status() {
    local status=$1
    local message=$2
    case $status in
        "INFO")
            echo -e "${BLUE}ℹ️  $message${NC}"
            ;;
        "SUCCESS")
            echo -e "${GREEN}✅ $message${NC}"
            ;;
        "WARNING")
            echo -e "${YELLOW}⚠️  $message${NC}"
            ;;
        "ERROR")
            echo -e "${RED}❌ $message${NC}"
            ;;
        "HEADER")
            echo -e "${CYAN}🚀 $message${NC}"
            ;;
    esac
}

# Function to check prerequisites
check_prerequisites() {
    print_status "INFO" "Checking prerequisites..."
    
    # Check Python version
    if ! python3 --version | grep -q "Python 3"; then
        print_status "ERROR" "Python 3 is required"
        exit 1
    fi
    
    # Check required Python packages
    local required_packages=("requests" "websockets" "redis" "asyncio")
    for package in "${required_packages[@]}"; do
        if ! python3 -c "import $package" 2>/dev/null; then
            print_status "WARNING" "Python package '$package' not found, installing..."
            pip3 install "$package" || {
                print_status "ERROR" "Failed to install $package"
                exit 1
            }
        fi
    done
    
    # Check AutoBot services status
    print_status "INFO" "Checking AutoBot services..."
    
    # Check backend
    if curl -s http://172.16.168.20:8001/api/health >/dev/null 2>&1; then
        print_status "SUCCESS" "Backend API accessible"
    else
        print_status "WARNING" "Backend API not accessible - some tests may fail"
    fi
    
    # Check Redis
    if redis-cli -h 172.16.168.23 -p 6379 ping >/dev/null 2>&1; then
        print_status "SUCCESS" "Redis accessible"
    else
        print_status "WARNING" "Redis not accessible - database tests may fail"
    fi
    
    # Check VNC
    if curl -s http://localhost:6080/vnc.html >/dev/null 2>&1; then
        print_status "SUCCESS" "VNC desktop accessible"
    else
        print_status "WARNING" "VNC desktop not accessible - desktop tests may fail"
    fi
}

# Function to run specific test category
run_test_category() {
    local category=$1
    local test_args=$2
    
    print_status "HEADER" "Running $category tests..."
    
    local start_time=$(date +%s)
    local test_output="$RESULTS_DIR/${category}_test_output_$TIMESTAMP.log"
    local test_results="$RESULTS_DIR/${category}_test_results_$TIMESTAMP.json"
    
    cd "$AUTOBOT_ROOT"
    
    case $category in
        "comprehensive")
            python3 tests/phase9_comprehensive_test_suite.py $test_args \
                > "$test_output" 2>&1 || true
            ;;
        "multi_agent")
            python3 tests/test_multi_agent_workflow_validation.py \
                > "$test_output" 2>&1 || true
            ;;
        "api")
            python3 tests/test_api_endpoints_comprehensive.py \
                > "$test_output" 2>&1 || true
            ;;
        "frontend")
            python3 tests/test_frontend_comprehensive.py \
                > "$test_output" 2>&1 || true
            ;;
        "system")
            python3 tests/test_comprehensive_system_validation.py \
                > "$test_output" 2>&1 || true
            ;;
        "performance")
            python3 tests/performance/test_performance_optimization.py \
                > "$test_output" 2>&1 || true
            ;;
        "security")
            python3 tests/security/test_security_validation.py \
                > "$test_output" 2>&1 || true
            ;;
    esac
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    # Check test results
    if grep -q "FAIL\|ERROR" "$test_output"; then
        print_status "WARNING" "$category tests completed with issues (${duration}s)"
        if [ "$VERBOSE" = true ]; then
            echo "Recent failures:"
            grep -A 2 -B 2 "FAIL\|ERROR" "$test_output" | tail -10
        fi
    else
        print_status "SUCCESS" "$category tests completed successfully (${duration}s)"
    fi
    
    # Extract JSON results if available
    if grep -q "Test Suite Complete" "$test_output"; then
        local json_file=$(grep -o "/home/kali/Desktop/AutoBot/tests/results/[^[:space:]]*\.json" "$test_output" | head -1)
        if [ -n "$json_file" ] && [ -f "$json_file" ]; then
            cp "$json_file" "$test_results"
            print_status "INFO" "Results saved to: $test_results"
        fi
    fi
}

# Function to generate consolidated report
generate_consolidated_report() {
    print_status "HEADER" "Generating consolidated test report..."
    
    local report_file="$RESULTS_DIR/phase9_consolidated_report_$TIMESTAMP.json"
    local summary_file="$RESULTS_DIR/phase9_consolidated_summary_$TIMESTAMP.txt"
    
    # Create consolidated report structure
    cat > "$report_file" <<EOF
{
    "autobot_phase9_test_execution": {
        "timestamp": "$TIMESTAMP",
        "test_mode": "$TEST_MODE",
        "execution_summary": {
            "total_test_categories": 0,
            "successful_categories": 0,
            "failed_categories": 0,
            "total_duration": 0
        },
        "category_results": {},
        "overall_status": "UNKNOWN",
        "recommendations": []
    }
}
EOF
    
    # Process individual test results
    local total_categories=0
    local successful_categories=0
    local total_tests=0
    local passed_tests=0
    
    for result_file in "$RESULTS_DIR"/*_test_results_$TIMESTAMP.json; do
        if [ -f "$result_file" ]; then
            local category=$(basename "$result_file" | cut -d'_' -f1)
            ((total_categories++))
            
            # Extract test statistics
            if jq -e '.summary.passed' "$result_file" >/dev/null 2>&1; then
                local category_passed=$(jq -r '.summary.passed' "$result_file")
                local category_total=$(jq -r '.summary.total_tests' "$result_file")
                
                ((total_tests += category_total))
                ((passed_tests += category_passed))
                
                if [ "$category_passed" -eq "$category_total" ]; then
                    ((successful_categories++))
                fi
            fi
        fi
    done
    
    # Calculate overall pass rate
    local pass_rate=0
    if [ "$total_tests" -gt 0 ]; then
        pass_rate=$(( (passed_tests * 100) / total_tests ))
    fi
    
    # Determine overall status
    local overall_status="FAIL"
    if [ "$pass_rate" -ge 90 ]; then
        overall_status="EXCELLENT"
    elif [ "$pass_rate" -ge 80 ]; then
        overall_status="GOOD"
    elif [ "$pass_rate" -ge 70 ]; then
        overall_status="ACCEPTABLE"
    fi
    
    # Create summary report
    cat > "$summary_file" <<EOF
AutoBot Phase 9 Test Execution Summary
=====================================

Execution Details:
  Timestamp: $TIMESTAMP
  Test Mode: $TEST_MODE
  Overall Status: $overall_status

Results Summary:
  Total Test Categories: $total_categories
  Successful Categories: $successful_categories
  Total Tests Executed: $total_tests
  Tests Passed: $passed_tests
  Overall Pass Rate: ${pass_rate}%

Category Breakdown:
EOF
    
    # Add category details to summary
    for result_file in "$RESULTS_DIR"/*_test_results_$TIMESTAMP.json; do
        if [ -f "$result_file" ]; then
            local category=$(basename "$result_file" | cut -d'_' -f1)
            if jq -e '.summary' "$result_file" >/dev/null 2>&1; then
                local cat_passed=$(jq -r '.summary.passed' "$result_file")
                local cat_total=$(jq -r '.summary.total_tests' "$result_file")
                local cat_rate=$(jq -r '.summary.pass_rate' "$result_file")
                
                echo "  $category: $cat_passed/$cat_total (${cat_rate}%)" >> "$summary_file"
            fi
        fi
    done
    
    echo "" >> "$summary_file"
    echo "Detailed results available in: $RESULTS_DIR" >> "$summary_file"
    
    print_status "SUCCESS" "Consolidated report generated: $summary_file"
    
    # Display summary if not in CI mode
    if [ "$CI_MODE" = false ]; then
        echo ""
        cat "$summary_file"
        echo ""
    fi
}

# Function to run health check before tests
run_health_check() {
    print_status "INFO" "Running pre-test health check..."
    
    local health_script="$AUTOBOT_ROOT/tests/quick_api_test.py"
    if [ -f "$health_script" ]; then
        cd "$AUTOBOT_ROOT"
        if python3 "$health_script" >/dev/null 2>&1; then
            print_status "SUCCESS" "System health check passed"
            return 0
        else
            print_status "WARNING" "System health check failed - proceeding with caution"
            return 1
        fi
    else
        print_status "WARNING" "Health check script not found"
        return 1
    fi
}

# Function to cleanup old test results
cleanup_old_results() {
    print_status "INFO" "Cleaning up old test results..."
    
    # Keep only last 10 test runs
    find "$RESULTS_DIR" -name "*test_results_*.json" -type f | sort -r | tail -n +11 | xargs rm -f
    find "$RESULTS_DIR" -name "*test_output_*.log" -type f | sort -r | tail -n +11 | xargs rm -f
    find "$RESULTS_DIR" -name "*summary_*.txt" -type f | sort -r | tail -n +11 | xargs rm -f
    
    print_status "SUCCESS" "Cleanup completed"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --quick)
            TEST_MODE="quick"
            shift
            ;;
        --full)
            TEST_MODE="full"
            shift
            ;;
        --integration)
            TEST_MODE="integration"
            shift
            ;;
        --performance)
            TEST_MODE="performance"
            shift
            ;;
        --ci)
            CI_MODE=true
            shift
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        --help)
            grep "^\"\"\"" "$0" -A 20 | grep -v "^\"\"\"" | head -n -1
            exit 0
            ;;
        *)
            print_status "ERROR" "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Main execution
main() {
    local start_time=$(date +%s)
    
    print_status "HEADER" "AutoBot Phase 9 Comprehensive Test Suite"
    print_status "INFO" "Test Mode: $TEST_MODE"
    print_status "INFO" "Timestamp: $TIMESTAMP"
    
    # Prerequisites check
    check_prerequisites
    
    # Cleanup old results
    cleanup_old_results
    
    # Health check
    run_health_check
    
    # Determine test categories based on mode
    local test_categories=()
    local test_args=""
    
    case $TEST_MODE in
        "quick")
            test_categories=("comprehensive")
            test_args="--integration=false"
            ;;
        "full")
            test_categories=("comprehensive" "multi_agent" "api" "frontend" "system" "performance")
            test_args="--performance --integration"
            ;;
        "integration")
            test_categories=("comprehensive" "multi_agent" "api" "frontend")
            test_args="--integration"
            ;;
        "performance")
            test_categories=("comprehensive" "performance")
            test_args="--performance"
            ;;
    esac
    
    if [ "$VERBOSE" = true ]; then
        test_args="$test_args --verbose"
    fi
    
    # Execute test categories
    for category in "${test_categories[@]}"; do
        run_test_category "$category" "$test_args"
    done
    
    # Generate consolidated report
    generate_consolidated_report
    
    local end_time=$(date +%s)
    local total_duration=$((end_time - start_time))
    
    print_status "SUCCESS" "Test suite execution completed in ${total_duration}s"
    
    # CI mode output
    if [ "$CI_MODE" = true ]; then
        echo "PHASE9_TEST_RESULTS_FILE=$RESULTS_DIR/phase9_consolidated_report_$TIMESTAMP.json"
        echo "PHASE9_TEST_SUMMARY_FILE=$RESULTS_DIR/phase9_consolidated_summary_$TIMESTAMP.txt"
    fi
}

# Trap to ensure cleanup on exit
trap 'print_status "INFO" "Test execution interrupted"' INT TERM

# Execute main function
main "$@"