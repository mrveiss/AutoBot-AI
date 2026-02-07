#!/bin/bash

# File Upload Functionality Test Script
# Tests the improved file upload capabilities in FileBrowser component

echo "🧪 File Upload Direct Testing"
echo "============================="

# Check if frontend and backend are running
echo "📡 Checking system status..."

# Check frontend (Vue app)
FRONTEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000 2>/dev/null || echo "000")
if [ "$FRONTEND_STATUS" != "200" ]; then
    echo "❌ Frontend not accessible at http://localhost:3000 (status: $FRONTEND_STATUS)"
    echo "   Please start the frontend with 'npm run dev' in autobot-vue/"
    echo ""
fi

# Check backend API
BACKEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/api/system/health 2>/dev/null || echo "000")
if [ "$BACKEND_STATUS" != "200" ]; then
    echo "❌ Backend not accessible at http://localhost:8001 (status: $BACKEND_STATUS)"
    echo "   Please start the backend with './run_agent.sh' or 'python main.py'"
    echo ""
fi

# Check file upload API specifically
FILE_API_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/api/files/stats 2>/dev/null || echo "000")
if [ "$FILE_API_STATUS" != "200" ]; then
    echo "❌ File API not accessible at http://localhost:8001/api/files/ (status: $FILE_API_STATUS)"
    echo "   File upload backend may not be properly initialized"
    echo ""
else
    echo "✅ File upload API is accessible"
    echo ""
fi

# If both are running, run the specific file upload test
if [ "$FRONTEND_STATUS" = "200" ] && [ "$BACKEND_STATUS" = "200" ]; then
    echo "✅ Both frontend and backend are accessible"
    echo ""
    echo "🎯 Testing file upload functionality..."
    echo ""

    # Test the file upload API directly first
    echo "🔧 Testing file upload API directly..."

    # Create a test file
    TEST_FILE="/tmp/autobot_upload_test.txt"
    echo "This is a test file for AutoBot file upload validation." > "$TEST_FILE"
    echo "Created: $(date)" >> "$TEST_FILE"
    echo "Purpose: Validate file upload API functionality" >> "$TEST_FILE"

    # Test file upload via curl
    UPLOAD_RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
        -H "X-User-Role: admin" \
        -F "file=@$TEST_FILE" \
        -F "path=" \
        http://localhost:8001/api/files/upload 2>/dev/null)

    HTTP_STATUS=$(echo "$UPLOAD_RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
    UPLOAD_BODY=$(echo "$UPLOAD_RESPONSE" | grep -v "HTTP_STATUS:")

    if [ "$HTTP_STATUS" = "200" ]; then
        echo "✅ Direct API upload test PASSED"
        echo "   Response: $UPLOAD_BODY"
        echo ""
    else
        echo "❌ Direct API upload test FAILED (status: $HTTP_STATUS)"
        echo "   Response: $UPLOAD_BODY"
        echo ""
    fi

    # Clean up test file
    rm -f "$TEST_FILE"

    echo "🎭 Running Playwright file upload tests..."
    echo ""

    cd autobot-vue

    # Run the specific file upload test
    npx playwright test tests/gui/test_file_upload_functionality.js --headed --workers=1 --timeout=60000

    RESULT=$?

    if [ $RESULT -eq 0 ]; then
        echo ""
        echo "✅ File upload functionality tests PASSED"
        echo "   All file upload improvements are working correctly"
    else
        echo ""
        echo "❌ File upload functionality tests FAILED"
        echo "   There may be issues with the file upload improvements"
    fi

    cd ..
else
    echo "🚫 Cannot run test - system components not fully available"
    echo ""
    echo "To test the file upload improvements:"
    echo "1. Start the backend: ./run_agent.sh"
    echo "2. Start the frontend: cd autobot-vue && npm run dev"
    echo "3. Re-run this test script"
fi

echo ""
echo "📋 File Upload Improvements Summary:"
echo "• Added visible file input with drag & drop UI"
echo "• Enhanced error handling for different file types and sizes"
echo "• Improved accessibility with proper ARIA labels and keyboard navigation"
echo "• Added data-testid attributes for reliable automated testing"
echo "• Maintained backward compatibility with hidden file input"
echo "• Integrated with existing backend file upload API (/api/files/upload)"
echo "• Added proper permission handling with user role headers"
echo "• Enhanced user feedback with detailed error messages"

echo ""
echo "🧪 Available File Upload Methods:"
echo "1. Button Click → Opens file dialog"
echo "2. Visible Input → Direct file selection"
echo "3. Drag & Drop → Visual drop zone (UI ready)"
echo "4. Programmatic → setInputFiles() for automated testing"

echo ""
echo "✨ Testing Commands:"
echo "• Full test suite: ./scripts/testing/test_file_upload.sh"
echo "• Playwright only: cd autobot-vue && npx playwright test tests/gui/test_file_upload_functionality.js"
echo "• Manual testing: Open file browser in AutoBot frontend and try uploading files"
