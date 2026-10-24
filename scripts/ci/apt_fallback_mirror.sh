#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
#
# Point apt's Ubuntu archive at a second mirror, for the CI provisioning retry (#19308).
#
# Usage: apt_fallback_mirror.sh APT_DIR MIRROR
# MIRROR is defined once, as the `apt-fallback-mirror` input of .github/actions/setup-python-suite.
# Prints how many apt files it changed. Exit 0 when at least one changed; exit 3 when none
# did, so the caller says so instead of retrying the same slow mirror under another name.
#
# GitHub's runners resolve the archive through `mirror+file:/etc/apt/apt-mirrors.txt` (seen in
# a provision log: "Get:1 file:/etc/apt/apt-mirrors.txt Mirrorlist"), not through a plain
# archive.ubuntu.com URI, so the mirror list is edited too: the fallback goes first, the
# runner's own entries stay after it. security.ubuntu.com is never touched.

set -euo pipefail

apt_dir=${1:?usage: apt_fallback_mirror.sh APT_DIR MIRROR}
mirror=${2:?usage: apt_fallback_mirror.sh APT_DIR MIRROR}
changed=0

# apt's mirror+file method orders entries by their `priority:` field and tries one without it
# LAST (#19345 review), so a plain prepended line would still come after the slow mirror. The
# fallback is written as priority:1 and every kept entry's priority moves up by one.
mirror_list="${apt_dir}/apt-mirrors.txt"
if [ -f "$mirror_list" ] && [ "$(head -n1 "$mirror_list" | cut -f1)" != "$mirror" ]; then
    {
        printf '%s\tpriority:1\n' "$mirror"
        awk -F'\t' -v m="$mirror" 'BEGIN { OFS = "\t" } $1 == m { next }
            { for (i = 2; i <= NF; i++) if ($i ~ /^priority:[0-9]+$/) { split($i, kv, ":"); $i = "priority:" kv[2] + 1 } print }' \
            "$mirror_list"
    } > "${mirror_list}.new"
    mv "${mirror_list}.new" "$mirror_list"
    changed=$((changed + 1))
fi

shopt -s nullglob
for src in "${apt_dir}/sources.list" "${apt_dir}"/sources.list.d/*.sources "${apt_dir}"/sources.list.d/*.list; do
    [ -f "$src" ] || continue
    before=$(cksum < "$src")
    sed -i -E "s#https?://([a-z0-9.-]+\.)?archive\.ubuntu\.com/ubuntu/?#${mirror}#g" "$src"
    [ "$(cksum < "$src")" = "$before" ] || changed=$((changed + 1))
done

echo "$changed"
[ "$changed" -gt 0 ] || exit 3
