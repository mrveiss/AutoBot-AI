#!/bin/bash
# Example: How to install dependency groups in parallel

# Create all requirements files first
create_requirements_files() {
    cat > requirements_group_1.txt << EOF
fastapi>=0.115.0
starlette>=0.47.2
uvicorn>=0.30.0
EOF

    cat > requirements_group_2.txt << EOF
torch>=2.8.0
transformers>=4.53.0
sentence-transformers>=2.2.0
EOF
    # ... other groups
}

# Install groups in parallel
install_parallel() {
    create_requirements_files

    echo "🚀 Installing all dependency groups in parallel..."

    # Start all installs in background
    pip install -r requirements_group_1.txt &
    PID1=$!

    pip install -r requirements_group_2.txt &
    PID2=$!

    pip install -r requirements_group_3.txt &
    PID3=$!

    # Wait for all to complete
    wait $PID1 && echo "✅ Group 1 complete" || echo "❌ Group 1 failed"
    wait $PID2 && echo "✅ Group 2 complete" || echo "❌ Group 2 failed"
    wait $PID3 && echo "✅ Group 3 complete" || echo "❌ Group 3 failed"

    # Clean up
    rm requirements_group_*.txt
}

# Note: This is just an example - dependency conflicts may occur
install_parallel
