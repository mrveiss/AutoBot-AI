#!/bin/sh
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# #19736: the one model kind check, run by assert_model_kinds.yml and install-bare-metal.sh.
# Prints one verdict per model. This script is the one definition of what fails (#19886):
#   exit 0  OK, or ABSENT (a chat model not installed: individual pulls may fail, #2950)
#   exit 1  the model server could not be reached
#   exit 2  WRONG-KIND, MISSING-EMBEDDING, SHOW-FAILED (listed, but `show` failed twice) or
#           UNKNOWN (no Capabilities section: an Ollama too old to print one, upgrade it)
# Environment: MODEL_CLI, EMBEDDING_MODEL, COMPLETION_MODELS (newline-separated).
listed=$($MODEL_CLI list 2>/dev/null) || { echo "UNREACHABLE model server via: $MODEL_CLI"; exit 1; }
verdict() {  # $1 model  $2 capability the role needs
  # One retry: a listed model's `show` can fail once while the server is busy.
  if ! out=$($MODEL_CLI show "$1" 2>&1) && { sleep "${MODEL_SHOW_RETRY_DELAY:-3}"; ! out=$($MODEL_CLI show "$1" 2>&1); }; then
    if printf '%s\n' "$listed" | awk -v m="$1" 'NR>1 && ($1==m || $1==m":latest"){f=1} END{exit !f}'; then
      echo "SHOW-FAILED $1: $(printf '%s' "$out" | tail -n 1)"
    elif [ "$2" = embedding ]; then echo "MISSING-EMBEDDING $1"
    else echo "ABSENT $1"; fi
    return
  fi
  caps=$(printf '%s\n' "$out" | awk '/^[[:space:]]*Capabilities[[:space:]]*$/{f=1;next} f&&NF==0{exit} f{print $1}' | tr '\n' ' ')
  if [ -z "$caps" ]; then echo "UNKNOWN $1: no Capabilities section; upgrade Ollama"
  elif printf ' %s ' "$caps" | grep -q " $2 "; then echo "OK $1 $2"
  else echo "WRONG-KIND $1 needs=$2 has=[${caps% }]"; fi
}
judge_all() {
  [ -n "$EMBEDDING_MODEL" ] && verdict "$EMBEDDING_MODEL" embedding
  printf '%s\n' "$COMPLETION_MODELS" | while IFS= read -r m; do
    [ -n "$m" ] && [ "$m" != "$EMBEDDING_MODEL" ] && verdict "$m" completion
  done
}
verdicts=$(judge_all)
[ -z "$verdicts" ] || printf '%s\n' "$verdicts"
if printf '%s\n' "$verdicts" | grep -qE '^(WRONG-KIND|MISSING-EMBEDDING|SHOW-FAILED|UNKNOWN) '; then exit 2; fi
exit 0
