# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Character-by-character line normalizer for the no-print-console guard
# (#14051 review round 2). Strips string/template/regex-literal BODIES
# (their punctuation must not count as call structure) and, depending on
# keep_comment, the trailing comment too:
#   keep_comment=0 — used for paren-BALANCE tracking: comment removed, since
#     a comment's stray '(' must not hold a call's "still open" window open.
#   keep_comment=1 — used for MATCHING the call and searching for a noqa:
#     comment kept (that is where a real suppression lives); a noqa written
#     inside a STRING ARGUMENT is still removed with the string, so it can't
#     be mistaken for a real suppression.
#
# Inputs (via -v): lang ("py" or "ts"), keep_comment ("0" or "1"), sq (a
# literal single-quote character, passed in rather than embedded so the
# calling shell never has to quote one inside this program's invocation).
#
# lang="py": '/" strings (backslash-escaped), '#' starts the comment.
# lang="ts": '/"/`" strings including template literals, plus a best-effort
#   `/regex/` literal detector — a '/' preceded by start-of-line or one of
#   ([{,;:=&|!?+-*%^~<> opens a regex literal; anything else (an identifier,
#   ')', ']') is read as division and left alone. Nested ${} inside a
#   template literal is stripped along with the rest of the template body —
#   this only protects OUR call's balance; a real call embedded in an
#   interpolation is simply not analyzed by this pass. '//' starts the
#   comment. Known limitation, like Python's triple-quoted strings: this is
#   a heuristic, not a full lexer (e.g. a '/' inside a regex character class
#   is not modeled) — add an explicit noqa if a line is still misread.

BEGIN {
    punct = "([{,;:=&|!?+-*%^~<>"
}
{
    n = length($0)
    out = ""
    in_str = 0; str_ch = ""
    in_tmpl = 0; in_regex = 0
    prev_sig = ""
    for (i = 1; i <= n; i++) {
        c = substr($0, i, 1)
        if (in_str) {
            if (c == "\\") { i++; continue }
            if (c == str_ch) in_str = 0
            continue
        }
        if (in_tmpl) {
            if (c == "\\") { i++; continue }
            if (c == "`") in_tmpl = 0
            continue
        }
        if (in_regex) {
            if (c == "\\") { i++; continue }
            if (c == "/") { in_regex = 0; prev_sig = "/" }
            continue
        }
        if (c == "\"" || c == sq) { in_str = 1; str_ch = c; continue }
        if (lang == "ts" && c == "`") { in_tmpl = 1; continue }
        if (lang == "py" && c == "#") {
            if (keep_comment == "1") out = out substr($0, i)
            break
        }
        if (lang == "ts" && c == "/") {
            nc = substr($0, i + 1, 1)
            if (nc == "/") {
                if (keep_comment == "1") out = out substr($0, i)
                break
            }
            if (prev_sig == "" || index(punct, prev_sig) > 0) { in_regex = 1; continue }
        }
        out = out c
        if (c !~ /[ \t]/) prev_sig = c
    }
    print out
}
