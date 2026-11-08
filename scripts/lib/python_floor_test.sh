#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Unit tests for scripts/lib/python_floor.sh (#20932).
# Run: bash scripts/lib/python_floor_test.sh   (hermetic: mktemp roots only)

set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/lib/python_floor.sh
source "${HERE}/python_floor.sh"
export AUTOBOT_PYTHON_FLOOR_NO_PROVISION=1

pass=0
fail=0
check() {
    if [ "$2" = "$3" ]; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "  FAIL: $1 -- expected [$2], got [$3]"; fi
}

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

echo "3.14" > "$tmp/.python-version"
check "version" "3.14" "$(python_floor_version "$tmp")"
check "binary" "python3.14" "$(python_floor_binary "$tmp")"
echo "3.15" > "$tmp/.python-version"
check "a bump is a one-file edit" "python3.15" "$(python_floor_binary "$tmp")"

echo "latest" > "$tmp/.python-version"
out="$(python_floor_binary "$tmp" 2>&1)"; rc=$?
check "garbage refuses" "1" "$rc"
check "garbage names the file" "yes" "$([[ "$out" == *".python-version"* ]] && echo yes || echo no)"
out="$(python_floor_binary "$tmp/nonexistent" 2>&1)"; rc=$?
check "missing file refuses" "1" "$rc"

echo "3.99" > "$tmp/.python-version"
out="$(python_floor_ensure "$tmp" 2>&1)"; rc=$?
check "missing interpreter refuses" "1" "$rc"
check "refusal names the interpreter" "yes" "$([[ "$out" == *"python3.99 is required"* ]] && echo yes || echo no)"
check "provision cmd has no single quote" "no" "$([[ "$(python_floor_provision_cmd python3.99)" == *"'"* ]] && echo yes || echo no)"

echo "3.14" > "$tmp/.python-version"
cmd="$(python_floor_remote_venv_cmd "$tmp" /x/venv)"
check "remote cmd creates the venv on the floor binary" "yes" "$([[ "$cmd" == *"python3.14 -m venv /x/venv" ]] && echo yes || echo no)"
check "remote cmd has no single quote" "no" "$([[ "$cmd" == *"'"* ]] && echo yes || echo no)"
echo "x" > "$tmp/.python-version"
check "remote cmd refuses on a bad floor" "yes" "$([[ "$(python_floor_remote_venv_cmd "$tmp" /x/venv)" == *"exit 1" ]] && echo yes || echo no)"

printf '3.14' > "$tmp/.python-version"
check "no trailing newline still reads" "3.14" "$(python_floor_version "$tmp")"
echo "3.14" > "$tmp/.python-version"
check "venv dir with metachar refused" "yes" "$([[ "$(python_floor_remote_venv_cmd "$tmp" '/x; rm -rf /')" == *"exit 1" && "$(python_floor_remote_venv_cmd "$tmp" '/x; rm -rf /')" != *"venv /x"* ]] && echo yes || echo no)"
check "remote cmd gates on ubuntu" "yes" "$([[ "$(python_floor_remote_venv_cmd "$tmp" /x/venv)" == *"grep -qx ID=ubuntu"* && "$(python_floor_remote_venv_cmd "$tmp" /x/venv)" != *"|| true"* ]] && echo yes || echo no)"
printf 'NAME=Debian\nID=debian\n' > "$tmp/os-release"
echo "3.99" > "$tmp/.python-version"
unset AUTOBOT_PYTHON_FLOOR_NO_PROVISION
out="$(AUTOBOT_PYTHON_FLOOR_OS_RELEASE="$tmp/os-release" python_floor_ensure "$tmp" 2>&1)"; rc=$?
export AUTOBOT_PYTHON_FLOOR_NO_PROVISION=1
check "non-ubuntu refuses" "1" "$rc"
check "non-ubuntu names OS and interpreter" "yes" "$([[ "$out" == *"debian"* && "$out" == *"python3.99"* ]] && echo yes || echo no)"
mkdir -p "$tmp/v/bin"
printf '#!/bin/sh\necho 3.14\n' > "$tmp/v/bin/python"; chmod +x "$tmp/v/bin/python"
echo "3.14" > "$tmp/.python-version"
python_floor_venv_matches "$tmp" "$tmp/v"; check "venv on floor matches" "0" "$?"
echo "3.15" > "$tmp/.python-version"
python_floor_venv_matches "$tmp" "$tmp/v"; check "venv on older python mismatches" "1" "$?"
python_floor_venv_matches "$tmp" "$tmp/none"; check "missing venv mismatches" "1" "$?"

echo "$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')" > "$tmp/.python-version"
check "present interpreter is returned" "yes" "$([[ "$(python_floor_ensure "$tmp")" == python3.* ]] && echo yes || echo no)"

# python_floor_build_venv, against fake interpreters on PATH (no real venv, no sudo).
mkfake() { # BIN_DIR VERSION: pythonVERSION whose `-m venv DIR` writes DIR/bin/python reporting VERSION
    mkdir -p "$1"
    cat > "$1/python$2" <<EOF
#!/bin/sh
[ "\$1 \$2" = "-m venv" ] || exit 2
mkdir -p "\$3/bin"
printf '#!/bin/sh\\necho $2\\n' > "\$3/bin/python"
chmod +x "\$3/bin/python"
EOF
    chmod +x "$1/python$2"
}
fake="$tmp/fakebin"; mkfake "$fake" 3.14
echo "3.14" > "$tmp/.python-version"
saved_path="$PATH"; PATH="$fake:$PATH"
rm -rf "$tmp/bv"
python_floor_build_venv "$tmp" "$tmp/bv"; check "build_venv creates a venv on the floor interpreter" "0:3.14" "$?:$("$tmp/bv/bin/python")"
mkdir -p "$tmp/old/bin"; printf '#!/bin/sh\necho 3.9\n' > "$tmp/old/bin/python"; chmod +x "$tmp/old/bin/python"; touch "$tmp/old/stale-marker"
python_floor_build_venv "$tmp" "$tmp/old"; rc=$?
check "build_venv rebuilds a venv left on another interpreter" "0:3.14:gone" "$rc:$("$tmp/old/bin/python"):$([ -e "$tmp/old/stale-marker" ] && echo kept || echo gone)"
touch "$tmp/bv/keep-marker"; python_floor_build_venv "$tmp" "$tmp/bv"
check "build_venv keeps a venv already on the floor" "yes" "$([ -e "$tmp/bv/keep-marker" ] && echo yes || echo no)"
echo "3.99" > "$tmp/.python-version"
out="$(python_floor_build_venv "$tmp" "$tmp/nv" 2>&1)"; rc=$?
check "build_venv fails cleanly when the interpreter cannot be ensured" "1:yes:no" "$rc:$([[ "$out" == *"python3.99 is required"* ]] && echo yes || echo no):$([ -e "$tmp/nv" ] && echo yes || echo no)"
echo "x" > "$tmp/.python-version"
python_floor_build_venv "$tmp" "$tmp/nv" >/dev/null 2>&1; check "build_venv refuses a bad .python-version" "1" "$?"
PATH="$saved_path"

echo "python_floor_test: ${pass} passed, ${fail} failed"
[ "$fail" -eq 0 ]
