#!/bin/bash
# Script to replace the GitHub URL in the compiled JavaScript file
sed -i 's|https://github.com/frdel/agent-zero|https://github.com/mrveiss/AutoBot-AI|g' autobot-vue/dist/assets/*.js
echo "GitHub URL updated in compiled JavaScript files."
