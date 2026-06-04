#!/usr/bin/env python3
"""
Wrapper for generate_report.py for backward compatibility.

This allows calling either generate-report.py or generate_report.py.
"""
from generate_report import main

if __name__ == '__main__':
    main()
