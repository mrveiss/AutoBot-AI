# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Upload filenames must be bare names, never paths (#13394).

The upload endpoint validated its target *directory* and then joined the
client-supplied filename to it unchecked. Four guards each missed a filename
carrying a directory component, and the post-write containment check was
lexical, so it neither normalised ``..`` nor ran before the write.

These tests exercise the rejection directly rather than asserting on source
text — the pre-existing coverage for this endpoint only grepped ``files.py``
for the substring ``is_safe_file``, which stays green whether or not the
function actually rejects a traversing name.
"""

import os
from pathlib import Path

import pytest

from api.files import is_safe_file
from autobot_shared.security.path_validator import validate_relative_path

# Extensions the endpoint allows; each escape below therefore clears the
# extension allowlist and is stopped only by the path-component check.
_ALLOWED_SUFFIX = ".py"


@pytest.mark.parametrize(
    "filename",
    [
        "../evil.py",
        "../../evil.py",
        "../../../../etc/passwd.py",
        "subdir/evil.py",
        "./evil.py",
        "/etc/passwd.py",
        "..\\evil.py",
        "dir\\evil.py",
    ],
)
def test_rejects_filenames_carrying_a_directory_component(filename):
    """Any multi-segment or absolute name is refused."""
    assert is_safe_file(filename) is False


# --- layer 2: containment of the resolved target ---------------------------
#
# is_safe_file is only the first layer. The endpoint additionally resolves the
# filename against the validated directory. These tests exercise that second
# layer directly, because layer 1 passing says nothing about it: an earlier
# revision of this fix routed layer 2 through the sandbox *path* resolver, which
# applies a lexical ".." / "~" substring rejection. That is correct for a path
# and wrong for a filename — it 400'd every legitimate name below while layer 1
# and its tests stayed green.


@pytest.mark.parametrize(
    "filename",
    [
        "..leading-dots.py",
        "my..file.py",
        "~notes.md",
        "backup~.txt",
        "draft~1.txt",
        "report..final.md",
        "...rc.yml",
    ],
)
def test_layer_two_accepts_legitimate_names_containing_dots_or_tilde(filename, tmp_path):
    """`..` and `~` inside a bare filename are ordinary characters, not traversal."""
    resolved = validate_relative_path(filename, tmp_path)
    assert resolved.parent == Path(os.path.realpath(tmp_path))
    assert resolved.name == filename


@pytest.mark.parametrize(
    "filename",
    ["../evil.py", "../../etc/passwd.py", "/etc/passwd.py", "sub/../../evil.py"],
)
def test_layer_two_rejects_escapes(filename, tmp_path):
    """Containment is enforced on the resolved path, not on the string."""
    with pytest.raises(ValueError):
        validate_relative_path(filename, tmp_path)


def test_layer_two_rejects_symlink_escape(tmp_path):
    """realpath resolution catches an escape a '..' comparison would miss."""
    outside = tmp_path.parent / "outside_target.py"
    outside.write_text("x", encoding="utf-8")
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    (sandbox / "link.py").symlink_to(outside)
    with pytest.raises(ValueError):
        validate_relative_path("link.py", sandbox)


@pytest.mark.parametrize(
    "filename",
    ["report.py", "notes.txt", "a-b_c.1.py", "..leading-dots.py"],
)
def test_accepts_bare_filenames(filename):
    """A plain name in the allowed-extension set still uploads."""
    assert is_safe_file(filename) is True


def test_absolute_filename_would_discard_the_sandbox_root():
    """Documents why the directory check alone was never sufficient.

    ``pathlib`` join semantics make an absolute filename escape without any
    ``..`` at all: the left operand is discarded outright.
    """
    sandbox = Path("/opt/sandbox")
    assert sandbox / "/etc/passwd" == Path("/etc/passwd")
    assert str(sandbox / "../../etc/passwd").startswith(str(sandbox))


def test_post_write_relative_to_does_not_normalise_traversal():
    """Documents why the trailing containment check could not catch it.

    ``Path.relative_to`` is lexical: it does not resolve ``..``, so a
    traversing path stays 'relative to' the sandbox and raises nothing.
    """
    sandbox = Path("/opt/sandbox")
    escaped = sandbox / "../../etc/passwd"
    assert escaped.relative_to(sandbox) == Path("../../etc/passwd")


def test_extension_allowlist_alone_is_bypassed_by_a_prefix():
    """``Path.suffix`` reads only the final component."""
    assert Path("../../../../etc/passwd.py").suffix == _ALLOWED_SUFFIX
