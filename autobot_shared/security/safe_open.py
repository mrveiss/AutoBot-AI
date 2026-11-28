# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one race-free "open this file below that root" helper (#21289, #20136).

``validate_path`` checks a path and the caller then opens it by name: a component
swapped for a symlink in between is followed out of the root (TOCTOU). Here every
directory below the root is opened ``O_NOFOLLOW | O_DIRECTORY`` relative to the
descriptor already held and the leaf with ``O_NOFOLLOW``, so a swapped component
fails (``OSError`` ELOOP/ENOTDIR) instead of being followed.

A symlinked leaf is resolved by hand, one ``readlink`` at a time, and each target is
re-walked from the root with the same rules, so a link may point elsewhere *inside*
the root but never out of it (:class:`ContainmentError`). Only the root itself is opened by
realpath: its own ancestors are trusted configuration. Linux/POSIX ``openat``
semantics (``dir_fd``, ``O_DIRECTORY``, ``O_NOFOLLOW``) are assumed.
"""

import os
import posixpath
import stat
from typing import Sequence, Tuple

MAX_LINK_HOPS = 8
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
_LEAF_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)


class ContainmentError(OSError):
    """A path left the root, is not a regular file, or chained too many links.

    An ``OSError`` so the one ``except OSError`` a caller already has around a read covers it, like
    the ELOOP/ENOTDIR a swapped directory raises.
    """


def open_dir_no_follow(root: str) -> int:
    """A directory descriptor on *root*: the ROOT is resolved by realpath (trusted configuration).

    Every component below it is opened no-follow by :func:`open_under_root`, not here.
    """
    return os.open(os.path.realpath(root), os.O_RDONLY | os.O_DIRECTORY)


def _walk_parents(root_fd: int, parts: Sequence[str]) -> int:
    """A new descriptor on the directory *parts* below *root_fd*; every step is ``O_NOFOLLOW``."""
    fd = os.dup(root_fd)
    try:
        for part in parts:
            child = os.open(part, _DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _link_target(root_fd: int, parts: Tuple[str, ...]) -> Tuple[str, ...]:
    """The root-relative parts a symlink at *parts* points to; ``ContainmentError`` if it leaves the root."""
    parent = _walk_parents(root_fd, parts[:-1])
    try:
        target = os.readlink(parts[-1], dir_fd=parent)
    finally:
        os.close(parent)
    joined = posixpath.normpath(posixpath.join(*parts[:-1], target)) if parts[:-1] else posixpath.normpath(target)
    if target.startswith("/") or joined == ".." or joined.startswith("../"):
        raise ContainmentError("symlink target is outside the root")
    return tuple(p for p in joined.split("/") if p and p != ".")


def open_under_root(root: str, parts: Sequence[str], follow_links: bool = True) -> Tuple[int, Tuple[str, ...]]:
    """``(fd, final_parts)``: a read-only descriptor on the regular file at *parts* below *root*.

    *final_parts* is where an in-root symlink chain ended (equal to *parts* for a plain file), so
    a caller can apply its exclusion rules to the real location. The caller closes the fd.
    ``OSError`` when a component was swapped for a symlink or is gone, its subclass
    ``ContainmentError`` when a link leads out of the root, the target is not a regular file or the
    chain is too long. ``follow_links=False`` refuses a
    symlinked leaf (``OSError`` ELOOP) instead of resolving it.
    """
    root_fd = open_dir_no_follow(root)
    try:
        current = tuple(parts)
        for _ in range(MAX_LINK_HOPS + 1):
            if not current:
                raise ContainmentError("not a regular file")
            fd = _open_leaf(root_fd, current, follow_links)
            if fd is not None:
                return fd, current
            current = _link_target(root_fd, current)
        raise ContainmentError("too many symlink hops")
    finally:
        os.close(root_fd)


def _open_leaf(root_fd: int, parts: Tuple[str, ...], follow_links: bool) -> int | None:
    """The regular-file fd at *parts*, or ``None`` when the leaf is a symlink to resolve (ELOOP)."""
    parent = _walk_parents(root_fd, parts[:-1])
    try:
        try:
            fd = os.open(parts[-1], _LEAF_FLAGS, dir_fd=parent)
        except OSError as exc:
            if (
                follow_links
                and exc.errno == getattr(os, "ELOOP", 40)
                and stat.S_ISLNK(os.lstat(parts[-1], dir_fd=parent).st_mode)
            ):
                return None
            raise
    finally:
        os.close(parent)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise ContainmentError("not a regular file")
    return fd


def read_text_under_root(root: str, parts: Sequence[str], encoding: str = "utf-8", errors: str = "strict") -> str:
    """Text of the file at *parts* below *root*, read through :func:`open_under_root`."""
    fd, _ = open_under_root(root, parts)
    with os.fdopen(fd, "r", encoding=encoding, errors=errors) as handle:
        return handle.read()
