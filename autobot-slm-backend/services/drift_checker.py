# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Drift Checker Service (Issue #2834).

Compares file checksums between the code_source directory and the deployed
directory to detect files that have been manually patched or missed by Ansible.
"""

import ast
import hashlib
import logging
import os
from pathlib import Path
from typing import Dict, List, Tuple

from autobot_shared.time_utils import utc_timestamp
from services.deploy_artifacts import ARTIFACT_DIR_SUFFIXES, ARTIFACT_DIRS
from services.git_tracker import DEFAULT_REPO_PATH

logger = logging.getLogger(__name__)

# File extensions that are meaningful to compare.
#
# Backend/config extensions (Python services, Ansible, shell scripts):
_BACKEND_EXTENSIONS: frozenset[str] = frozenset({".py", ".cfg", ".ini", ".toml", ".yaml", ".yml", ".sh", ".txt"})
# Frontend source extensions (Vue SFC, TypeScript, styles, HTML, manifests).
# These are source files — node_modules/dist/build are excluded by _SKIP_DIRS
# so compiled output is never compared, only source (Issue #10120).
_FRONTEND_EXTENSIONS: frozenset[str] = frozenset(
    {".vue", ".ts", ".tsx", ".js", ".jsx", ".css", ".scss", ".html", ".json"}
)

# Components whose source is primarily frontend files (Issue #10120).
_FRONTEND_COMPONENTS: frozenset[str] = frozenset({"autobot-frontend", "autobot-slm-frontend"})

# Union set — used as the broadest possible filter and by tests that call
# _collect_checksums without a component (backward-compatible default).
_INCLUDE_EXTENSIONS: frozenset[str] = _BACKEND_EXTENSIONS | _FRONTEND_EXTENSIONS


def comparable_extensions(component: str) -> frozenset[str]:
    """Return the file-extension set appropriate for *component* (Issue #10120).

    Frontend components (``autobot-frontend``, ``autobot-slm-frontend``) use
    the full frontend source set so that .vue/.ts/.css files are included in
    the drift comparison.  All other components (Python backends, Ansible
    playbook repos) use only the backend extension set so that stray .ts/.js
    files inside a backend directory are not accidentally compared.

    Args:
        component: Bare component name, e.g. ``"autobot-frontend"``.

    Returns:
        A frozenset of lower-case file-extension strings (e.g. ``".vue"``).
    """
    if component in _FRONTEND_COMPONENTS:
        return _FRONTEND_EXTENSIONS | _BACKEND_EXTENSIONS
    return _BACKEND_EXTENSIONS


# Permitted component names for the /drift endpoint (Issue #3427).
# Only these sub-directories may be requested to prevent path traversal.
ALLOWED_COMPONENTS = frozenset(
    {
        "autobot-slm-backend",
        "autobot-slm-frontend",
        "autobot-backend",
        "autobot-frontend",
        # #10248: the shared library is its own syncable component. Without this,
        # component code could be advanced past the autobot_shared it imports
        # (e.g. a new symbol) with no way to sync the lib and no drift signal,
        # crash-looping every backend that imports it. Resolving it restarts all
        # dependent services (see _COMPONENT_SERVICES in api/code_sync.py).
        "autobot_shared",
        # #12450: worker components promoted from read-only visibility to a real
        # per-component resolve path. Each has an explicit post-sync definition in
        # api/code_sync.py (_WORKER_COMPONENTS / _WORKER_COMPONENT_PIP /
        # _COMPONENT_SERVICES) traced to its actual ansible deploy task — notably
        # the restart target is NOT derivable from the component name for two of
        # them (slm-agent -> autobot-agent, browser-worker -> autobot-playwright).
        "autobot-ai-stack",
        "autobot-npu-worker",
        "autobot-browser-worker",
        "autobot-slm-agent",
    }
)

# Deployed components that are visible to the drift walk but still have NO
# resolve wiring — READ-ONLY. Do NOT add an entry here without either giving it
# a post-sync definition (then it belongs in ALLOWED_COMPONENTS instead) or
# recording why it cannot have one. Whitelisting resolve without post-sync would
# rsync files but never restart the right service — half-working and worse than
# the current 400.
#
# #12450 phase 2 promoted ai-stack, npu-worker, browser-worker and slm-agent out
# of this set into ALLOWED_COMPONENTS once each had a verified post-sync
# definition. `plugins` stays here — see below.
#
# Every entry must be verified against its actual ansible deploy task before
# being added here — see _NONSTANDARD_COMPONENT_PATHS below for the ones whose
# layout isn't the standard code_source/<name> -> /opt/autobot/<name> shape.
#
# NOT resolve-capable (confirmed unmappable, see #12450 PR notes):
#   - autobot-tts-worker: deployed via a single Jinja2-templated file
#     (tts-worker.py.j2 -> tts-worker.py), not a 1:1 sync of the repo's
#     autobot-tts-worker/ directory. It is still VISIBLE — see
#     _TEMPLATED_COMPONENTS, which compares it render-invariantly instead of
#     by directory checksum (#12886). Resolve stays blocked because
#     re-rendering the template needs the ansible var context.
#   - autobot-celery / celery-beat: no distinct deployed directory — both run
#     FROM the autobot-backend deployed dir (systemd WorkingDirectory), so
#     they are already covered by the existing "autobot-backend" entry.
#   - autobot-plugins (the @autobot/vnc, @autobot/terminal npm workspace
#     packages): synced into TWO deployed locations (autobot-frontend/ and
#     autobot-slm-frontend/), so there is no single canonical deployed target
#     to compare against — needs an owner decision on which (or both) to scan.
EXTRA_VISIBILITY_COMPONENTS = frozenset({"plugins", "autobot-tts-worker"})

# Components deployed as a *rendered* Jinja2 template rather than a 1:1 file
# sync (#12886). Maps component -> (template path relative to the repo root,
# rendered file path relative to the deployed component dir).
#
# A directory checksum walk is meaningless for these: the repo dir holds
# different files entirely (autobot-tts-worker/ ships main.py; the host runs
# tts-worker.py), so every file would report source_only/deployed_only. That is
# the fake drift the exclusion above was written to avoid — but excluding the
# component outright traded noise for *no* signal, and the worker silently fell
# behind the backend calling it until a user hit a runtime 404.
#
# _compute_templated_drift compares structure instead: both sides are parsed as
# Python and every string constant is blanked before hashing. Rendering only
# substitutes inside string literals, so a rendered value (install dir, model
# id, port) can never register as drift, while a missing route, dropped helper
# or changed call still does — which is exactly the class of skew that broke
# /tts/synthesize/stream.
_TEMPLATED_COMPONENTS: dict[str, tuple[str, str]] = {
    "autobot-tts-worker": (
        "autobot-slm-backend/ansible/roles/tts-worker/templates/tts-worker.py.j2",
        "tts-worker.py",
    ),
}

# Union of the resolve-capable allowlist and the read-only extras — used by
# the GET-only drift surfaces (/status stale_components, GET /drift). The
# resolve/resolve-async endpoints must keep checking ALLOWED_COMPONENTS only
# (#12450).
VISIBILITY_COMPONENTS = ALLOWED_COMPONENTS | EXTRA_VISIBILITY_COMPONENTS

# Source/deployed path overrides for components whose layout does not follow
# the code_source/<component> -> <SLM_DEPLOYED_ROOT>/<component> convention
# assumed by get_default_source_dir/get_default_deployed_dir (#12450). Paths
# are relative to DEFAULT_REPO_PATH / SLM_DEPLOYED_ROOT respectively. Verified
# against the live ansible deploy tasks — do not add an entry without tracing
# it to the actual unarchive/copy/synchronize task.
_NONSTANDARD_COMPONENT_PATHS: dict[str, tuple[str, str]] = {
    # ai-stack has no top-level code_source/autobot-ai-stack dir; it lives
    # under autobot-infrastructure/ and deploys with --strip-components=4 so
    # the ai-stack/ subtree contents land directly under the deployed root
    # (ansible/playbooks/update-all-nodes.yml ~135-141, ~1060-1064).
    "autobot-ai-stack": (
        "autobot-infrastructure/shared/docker/ai-stack",
        "autobot-ai-stack",
    ),
    # slm-agent has no top-level code_source/autobot-slm-agent dir either;
    # its source of truth is the individual per-file `copy:` tasks in the
    # slm_agent role, all of which live under files/slm/agent/ and land at
    # <slm_agent_dir>/slm/agent/ (ansible/roles/slm_agent/tasks/main.yml
    # ~132-213). config.yaml/role.json/version.json are Jinja2 templates
    # (not raw source files) and are intentionally excluded from this scan.
    "autobot-slm-agent": (
        "autobot-slm-backend/ansible/roles/slm_agent/files/slm/agent",
        "autobot-slm-agent/slm/agent",
    ),
    # plugins/ ships at the repo root, a SIBLING of autobot-backend/, and is
    # rsynced into the backend's own plugins/ subdirectory rather than its
    # own top-level /opt/autobot/plugins tree (ansible/roles/backend/tasks/
    # main.yml #10294).
    "plugins": (
        "plugins",
        "autobot-backend/plugins",
    ),
}


# Directory names / suffixes to skip entirely during traversal. Sourced from the
# canonical deploy-artifact vocabulary (#11459) so the drift walk and the
# code_sync rsync excludes never disagree about what is an artifact — the
# divergence that let ``*.egg-info`` be drift-skipped (#11440) yet still
# rsync-churned. See services/deploy_artifacts.py for the shared definitions.
_SKIP_DIRS = set(ARTIFACT_DIRS)
_SKIP_DIR_SUFFIXES: tuple[str, ...] = ARTIFACT_DIR_SUFFIXES

# Paths that are deployment-generated and never present in the git source tree.
# Exact-match paths and prefix patterns are checked against the POSIX relative
# path of each file before it is added to the drift report (Issue #4610).
#
#   ansible/enroll.yml          — written by install.sh during fleet enrollment
#   ansible/inventory/localhost.yml — node-specific IP/hostname; not in git
#   autobot_shared/             — embedded copy rsync'd from a separate source
#                                  dir by Ansible; intentionally absent from
#                                  code_source/<component>/
_EXPECTED_DRIFT_EXACT: frozenset[str] = frozenset(
    {
        "ansible/enroll.yml",
        "ansible/inventory/localhost.yml",
    }
)

_EXPECTED_DRIFT_PREFIXES: tuple[str, ...] = ("autobot_shared/",)

# Per-component entries that exist ONLY in the deployed tree — the deployment or
# the running service creates them and source has no counterpart (#13851).
# Unlike ``_EXPECTED_DRIFT_EXACT`` these are scoped to the component whose tree
# they sit in, because the same relative path under a different component would
# be ordinary source.
#
# Every entry is protected from the delete-style resolve as well as skipped by
# the drift walk (see ``deploy_only_entries``) — the two disagreeing is what let
# a false drift report recommend deleting live state, the same lockstep
# rationale as #11459.
#
#   autobot-backend/config/npu_workers.yaml — the worker registry, written by
#   NPUWorkerManager._save_workers_to_config() on every worker add/remove/update
#   (services/npu_worker_manager.py). Neither this path nor any source of it
#   exists under autobot-backend/ in the repo; the live file is state, not
#   deployed code. Comparing it reported permanent false drift, and resolving
#   that drift would DELETE the live worker registry.
#
#   <backend>/autobot_shared — a symlink to <root>/autobot_shared created by
#   _ensure_autobot_shared_symlink (#10912) and absent from code_source. Before
#   #13851 every backend resolve deleted it and then recreated it in post-sync;
#   excluding it keeps the symlink in place, and — because the deletion guard
#   refuses on ANY would-be deletion — is what stops every unforced backend
#   resolve from being refused over an entry the deploy itself creates.
_DEPLOY_ONLY_ENTRIES: dict[str, frozenset[str]] = {
    "autobot-backend": frozenset({"config/npu_workers.yaml", "autobot_shared"}),
    "autobot-slm-backend": frozenset({"autobot_shared"}),
}

# Individual files inside an otherwise-1:1 component tree that are deployed as a
# *rendered* Jinja2 template (#13851). Maps component -> {deployed rel path ->
# template path relative to the repo root}.
#
# ``_TEMPLATED_COMPONENTS`` above covers a component that is ENTIRELY a rendered
# file; this covers the far commoner case of one rendered file inside a normal
# directory sync. Both compare the template against the deployed artifact rather
# than excluding it — excluding trades permanent false drift for no signal at
# all, which is the mistake #12886 was written to undo.
#
#   autobot-npu-worker/npu-worker.py — deployed by roles/npu-worker/tasks/
#   code_only.yml:25-26 from npu-worker.py.j2 into {{ npu_install_dir }}. The
#   component's source dir has no npu-worker.py at all, so the walk reported it
#   as permanently untracked while the file it should be compared against sat in
#   the role's templates/ directory.
_RENDERED_FILES: dict[str, dict[str, str]] = {
    "autobot-npu-worker": {
        "npu-worker.py": "autobot-slm-backend/ansible/roles/npu-worker/templates/npu-worker.py.j2",
    },
}


def _deployed_relpath(component: str) -> str:
    """Deployed path of *component* relative to the deployed root.

    Mirrors :func:`get_default_deployed_dir` without the root prefix so
    ownership between component trees can be reasoned about (#13851).
    """
    override = _NONSTANDARD_COMPONENT_PATHS.get(component)
    return override[1] if override else component


def owned_subtrees(component: str) -> frozenset[str]:
    """Sub-paths of *component*'s deployed tree that belong to ANOTHER component.

    ``plugins`` is its own component whose source is ``<repo>/plugins`` but whose
    deployed target is ``<root>/autobot-backend/plugins`` — so the backend's own
    drift walk found 17 plugin files, looked for them under
    ``code_source/autobot-backend/plugins/`` where they have never existed, and
    reported them as drift. They were perfectly in sync with their real source
    (#13851).

    A file owned by another component is that component's business: it must not
    count as drift for the component whose tree it happens to sit in, and it must
    not be deleted by that component's delete-style resolve.

    Args:
        component: Bare component name, e.g. ``"autobot-backend"``.

    Returns:
        Frozenset of POSIX relative sub-paths (e.g. ``{"plugins"}``), empty when
        no other component deploys inside this one.
    """
    prefix = _deployed_relpath(component) + "/"
    return frozenset(
        _deployed_relpath(other)[len(prefix) :]
        for other in VISIBILITY_COMPONENTS
        if other != component and _deployed_relpath(other).startswith(prefix)
    )


def deploy_only_entries(component: str) -> frozenset[str]:
    """Deployed-tree entries of *component* that source never has.

    Runtime-written state, plus deployment-created entries such as the
    ``autobot_shared`` symlink, plus every rendered artifact — anything the
    delete-style resolve would otherwise remove because it cannot find it in
    source. Public so the rsync chokepoint protects them (#13851, same lockstep
    rationale as #11459).

    Rendered artifacts belong here but NOT in the drift-walk skip: rsync must
    not delete ``npu-worker.py`` (its source is a .j2 in the role, not a file in
    the component tree), while the walk must still compare it — see
    ``_rendered_file_drift``.
    """
    return _DEPLOY_ONLY_ENTRIES.get(component, frozenset()) | frozenset(_RENDERED_FILES.get(component, {}))


def _is_expected_drift(
    rel_path: str,
    component: str | None = None,
    owned: frozenset[str] | None = None,
) -> bool:
    """Return True if *rel_path* is a deployment-generated file to exclude.

    Checks against the exact-match set and prefix list defined in
    ``_EXPECTED_DRIFT_EXACT`` and ``_EXPECTED_DRIFT_PREFIXES`` (Issue #4610),
    then the component-scoped subtrees and deploy-only entries (#13851).

    Args:
        rel_path: POSIX-style relative path of the file being evaluated.
        component: Bare component name whose tree is being walked, or ``None``
            for the component-agnostic default.
        owned: Pre-computed ``owned_subtrees(component)``. The caller passes it
            once per walk rather than per file — recomputing it inside a
            several-thousand-file loop rebuilt the same frozenset every time.

    Returns:
        True when the path represents expected (non-actionable) drift.
    """
    if rel_path in _EXPECTED_DRIFT_EXACT:
        return True
    if any(rel_path.startswith(prefix) for prefix in _EXPECTED_DRIFT_PREFIXES):
        return True
    if component is None:
        return False
    # _DEPLOY_ONLY_ENTRIES, not deploy_only_entries(): the latter also carries
    # the rendered artifacts, which rsync must not delete but the walk MUST
    # still compare (#13851).
    if rel_path in _DEPLOY_ONLY_ENTRIES.get(component, frozenset()):
        return True
    subtrees = owned_subtrees(component) if owned is None else owned
    return any(rel_path == sub or rel_path.startswith(sub + "/") for sub in subtrees)


def _file_checksum(path: Path, block_size: int = 65536) -> str:
    """Return the SHA-256 hex digest of a file.

    Reads in blocks to avoid loading large files into memory at once.

    Args:
        path: Absolute path to the file.
        block_size: Read chunk size in bytes.

    Returns:
        Lowercase hex SHA-256 digest string.
    """
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(block_size):
            h.update(chunk)
    return h.hexdigest()


def _collect_checksums(
    root: Path,
    extensions: frozenset[str] | None = None,
) -> Dict[str, str]:
    """Walk *root* and return a mapping of relative-path → SHA-256 checksum.

    Only files whose suffix is in *extensions* are included.  When *extensions*
    is ``None`` the full ``_INCLUDE_EXTENSIONS`` union is used (backward-
    compatible default for tests that call this function without a component).
    Directories in ``_SKIP_DIRS`` are pruned from the walk.

    Args:
        root: Directory to scan.
        extensions: Frozenset of lower-case file-extension strings to include.
            Defaults to ``_INCLUDE_EXTENSIONS`` (the backend ∪ frontend set).

    Returns:
        Dict mapping POSIX-style relative path strings to hex digest strings.
    """
    active_extensions = extensions if extensions is not None else _INCLUDE_EXTENSIONS
    checksums: Dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skip dirs in-place so os.walk does not descend into them. Also
        # prune variable-named build-artifact dirs like ``<pkg>.egg-info`` (#11440).
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.endswith(_SKIP_DIR_SUFFIXES)]

        for filename in filenames:
            filepath = Path(dirpath) / filename
            if filepath.suffix not in active_extensions:
                continue
            try:
                rel = filepath.relative_to(root).as_posix()
                checksums[rel] = _file_checksum(filepath)
            except (OSError, IOError) as exc:
                logger.warning("drift_checker: cannot read %s: %s", filepath, exc)

    return checksums


def _string_constants(tree: ast.AST) -> List[ast.Constant]:
    """String-literal nodes of *tree* in a stable walk order."""
    return [n for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _render_invariant_digests(template_src: str, deployed_src: str | None) -> Tuple[str, str | None] | None:
    """Digest a .j2 template and its rendered file so the two are comparable.

    Only the string literals the template actually *renders* — the ones holding
    a Jinja expression — are blanked, on both sides at the same walk position.
    A substituted install dir or model id therefore cannot read as drift, while
    an ordinary string constant such as a route path still can: blanking every
    literal would have made a renamed ``/tts/synthesize/stream`` invisible,
    which is the very skew this exists to catch (#12886).

    Args:
        template_src: Raw .j2 template text (valid Python — all Jinja
            expressions sit inside string literals).
        deployed_src: The rendered file's text, or ``None`` to digest the
            template alone (deployed file absent).

    Returns:
        Tuple of (template_digest, deployed_digest_or_None), or ``None`` when
        either side does not parse as Python.
    """
    try:
        template_tree = ast.parse(template_src)
    except SyntaxError:
        return None

    template_strings = _string_constants(template_tree)
    rendered_at = [i for i, node in enumerate(template_strings) if "{{" in node.value]

    deployed_strings: List[ast.Constant] = []
    deployed_tree = None
    if deployed_src is not None:
        try:
            deployed_tree = ast.parse(deployed_src)
        except SyntaxError:
            return None
        deployed_strings = _string_constants(deployed_tree)

    for index in rendered_at:
        template_strings[index].value = ""
        # Misaligned lengths mean the structures already differ; the digests
        # will disagree and report drift, which is the right answer.
        if index < len(deployed_strings):
            deployed_strings[index].value = ""

    return (
        _dump_digest(template_tree),
        _dump_digest(deployed_tree) if deployed_tree is not None else None,
    )


def _dump_digest(tree: ast.AST) -> str:
    """SHA-256 over an AST dump."""
    return hashlib.sha256(ast.dump(tree).encode("utf-8")).hexdigest()


def _compute_templated_drift(component: str, deployed_dir: str) -> Tuple[List[dict], int]:
    """Structure-only drift for a template-rendered component (#12886).

    Args:
        component: A key of ``_TEMPLATED_COMPONENTS``.
        deployed_dir: Absolute path to the deployed component directory.

    Returns:
        Tuple of (list_of_drift_dicts, total_files_compared) — same shape as
        ``compute_drift``, always covering the single rendered file.
    """
    template_rel, deployed_rel = _TEMPLATED_COMPONENTS[component]
    template_path = Path(DEFAULT_REPO_PATH) / template_rel
    deployed_path = Path(deployed_dir) / deployed_rel

    try:
        template_src = template_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("drift_checker: cannot read template for %s: %s", component, exc)
        return [], 0

    try:
        deployed_src: str | None = deployed_path.read_text(encoding="utf-8")
    except OSError:
        deployed_src = None

    digests = _render_invariant_digests(template_src, deployed_src)
    if digests is None and deployed_src is not None:
        # The template is known-parseable (pinned by test), so a failure here
        # means the DEPLOYED file no longer parses — real drift. Fall back to
        # its raw checksum, which cannot collide with an AST digest.
        digests = _render_invariant_digests(template_src, None)
        if digests is not None:
            return (
                _templated_drift_entry(deployed_rel, digests[0], _file_checksum(deployed_path), "modified"),
                1,
            )

    if digests is None:
        # An unparseable template is a repo defect, not deployment drift —
        # there is nothing to compare against. Pinned by drift_checker_test.
        logger.error("drift_checker: template does not parse as Python: %s", template_path)
        return [], 0

    source_digest, deployed_digest = digests
    if deployed_digest is None:
        return _templated_drift_entry(deployed_rel, source_digest, None, "source_only"), 1

    if deployed_digest == source_digest:
        return [], 1

    return _templated_drift_entry(deployed_rel, source_digest, deployed_digest, "modified"), 1


def _templated_drift_entry(
    rel_path: str,
    source_digest: str,
    deployed_digest: str | None,
    status: str,
) -> List[dict]:
    """Wrap a templated-component comparison in the standard drift dict shape."""
    return [
        {
            "path": rel_path,
            "source_checksum": source_digest,
            "deployed_checksum": deployed_digest,
            "status": status,
        }
    ]


def _rendered_file_drift(rel_path: str, template_rel: str, deployed_path: Path) -> dict | None:
    """Compare one templated file inside an otherwise 1:1 component tree.

    Same idea as :func:`_compute_templated_drift` (#12886) scoped to a single
    file (#13851), but a template with NO Jinja syntax is compared by raw
    checksum: rendering it is the identity function, so the artifact must match
    byte for byte, and a checksum is the STRONGER check — the AST digest
    discards comment-only and formatting drift in a file that runs on the host.
    ``npu-worker.py.j2`` is exactly that case today, with zero ``{{`` in it.

    Only a template that actually substitutes something falls back to the
    render-invariant AST comparison, so adding a Jinja expression later needs no
    change here — it just moves this file onto the weaker-but-necessary path.

    Args:
        rel_path: POSIX relative path of the deployed file inside the component.
        template_rel: Template path relative to the repo root.
        deployed_path: Absolute path to the deployed rendered file.

    Returns:
        A drift dict, or ``None`` when the rendered file matches its template.
    """
    template_path = Path(DEFAULT_REPO_PATH) / template_rel
    try:
        template_src = template_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("drift_checker: cannot read template %s: %s", template_path, exc)
        return None

    try:
        deployed_src: str | None = deployed_path.read_text(encoding="utf-8")
    except OSError:
        deployed_src = None

    if deployed_src is None:
        return _rendered_entry(rel_path, _text_digest(template_src), None, "source_only")
    if deployed_src == template_src:
        return None

    if not _has_jinja(template_src):
        # Nothing to substitute — the bytes SHOULD have matched, so they differ
        # for a real reason. Falling through to the AST comparison here would
        # forgive a hand-edit that changed only comments or formatting.
        return _rendered_entry(
            rel_path, _text_digest(template_src), _file_checksum(deployed_path), "modified"
        )

    digests = _render_invariant_digests(template_src, deployed_src)
    if digests is None:
        # The template is pinned parseable by drift_checker_test, so a failure
        # here means the DEPLOYED file no longer parses — real drift. Report the
        # raw checksums, which cannot collide with an AST digest.
        return _rendered_entry(
            rel_path, _text_digest(template_src), _file_checksum(deployed_path), "modified"
        )

    source_digest, deployed_digest = digests
    if deployed_digest == source_digest:
        # Bytes differ but only inside rendered values — not drift (#12886).
        return None
    return _rendered_entry(rel_path, source_digest, deployed_digest, "modified")


def _has_jinja(template_src: str) -> bool:
    """True when *template_src* substitutes anything at render time.

    Expressions ``{{ }}`` and statements ``{% %}`` — the two forms that make a
    rendered artifact differ from its template. Comments ``{# #}`` count too:
    they are stripped on render, so the output is not byte-identical either.
    """
    return any(marker in template_src for marker in ("{{", "{%", "{#"))


def _text_digest(text: str) -> str:
    """SHA-256 of *text* as UTF-8 — comparable with :func:`_file_checksum`."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _rendered_entry(rel_path: str, source: str | None, deployed: str | None, status: str) -> dict:
    """Standard drift dict for a rendered-file comparison."""
    return {
        "path": rel_path,
        "source_checksum": source,
        "deployed_checksum": deployed,
        "status": status,
    }


def compute_drift(
    source_dir: str,
    deployed_dir: str,
    component: str | None = None,
) -> Tuple[List[dict], int]:
    """Compare file checksums between *source_dir* and *deployed_dir*.

    Returns a tuple of (drifted_file_dicts, total_compared).

    Each drifted file dict has keys:
        path            – POSIX relative path
        source_checksum – SHA-256 of the source file (None if absent)
        deployed_checksum – SHA-256 of the deployed file (None if absent)
        status          – "modified" | "source_only" | "untracked"

    ``untracked`` (present on the host, absent from this component's source)
    is returned in the same list but partitioned out of ``drift_detected`` by
    :func:`build_drift_report` — see the status assignment below (#13851).

    Files that exist in both directories with identical checksums are not
    included in the returned list.

    Args:
        source_dir: Absolute path to the authoritative code source directory.
        deployed_dir: Absolute path to the currently deployed directory.
        component: Bare component name used to select the correct extension
            set via ``comparable_extensions()``.  When ``None`` the full
            ``_INCLUDE_EXTENSIONS`` union is used (backward-compatible default).

    Returns:
        Tuple of (list_of_drift_dicts, total_files_compared).
    """
    # Template-rendered components never match by directory walk — their repo
    # dir holds different files than the host does (#12886).
    if component in _TEMPLATED_COMPONENTS:
        return _compute_templated_drift(component, deployed_dir)

    src_path = Path(source_dir)
    dep_path = Path(deployed_dir)

    if not src_path.is_dir():
        logger.warning("drift_checker: source_dir does not exist: %s", source_dir)
        return [], 0

    if not dep_path.is_dir():
        logger.warning("drift_checker: deployed_dir does not exist: %s", deployed_dir)
        return [], 0

    extensions = comparable_extensions(component) if component is not None else None
    src_checksums = _collect_checksums(src_path, extensions)
    dep_checksums = _collect_checksums(dep_path, extensions)

    rendered = _RENDERED_FILES.get(component or "", {})
    # Rendered files are always compared, even when neither tree lists them:
    # an absent rendered artifact means the deploy never ran, which is exactly
    # the drift this is for (#13851).
    all_paths = set(src_checksums) | set(dep_checksums) | set(rendered)
    compared = 0
    drifted: List[dict] = []
    owned = owned_subtrees(component) if component is not None else frozenset()

    for rel_path in sorted(all_paths):
        if _is_expected_drift(rel_path, component, owned):
            logger.debug("drift_checker: skipping expected-drift path: %s", rel_path)
            continue

        compared += 1

        if rel_path in rendered:
            entry = _rendered_file_drift(rel_path, rendered[rel_path], dep_path / rel_path)
            if entry is not None:
                drifted.append(entry)
            continue

        src_cs = src_checksums.get(rel_path)
        dep_cs = dep_checksums.get(rel_path)

        if src_cs == dep_cs:
            # Both present and identical — no drift.
            continue

        if src_cs is None:
            # Present on the host, absent from THIS component's source: not out
            # of date, foreign. Reported as its own state so it is visible
            # without being folded into drift_detected — a delete-style resolve
            # is the wrong remedy for a file that source never owned (#13851).
            status = "untracked"
        elif dep_cs is None:
            status = "source_only"
        else:
            status = "modified"

        drifted.append(
            {
                "path": rel_path,
                "source_checksum": src_cs,
                "deployed_checksum": dep_cs,
                "status": status,
            }
        )

    return drifted, compared


def build_drift_report(
    source_dir: str,
    deployed_dir: str,
    component: str | None = None,
) -> dict:
    """Build the full drift report dict for the API response (Issue #2834).

    Args:
        source_dir: Path to code_source directory.
        deployed_dir: Path to deployed component directory.
        component: Bare component name forwarded to ``compute_drift`` so that
            the correct per-component extension set is used (Issue #10120).
            When ``None`` the full ``_INCLUDE_EXTENSIONS`` union is used.

    Returns:
        Dict matching the ``FileDriftReport`` schema.
    """
    entries, total = compute_drift(source_dir, deployed_dir, component)

    # #13851: "present on the host, absent from source" is reported, but it is
    # not drift. Folding it in made stale_components non-empty on a fully-synced
    # host, and the obvious remedy — a delete-style resolve — would have removed
    # the untracked files rather than updating anything.
    drifted = [entry for entry in entries if entry["status"] != "untracked"]
    untracked = [entry for entry in entries if entry["status"] == "untracked"]

    return {
        "source_dir": source_dir,
        "deployed_dir": deployed_dir,
        "drifted_files": drifted,
        "untracked_files": untracked,
        "total_compared": total,
        "drift_detected": len(drifted) > 0,
        "checked_at": utc_timestamp(),
    }


def get_default_deployed_dir(component: str = "autobot-slm-backend") -> str:
    """Return the expected deployed path for *component* under /opt/autobot.

    Reads ``SLM_DEPLOYED_ROOT`` from the environment so the path is
    configurable without hardcoding. Components listed in
    ``_NONSTANDARD_COMPONENT_PATHS`` (#12450) use their verified override
    sub-path instead of the standard ``<root>/<component>`` convention.

    Args:
        component: Sub-directory name under the deployed root.

    Returns:
        Absolute path string for the deployed component directory.
    """
    deployed_root = os.environ.get("SLM_DEPLOYED_ROOT", "/opt/autobot")
    override = _NONSTANDARD_COMPONENT_PATHS.get(component)
    rel_path = override[1] if override else component
    return str(Path(deployed_root) / rel_path)


def get_default_source_dir(component: str = "autobot-slm-backend") -> str:
    """Return the code_source sub-directory for *component*.

    Uses ``DEFAULT_REPO_PATH`` from ``services.git_tracker``, which resolves
    ``SLM_REPO_PATH`` with the same fallback, ensuring a single source of truth.
    Components listed in ``_NONSTANDARD_COMPONENT_PATHS`` (#12450) use their
    verified override sub-path instead of the standard
    ``code_source/<component>`` convention (e.g. ai-stack, which lives under
    ``autobot-infrastructure/``).

    Args:
        component: Sub-directory name inside the code_source repository.

    Returns:
        Absolute path string for the source directory to compare against.
    """
    override = _NONSTANDARD_COMPONENT_PATHS.get(component)
    rel_path = override[0] if override else component
    candidate = Path(DEFAULT_REPO_PATH) / rel_path
    if not candidate.is_dir():
        raise ValueError(f"drift_checker: source component directory does not exist: {candidate}")
    return str(candidate)
