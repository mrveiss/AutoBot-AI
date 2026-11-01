#!/bin/sh
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# #19736: the one model kind check, run by assert_model_kinds.yml and install-bare-metal.sh.
# Prints one verdict per model. Exits 1 only when the model server cannot be reached. OK and ABSENT
# (a chat model not installed: individual pulls may fail, #2950) pass; WRONG-KIND, MISSING-EMBEDDING,
# SHOW-FAILED (listed, but `show` failed) and UNKNOWN (no readable capabilities) fail the caller (#19886).
# Environment: MODEL_CLI, EMBEDDING_MODEL, COMPLETION_MODELS (newline-separated).
listed=$($MODEL_CLI list 2>/dev/null) || { echo "UNREACHABLE model server via: $MODEL_CLI"; exit 1; }
verdict() {  # $1 model  $2 capability the role needs
  if ! out=$($MODEL_CLI show "$1" 2>&1); then
    if printf '%s\n' "$listed" | awk -v m="$1" 'NR>1 && ($1==m || $1==m":latest"){f=1} END{exit !f}'; then
      echo "SHOW-FAILED $1: $(printf '%s' "$out" | tail -n 1)"
    elif [ "$2" = embedding ]; then echo "MISSING-EMBEDDING $1"
    else echo "ABSENT $1"; fi
    return
  fi
  caps=$(printf '%s\n' "$out" | awk '/^[[:space:]]*Capabilities[[:space:]]*$/{f=1;next} f&&NF==0{exit} f{print $1}' | tr '\n' ' ')
  if [ -z "$caps" ]; then echo "UNKNOWN $1"
  elif printf ' %s ' "$caps" | grep -q " $2 "; then echo "OK $1 $2"
  else echo "WRONG-KIND $1 needs=$2 has=[${caps% }]"; fi
}
[ -n "$EMBEDDING_MODEL" ] && verdict "$EMBEDDING_MODEL" embedding
printf '%s\n' "$COMPLETION_MODELS" | while IFS= read -r m; do
  [ -n "$m" ] && [ "$m" != "$EMBEDDING_MODEL" ] && verdict "$m" completion
done
exit 0
