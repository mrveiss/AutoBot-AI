#!/bin/bash

# Git askpass helper script for AutoBot project
# This script handles Git credential prompts

case "$1" in
    *Username*|*username*)
        echo "Enter your Git username:"
        read -r username
        echo "$username"
        ;;
    *Password*|*password*|*token*)
        echo "Enter your Git password/token:"
        read -rs password
        echo "$password"
        ;;
    *)
        echo "Git credential prompt: $1"
        read -rs response
        echo "$response"
        ;;
esac
