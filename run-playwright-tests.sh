#!/bin/bash

# AutoBot Playwright Test Runner
# This script starts the necessary services and runs Playwright tests

set -e  # Exit on any error

echo "🚀 Starting AutoBot Playwright Tests..."

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if we're in the right directory
if [ ! -f "autobot-vue/package.json" ]; then
    print_error "Please run this script from the AutoBot root directory"
    exit 1
fi

# Function to cleanup on exit
cleanup() {
    print_status "Cleaning up processes..."

    # Kill any running processes
    pkill -f "python main.py" || true
    pkill -f "vite" || true
    pkill -f "node.*vite" || true

    # Wait a moment for processes to terminate
    sleep 2

    print_status "Cleanup complete"
}

# Set up cleanup trap
trap cleanup EXIT INT TERM

# Start backend in background
print_status "Starting AutoBot backend..."
source venv/bin/activate 2>/dev/null || {
    print_error "Python virtual environment not found. Please run ./setup_agent.sh first"
    exit 1
}

# Start backend in test mode
python main.py --test-mode &
BACKEND_PID=$!

print_status "Backend started with PID: $BACKEND_PID"

# Wait for backend to be ready
print_status "Waiting for backend to be ready..."
max_attempts=30
attempt=0

while [ $attempt -lt $max_attempts ]; do
    if curl -s http://127.0.0.1:8001/api/system/health > /dev/null 2>&1; then
        print_status "Backend is ready!"
        break
    fi

    sleep 1
    attempt=$((attempt + 1))

    if [ $attempt -eq $max_attempts ]; then
        print_error "Backend failed to start within 30 seconds"
        exit 1
    fi
done

# Check KB Librarian status
print_status "Checking KB Librarian status..."
if curl -s http://127.0.0.1:8001/api/kb-librarian/status > /dev/null 2>&1; then
    KB_STATUS=$(curl -s http://127.0.0.1:8001/api/kb-librarian/status | jq -r '.enabled')
    if [ "$KB_STATUS" = "true" ]; then
        print_status "KB Librarian is enabled and ready"
    else
        print_warning "KB Librarian is disabled"
    fi
else
    print_warning "KB Librarian endpoint not accessible"
fi

# Navigate to Vue app directory
cd autobot-vue

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    print_status "Installing frontend dependencies..."
    npm install
fi

# Start frontend in background
print_status "Starting AutoBot frontend..."
npm run dev &
FRONTEND_PID=$!

print_status "Frontend started with PID: $FRONTEND_PID"

# Wait for frontend to be ready
print_status "Waiting for frontend to be ready..."
max_attempts=30
attempt=0

while [ $attempt -lt $max_attempts ]; do
    if curl -s http://127.0.0.1:5173 > /dev/null 2>&1; then
        print_status "Frontend is ready!"
        break
    fi

    sleep 1
    attempt=$((attempt + 1))

    if [ $attempt -eq $max_attempts ]; then
        print_error "Frontend failed to start within 30 seconds"
        exit 1
    fi
done

# Wait a bit more for everything to settle
sleep 3

print_status "Both services are running. Starting Playwright tests..."

# Run different types of tests based on argument
case "${1:-all}" in
    "api")
        print_status "Running KB Librarian API tests..."
        npx playwright test tests/e2e/kb-librarian-api.spec.ts --reporter=html
        ;;
    "chat")
        print_status "Running KB Librarian Chat Integration tests..."
        npx playwright test tests/e2e/kb-librarian-chat.spec.ts --reporter=html
        ;;
    "gui")
        print_status "Running AutoBot GUI tests..."
        npx playwright test tests/e2e/autobot-gui.spec.ts --reporter=html
        ;;
    "headed")
        print_status "Running all tests in headed mode..."
        npx playwright test --headed --reporter=html
        ;;
    "ui")
        print_status "Opening Playwright UI..."
        npx playwright test --ui
        ;;
    "debug")
        print_status "Running tests in debug mode..."
        npx playwright test --debug
        ;;
    "all"|*)
        print_status "Running all Playwright tests..."
        npx playwright test --reporter=html
        ;;
esac

TEST_EXIT_CODE=$?

# Show results
if [ $TEST_EXIT_CODE -eq 0 ]; then
    print_status "✅ All tests completed successfully!"
    print_status "Test report available at: autobot-vue/playwright-report/index.html"
else
    print_error "❌ Some tests failed. Check the report for details."
fi

# Show report
if command -v xdg-open &> /dev/null; then
    print_status "Opening test report in browser..."
    xdg-open playwright-report/index.html 2>/dev/null || true
elif command -v open &> /dev/null; then
    print_status "Opening test report in browser..."
    open playwright-report/index.html 2>/dev/null || true
else
    print_status "Test report saved to: autobot-vue/playwright-report/index.html"
fi

exit $TEST_EXIT_CODE
