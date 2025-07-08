#!/bin/bash
echo "Starting server for previous UI on port 8081..."
cd frontend/static
python3 -m http.server 8081
