#!/bin/bash

# Install Winston logging framework
echo "Installing Winston logging framework..."

# Check if package.json exists
if [ ! -f "package.json" ]; then
    echo "Creating package.json..."
    npm init -y
fi

# Install Winston
npm install winston

echo "Winston installation completed!"
echo "You can now run the playwright-server.js with structured logging"
