#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
#
# Point apt's Ubuntu archive at a second mirror, but only when that helps (#19308, #21325).
#
# Usage: apt_fallback_mirror.sh APT_DIR MIRROR [--primary-known-bad]
# MIRROR is defined once, as the `apt-fallback-mirror` input of .github/actions/setup-python-suite.
# stdout is the number of apt files changed; every diagnostic goes to stderr. Exit 0 when the fallback was
# applied; exit 3 when it was not (the decision line says why), so the caller never mistakes a no-op for a repoint.
#
# An unprobed mirror is never ordered first: a mirror that accepts connections and then stalls makes apt wait
# out Timeout x (Retries+1) per index file, which is how an unconditional fallback turned into 30-65 minute
# silent hangs (#21325). So:
#   primary archive   fallback mirror   decision
#   healthy           (not probed)      change nothing; restore the original files if a fallback was applied before
#   unhealthy         healthy           apply the fallback
#   unhealthy         unhealthy         change nothing, say so (the retry wrapper and step timeouts decide)
# --primary-known-bad skips the primary probe only: the setup-python-suite action passes it on its second
# download try, after the primary failed a real download. The fallback's own probe is never skipped.
#
# A probe is two small requests per mirror (the suite's InRelease, then its main/binary-amd64/Release), each
# bounded by APT_PROBE_TIMEOUT_S in total (connect + transfer) and required to complete with a non-empty body.
# The second request exists because a mirror can answer the first and then stall on the next index file.
# curl is on every hosted runner this script runs on (workflow steps and the setup-python-suite action).
#
# GitHub's runners resolve the archive through `mirror+file:/etc/apt/apt-mirrors.txt`, not through a plain
# archive.ubuntu.com URI, so the mirror list is edited; the fallback goes first as priority:1 and the runner's
# own entries stay after it (apt can still fail over). Plain archive.ubuntu.com URIs in sources files (older
# images, hand-written sources) are rewritten too. security.ubuntu.com is never touched. Every changed file is
# kept as FILE.pre-fallback, which is what a later run restores from, so a second run gives the same result.

set -euo pipefail

readonly APT_PROBE_TIMEOUT_S="${APT_PROBE_TIMEOUT_S:-10}"   # total seconds for one probe request
readonly BACKUP_SUFFIX=".pre-fallback"

apt_dir=${1:?usage: apt_fallback_mirror.sh APT_DIR MIRROR [--primary-known-bad]}
mirror=${2:?usage: apt_fallback_mirror.sh APT_DIR MIRROR [--primary-known-bad]}
primary_known_bad=0
[ "${3:-}" != "--primary-known-bad" ] || primary_known_bad=1
os_release="${APT_FALLBACK_OS_RELEASE:-/etc/os-release}"
mirror_list="${apt_dir}/apt-mirrors.txt"

say() { echo "apt fallback: $*" >&2; }
not_applied() { say "$1"; echo 0; exit 3; }

