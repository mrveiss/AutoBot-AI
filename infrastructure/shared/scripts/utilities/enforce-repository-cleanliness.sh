#!/bin/bash
# Repository Cleanliness Enforcement Script
# Automatically moves misplaced files to proper directories
# Can be run manually or as a pre-commit hook

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🧹 AUTOBOT REPOSITORY CLEANLINESS ENFORCEMENT${NC}"
echo "=============================================="

violations_found=false

# Check for test files in root
test_files=$(find . -maxdepth 1 -name "test*.py" -o -name "TEST*.py" 2>/dev/null || true)
if [ -n "$test_files" ]; then
    echo -e "${YELLOW}⚠️  Found test files in root directory:${NC}"
    echo "$test_files" | sed 's/^/  /'
    echo "$test_files" | xargs -I {} mv {} tests/ 2>/dev/null || true
    echo -e "${GREEN}  ✅ Moved to tests/${NC}"
    violations_found=true
fi

# Check for report files in root
report_files=$(find . -maxdepth 1 -name "*REPORT*.md" -o -name "*SUMMARY*.md" -o -name "*GUIDE*.md" -o -name "*ANALYSIS*.md" 2>/dev/null || true)
if [ -n "$report_files" ]; then
    echo -e "${YELLOW}⚠️  Found report files in root directory:${NC}"
    echo "$report_files" | sed 's/^/  /'
    echo "$report_files" | xargs -I {} mv {} reports/ 2>/dev/null || true
    echo -e "${GREEN}  ✅ Moved to reports/${NC}"
    violations_found=true
fi

# Check for log files in root
log_files=$(find . -maxdepth 1 -name "*.log" -o -name "*.log.*" 2>/dev/null || true)
if [ -n "$log_files" ]; then
    echo -e "${YELLOW}⚠️  Found log files in root directory:${NC}"
    echo "$log_files" | sed 's/^/  /'
    echo "$log_files" | xargs -I {} mv {} logs/ 2>/dev/null || true
    echo -e "${GREEN}  ✅ Moved to logs/${NC}"
    violations_found=true
fi

# Check for backup files in root
backup_files=$(find . -maxdepth 1 -name "*.bak" -o -name "*.backup" -o -name "*_backup.*" -o -name "*.old" -o -name "*_old.*" 2>/dev/null || true)
if [ -n "$backup_files" ]; then
    echo -e "${YELLOW}⚠️  Found backup files in root directory:${NC}"
    echo "$backup_files" | sed 's/^/  /'
    echo "$backup_files" | xargs -I {} mv {} backups/ 2>/dev/null || true
    echo -e "${GREEN}  ✅ Moved to backups/${NC}"
    violations_found=true
fi

# Check for analysis files in root
analysis_files=$(find . -maxdepth 1 -name "analysis_*.json" -o -name "profile_*.txt" -o -name "trace_*.log" -o -name "benchmark_*.json" 2>/dev/null || true)
if [ -n "$analysis_files" ]; then
    echo -e "${YELLOW}⚠️  Found analysis files in root directory:${NC}"
    echo "$analysis_files" | sed 's/^/  /'
    # Move different types to appropriate directories
    find . -maxdepth 1 -name "analysis_*.json" -exec mv {} analysis/ \; 2>/dev/null || true
    find . -maxdepth 1 -name "profile_*.txt" -exec mv {} reports/performance/ \; 2>/dev/null || true
    find . -maxdepth 1 -name "trace_*.log" -exec mv {} logs/performance/ \; 2>/dev/null || true
    find . -maxdepth 1 -name "benchmark_*.json" -exec mv {} tests/benchmarks/ \; 2>/dev/null || true
    echo -e "${GREEN}  ✅ Moved to appropriate directories${NC}"
    violations_found=true
fi

if [ "$violations_found" = false ]; then
    echo -e "${GREEN}✅ Repository is clean - no violations found!${NC}"
else
    echo ""
    echo -e "${RED}⚠️  REPOSITORY CLEANLINESS VIOLATIONS WERE FOUND AND CORRECTED${NC}"
    echo "Files have been moved to proper directories according to CLAUDE.md standards."
    echo ""
    echo "Please ensure future files are created in the correct directories:"
    echo "  • Test files → tests/"
    echo "  • Reports → reports/"
    echo "  • Logs → logs/"
    echo "  • Backups → backups/"
    echo "  • Analysis → analysis/"
    echo ""
fi

echo "=============================================="
echo -e "${GREEN}🏁 Repository cleanliness enforcement complete${NC}"
