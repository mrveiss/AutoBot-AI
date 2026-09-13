#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot SLM Frontend - Build & Publish Script (#15650, #15689, #15659)
#
# The shell equivalent of the ONE way provisioning builds and publishes the
# SLM frontend on the Ansible side:
#   autobot-slm-backend/ansible/roles/_shared/tasks/build_publish_slm_frontend.yml
# and the Python self-sync side: autobot-slm-backend/services/slm_frontend_build.py
#
# vite empties its outDir before writing, so a build that fails leaves the
# directory it targeted with nothing in it. nginx serves the SLM bundle with
# `try_files $uri $uri/ /slm/index.html` and autoindex off, so a missing
# index.html answers 403 for EVERY path under /slm/ (#15430, #15462). So a
# build goes into a directory nothing is serving and is published only after
# it is proven to carry a real entry point; a failed or partial build leaves
# the previously working bundle serving and this script exits non-zero
# loudly -- nothing here downgrades a build failure to a warning, which is
# exactly what #15650/#15689 found `bootstrap-slm.sh` doing.
#
# Layout (#15610), identical to both other implementations:
#   dist-<build-id>/     one directory per build; immutable once published
#   current -> dist-<id> THE served path; only ever created, or replaced by a
#                        single rename(2). It never resolves to nothing.
#   previous -> dist-<older-id>  the bundle `current` replaced -- the
#                        rollback target.
#
# Run with the SLM frontend package directory (the one holding package.json
# and the served `current` symlink, e.g. /opt/autobot/autobot-slm-frontend) as
# the current working directory. Two shell entry points install and invoke
# this SAME file rather than each carrying their own copy of the logic:
#   autobot-infrastructure/autobot-slm-backend/scripts/bootstrap-slm.sh
#   sync-frontend.sh
#
# Env:
#   SLM_FRONTEND_RELEASE_KEEP  bundles retained after a publish (default 3 --
#                              same name and default as slm_frontend_build.py
#                              and inventory/group_vars/all.yml's
#                              slm_frontend_release_keep).

set -euo pipefail

release_keep="${SLM_FRONTEND_RELEASE_KEEP:-3}"

if [[ ! -f package.json ]]; then
    echo "FATAL: package.json not found in $(pwd) -- run this from the SLM frontend directory" >&2
    exit 1
fi

# Seed `current` from a pre-#15610 dist/ BEFORE the build runs, so the served
# path resolves even if the build below then fails -- the #15557 invariant: a
# failed build leaves the previous bundle serving.
if [[ ! -e current ]] && [[ ! -L current ]] && [[ -d dist ]]; then
    ln -s dist current
    echo "Seeded current -> dist (adopting the pre-#15610 layout)"
fi

build_id="$(date -u +%Y%m%dT%H%M%S%3NZ)"
build_dir="dist-${build_id}"

echo "Building SLM frontend into ${build_dir} (npm run build:slm)..."
# build:slm = "VITE_API_URL=/slm vite build". The SLM UI is always served
# under `location /slm/` and vite.config sets base /slm/; a plain
# `npm run build` bakes in the wrong API base and the dashboard calls the
# user backend's endpoints instead (#9563, #9710, #10435, #15650).
build_rc=0
npm run build:slm -- --outDir "${build_dir}" --emptyOutDir || build_rc=$?
if [[ "${build_rc}" -ne 0 ]]; then
    echo "FATAL: SLM frontend build failed (rc=${build_rc}). current was NOT touched -- the previous bundle is still being served." >&2
    exit 1
fi

# Size as well as existence: a zero-byte index.html satisfies nginx's
# try_files and then serves a blank page, which no health check notices.
if [[ ! -s "${build_dir}/index.html" ]]; then
    echo "FATAL: ${build_dir}/index.html is missing or empty -- publishing it would make every /slm/ path answer 403. current was NOT touched." >&2
    exit 1
fi

# Read before the flip, because after it `current` names the new bundle.
previous_target=""
if [[ -L current ]]; then
    previous_target="$(readlink current)"
fi

# THE publish. One rename(2) over a symlink: `current` goes straight from the
# old bundle to the new one, with no instant at which it resolves to nothing.
# `ln -sfn <target> current` on its own is NOT this -- GNU ln unlinks the old
# name and then creates the new one, which is the window this replaces.
ln -sfn "${build_dir}" .current.next
mv -T .current.next current
echo "Published ${build_dir} -> current"

if [[ -n "${previous_target}" ]]; then
    ln -sfn "${previous_target}" .previous.next
    mv -T .previous.next previous
fi

# Bounded, or the disk grows by one bundle per deploy forever. Build ids are
# UTC timestamps, so a reverse lexicographic sort of the names IS newest-first.
# The targets of `current` and `previous` are excluded by name rather than
# trusted to fall inside the kept window -- a rollback moves `current` to an
# older bundle, and pruning the bundle being served is the outage this script
# exists to prevent.
keep_current="$(readlink current || true)"
keep_previous="$(readlink previous || true)"
find . -maxdepth 1 -type d -name 'dist-*' -printf '%f\n' \
    | LC_ALL=C sort -r \
    | tail -n +"$((release_keep + 1))" \
    | while IFS= read -r bundle; do
        if [[ "${bundle}" != "${keep_current}" ]] && [[ "${bundle}" != "${keep_previous}" ]]; then
            rm -rf -- "${bundle}"
            echo "Pruned ${bundle}"
        fi
    done