shopt -s nullglob
apt_files() { printf '%s\n' "${apt_dir}/sources.list" "${apt_dir}"/sources.list.d/*.sources "${apt_dir}"/sources.list.d/*.list; }

# The file as it was before any fallback: its backup when one exists.
original_of() { if [ -f "$1${BACKUP_SUFFIX}" ]; then echo "$1${BACKUP_SUFFIX}"; else echo "$1"; fi; }

restore_originals() {
    local f restored=0
    for f in "$mirror_list" $(apt_files); do
        [ -f "${f}${BACKUP_SUFFIX}" ] || continue
        mv "${f}${BACKUP_SUFFIX}" "$f"
        restored=$((restored + 1))
    done
    echo "$restored"
}

# The primary archive: the runner's first-priority mirror-list entry, else its first plain archive URI.
primary_uri() {
    local list f uri=""
    list=$(original_of "$mirror_list")
    if [ -f "$list" ]; then
        uri=$(awk -F'\t' -v m="$mirror" '$1 != m && $1 != "" {
            p = 1000000000
            for (i = 2; i <= NF; i++) if ($i ~ /^priority:[0-9]+$/) { split($i, kv, ":"); p = kv[2] + 0 }
            if (n++ == 0 || p < best) { best = p; u = $1 } } END { print u }' "$list")
    fi
    if [ -z "$uri" ]; then
        for f in $(apt_files); do
            [ -f "$(original_of "$f")" ] || continue
            uri=$(grep -ohE -m1 'https?://([a-z0-9.-]+\.)?archive\.ubuntu\.com/ubuntu/?' "$(original_of "$f")" | head -n1 || true)
            [ -z "$uri" ] || break
        done
    fi
    echo "$uri"
}

# probe LABEL BASE_URI: both requests must complete, non-empty, within APT_PROBE_TIMEOUT_S each.
probe() {
    local label=$1 base=${2%/} path out start
    out=$(mktemp)
    for path in "dists/${codename}/InRelease" "dists/${codename}/main/binary-amd64/Release"; do
        start=$SECONDS
        : > "$out"
        if timeout -k 1 "$APT_PROBE_TIMEOUT_S" curl -fsS --connect-timeout "$APT_PROBE_TIMEOUT_S" \
            --max-time "$APT_PROBE_TIMEOUT_S" -o "$out" "${base}/${path}" 2>/dev/null && [ -s "$out" ]; then
            say "${label}: ${path##*/} ok ($((SECONDS - start)) s)"
        else
            say "${label}: ${path##*/} failed or stalled past ${APT_PROBE_TIMEOUT_S} s ($((SECONDS - start)) s)"
            rm -f "$out"
            return 1
        fi
    done
    rm -f "$out"
}

apply_fallback() {
    local src before changed=0
    if [ -f "$mirror_list" ]; then
        cp -p "$mirror_list" "${mirror_list}${BACKUP_SUFFIX}"
        {
            printf '%s\tpriority:1\n' "$mirror"
            awk -F'\t' -v m="$mirror" 'BEGIN { OFS = "\t" } $1 == m { next }
                { for (i = 2; i <= NF; i++) if ($i ~ /^priority:[0-9]+$/) { split($i, kv, ":"); $i = "priority:" kv[2] + 1 } print }' \
                "${mirror_list}${BACKUP_SUFFIX}"
        } > "${mirror_list}.new"
        mv "${mirror_list}.new" "$mirror_list"
        changed=$((changed + 1))
    fi
    for src in $(apt_files); do
        [ -f "$src" ] || continue
        before=$(cksum < "$src")
        cp -p "$src" "${src}${BACKUP_SUFFIX}"
        sed -i -E "s#https?://([a-z0-9.-]+\.)?archive\.ubuntu\.com/ubuntu/?#${mirror}#g" "$src"
        if [ "$(cksum < "$src")" = "$before" ]; then rm -f "${src}${BACKUP_SUFFIX}"; else changed=$((changed + 1)); fi
    done
    echo "$changed"
}

command -v curl >/dev/null 2>&1 || not_applied "curl not found; cannot probe, so the fallback mirror is not applied"
codename=$(. "$os_release" 2>/dev/null && echo "${VERSION_CODENAME:-}") || codename=""
[ -n "$codename" ] || not_applied "no VERSION_CODENAME in ${os_release}; cannot probe, fallback mirror not applied"
primary=$(primary_uri)
[ -n "$primary" ] || not_applied "no Ubuntu archive entry found to repoint; fallback mirror not applied"

if [ "$primary_known_bad" -eq 1 ]; then
    say "primary archive: not probed (caller reports it unhealthy)"
elif probe "primary archive" "$primary"; then
    restored=$(restore_originals)
    not_applied "primary healthy; fallback not applied (${restored} earlier change(s) restored)"
fi

probe "fallback mirror" "$mirror" || not_applied "fallback unhealthy; not applied (primary archive stays as configured)"

restore_originals >/dev/null
changed=$(apply_fallback)
[ "$changed" -gt 0 ] || not_applied "no Ubuntu archive entry found to repoint; fallback mirror not applied"
say "fallback mirror applied to ${changed} apt file(s)"
echo "$changed"
