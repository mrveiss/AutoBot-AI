# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which frontend spec files a head adds or changes, and which Vitest package runs them (#21509).

The pre-board lane's ``own-specs`` job runs a member's own new Vitest specs before the member boards a
merge train, so a spec that only fails when it first executes fails in minutes and not inside the train.
This module is the selection: given the paths a head changed, it names the specs Vitest would collect,
grouped by the package (the directory that holds a ``vitest.config.*``) that runs them.

What counts as collected is read from the package's own config, never restated here: the ``include`` and
``exclude`` arrays of the config's ``test`` object, with comments removed through the shared comment
syntax. A config without ``include`` collects Vitest's default pattern, one without ``exclude`` gets
Vitest's default excludes. A path that looks like a spec (``*.test.*`` / ``*.spec.*``) but that no package
collects is returned apart, so the job can say so instead of dropping it unseen.
"""

from __future__ import annotations

import re
from pathlib import Path

from tools.lint._comment_syntax import code_text

#: Vitest's config file names, in the order it looks for them.
CONFIG_NAMES = ("vitest.config.ts", "vitest.config.mts", "vitest.config.js", "vitest.config.mjs")

#: A file name that looks like a spec; whether a package collects it is the config's call.
SPEC_NAME = re.compile(r"\.(?:test|spec)\.[cm]?[jt]sx?$")

#: What Vitest collects when the config declares no ``include`` (its ``configDefaults.include``).
DEFAULT_INCLUDE = ("**/*.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}",)

#: What Vitest excludes when the config declares no ``exclude``, and what ``...configDefaults.exclude`` adds.
DEFAULT_EXCLUDE = (
    "**/node_modules/**",
    "**/dist/**",
    "**/cypress/**",
    "**/.{idea,git,cache,output,temp}/**",
    "**/{karma,rollup,webpack,vite,vitest,jest,ava,babel,nyc,cypress,tsup,build,eslint,prettier}.config.*",
)

_QUOTED = re.compile(r"'([^']*)'|\"([^\"]*)\"")
_ARRAY = r"\b{key}\s*:\s*\[((?:[^\]'\"]|'[^']*'|\"[^\"]*\")*)\]"


def expand_braces(pattern: str) -> list[str]:
    """``a.{b,c}`` as ``[a.b, a.c]``; nested groups are expanded too."""
    start = pattern.find("{")
    if start < 0:
        return [pattern]
    depth, parts, last = 0, [], start + 1
    for index in range(start, len(pattern)):
        char = pattern[index]
        depth += (char == "{") - (char == "}")
        if (char == "," and depth == 1) or depth == 0:
            parts.append(pattern[last:index])
            last = index + 1
        if depth == 0:
            tails = expand_braces(pattern[index + 1 :])
            prefix = pattern[:start]
            return [prefix + head + tail for part in parts for head in expand_braces(part) for tail in tails]
    return [pattern]


def _translate(pattern: str) -> str:
    """One brace-free glob as a regular expression: ``**/`` any directories, ``*`` within a segment."""
    out, index = [], 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            out.append("(?:.*/)?")
            index += 3
        elif pattern.startswith("**", index):
            out.append(".*")
            index += 2
        else:
            char = pattern[index]
            out.append("[^/]*" if char == "*" else "[^/]" if char == "?" else re.escape(char))
            index += 1
    return "".join(out)


def glob_matches(path: str, patterns: tuple[str, ...] | list[str]) -> bool:
    """Whether the package-relative *path* matches any of the globs (``**``, ``*``, ``?``, ``{a,b}``)."""
    return any(re.fullmatch(_translate(expanded), path) for pattern in patterns for expanded in expand_braces(pattern))


def _test_object(config: str) -> str:
    """The first ``test: { ... }`` object of *config* without nested objects (quote-aware: a glob's brace is data)."""
    start = re.search(r"\btest\s*:\s*\{", config)
    if start is None:
        return ""
    kept, depth, quote = [], 0, ""
    for char in config[start.end() - 1 :]:
        if quote:
            quote = "" if char == quote else quote
        elif char in "'\"`":
            quote = char
        elif char in "{}":
            depth += 1 if char == "{" else -1
            if depth == 0:
                break
            continue
        if depth == 1:
            kept.append(char)
    return "".join(kept)


def _strings_of(body: str) -> list[str]:
    return [a or b for a, b in _QUOTED.findall(body)]


class UnreadableConfig(ValueError):
    """A config declares its ``test`` rules in a shape this reader cannot evaluate (guessing runs the wrong specs)."""


def _array_rule(config_path: Path, test: str, key: str) -> tuple[list[str], bool] | None:
    """``(globs, spreads the default exclude)`` of the ``key`` array, ``None`` when the key is absent.

    Raises :class:`UnreadableConfig` when the key is there but is not an array of string literals, optionally
    led or followed by ``...configDefaults.exclude`` (``exclude`` only).
    """
    if re.search(rf"\b{key}\s*:", test) is None:
        return None
    found = re.search(_ARRAY.format(key=key), test)
    if found is None:
        raise UnreadableConfig(f"{config_path.name}: test.{key} is not an array literal")
    spread = key == "exclude" and "...configDefaults.exclude" in found.group(1)
    residue = _QUOTED.sub("", found.group(1)).replace("...configDefaults.exclude" if spread else "", "")
    if residue.strip(" \t\r\n,"):
        raise UnreadableConfig(f"{config_path.name}: test.{key} holds something other than string globs")
    return _strings_of(found.group(1)), spread


def package_rules(config_path: Path) -> tuple[list[str], list[str]]:
    """``(include, exclude)`` globs the config at *config_path* declares in its ``test`` object.

    A config with no ``test`` object, or none of the two keys, gets Vitest's defaults (its real behaviour). A ``test``
    that is not an object literal, or a key that is not a readable array, raises :class:`UnreadableConfig`.
    """
    text = code_text(config_path.read_text(encoding="utf-8"), name=config_path.name, strip_trailing=True)
    if re.search(r"\btest\s*:", text) and not re.search(r"\btest\s*:\s*\{", text):
        raise UnreadableConfig(f"{config_path.name}: test is not an object literal")
    test = _test_object(text)
    include = _array_rule(config_path, test, "include")
    exclude = _array_rule(config_path, test, "exclude")
    include_globs = list(DEFAULT_INCLUDE) if include is None else include[0]
    if exclude is None:
        return include_globs, list(DEFAULT_EXCLUDE)
    return include_globs, exclude[0] + (list(DEFAULT_EXCLUDE) if exclude[1] else [])


def package_of(root: Path, path: str) -> str | None:
    """The nearest directory above *path* (below the repository root) that holds a Vitest config."""
    parent = Path(path).parent
    while parent.as_posix() != ".":
        if any((root / parent / name).is_file() for name in CONFIG_NAMES):
            return parent.as_posix()
        parent = parent.parent
    return None


def _config_file(root: Path, package: str) -> Path:
    return next(root / package / name for name in CONFIG_NAMES if (root / package / name).is_file())


def collected(rules: tuple[list[str], list[str]], relative: str) -> bool:
    """Whether Vitest would collect the package-relative *relative* under the ``(include, exclude)`` *rules*."""
    include, exclude = rules
    return glob_matches(relative, include) and not glob_matches(relative, exclude)


def select_specs(root: Path, paths: list[str]) -> tuple[dict[str, list[str]], list[str], list[tuple[str, str]]]:
    """``(by package, notices, unrun)`` for the changed spec files that still exist.

    *by package* are the specs a package collects, relative to it. *notices* are full paths nobody is expected to
    run: a spec outside every package (no config to judge it by), or one a package's own ``exclude`` rule skips on
    purpose. *unrun* are ``(path, package)`` pairs inside a package that neither include nor exclude rules name:
    a spec that looks like coverage and that no job runs.
    """
    selected: dict[str, list[str]] = {}
    notices: list[str] = []
    unrun: list[tuple[str, str]] = []
    rules: dict[str, tuple[list[str], list[str]]] = {}
    for path in sorted(set(paths)):
        if not SPEC_NAME.search(path) or not (root / path).is_file():
            continue
        package = package_of(root, path)
        if package is None:
            notices.append(path)
            continue
        if package not in rules:
            rules[package] = package_rules(_config_file(root, package))
        relative = path[len(package) + 1 :]
        if collected(rules[package], relative):
            selected.setdefault(package, []).append(relative)
        elif glob_matches(relative, rules[package][1]):
            notices.append(path)
        else:
            unrun.append((path, package))
    return selected, notices, unrun


def slug_of(package: str) -> str:
    """The file stem the selection of *package* is written under."""
    return package.replace("/", "__")


def write_selection(selected: dict[str, list[str]], out_dir: Path) -> None:
    """``packages.txt`` (one package directory per line) and ``<slug>.txt`` (its specs, relative to it)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "packages.txt").write_text("".join(f"{p}\n" for p in sorted(selected)), encoding="utf-8")
    for package, files in selected.items():
        (out_dir / f"{slug_of(package)}.txt").write_text("".join(f"{f}\n" for f in files), encoding="utf-8")
