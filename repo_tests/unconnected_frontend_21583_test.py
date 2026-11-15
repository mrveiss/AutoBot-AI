# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Controls for the frontend half of the unconnected-code gate (#21583).

Each case plants a small frontend tree and asks the real detector (`_unconnected_frontend`) what it finds, so an empty
result on the repository is a measurement ("looked, found nothing") and not "looked at nothing". Every firing case has a
connected twin, and every decoy that must not count as an importer leaves the file unconnected.
"""

from __future__ import annotations

import pytest
from repo_tests import _unconnected_frontend as fe
from repo_tests._unconnected_common import Tree


def _glob(arguments: str, comment: bool = False, generic: str = "") -> str:
    """A planted `import.meta` glob call. This file reads no tree (`Tree.of_files` only); the call is assembled from
    an f-string because a literal dot-glob call in the source matches the guard-reach census regex
    (`_guard_reach_census._ENUMERATOR`), which would misclassify this control-only file as a tree-scanning guard."""
    return ("// " if comment else "") + f"const m = import.meta.glob{generic}({arguments})\n"


_SUBJECT = "autobot-frontend/src/utils/planted.ts"
_BODY = {_SUBJECT: "export const X = 1\n"}


def _found(files: dict[str, str]) -> list[str]:
    """What the detector says about the SUBJECT only.

    The planted importer is itself a candidate nothing imports, so the full result also names it (the case below
    proves that on purpose); every other control asks about the subject alone.
    """
    return [rel for rel in fe.unconnected(Tree.of_files({**_BODY, **files})) if rel == _SUBJECT]


def test_an_importer_nothing_imports_is_itself_reported() -> None:
    """Leaf-only reporting: the subject is connected by `a.ts`, and `a.ts` is the unconnected leaf."""
    importer = "autobot-frontend/src/a.ts"
    result = fe.unconnected(Tree.of_files({**_BODY, importer: "import { X } from '@/utils/planted'\n"}))
    assert result == [importer]


def test_an_unimported_source_file_fires() -> None:
    assert _found({}) == [_SUBJECT]


@pytest.mark.parametrize(
    ("label", "importer"),
    [
        ("alias import", {"autobot-frontend/src/a.ts": "import { X } from '@/utils/planted'\n"}),
        ("relative import with extension", {"autobot-frontend/src/utils/a.ts": "import { X } from './planted.ts'\n"}),
        ("dynamic import", {"autobot-frontend/src/a.ts": "const m = await import('@/utils/planted')\n"}),
        ("require", {"autobot-frontend/src/a.js": "const m = require('../utils/planted')\n"}),
        ("re-export", {"autobot-frontend/src/a.ts": "export * from './utils/planted'\n"}),
        (
            "vue script import",
            {
                "autobot-frontend/src/a.vue": "<template><p>it's</p></template>\n<script setup>\nimport { X } from '@/utils/planted'\n</script>\n"
            },
        ),
        (
            "multi-line named import in a typed script setup",
            {
                "autobot-frontend/src/b.vue": '<template><p>x</p></template>\n<script setup lang="ts">\n'
                "import { ref } from 'vue'\nimport {\n  alpha,\n  beta,\n} from '../utils/planted'\n</script>\n"
            },
        ),
        ("import in another frontend", {"autobot-slm-frontend/src/a.ts": "import { X } from '@/utils/planted'\n"}),
        (
            "html entry script",
            {"autobot-frontend/planted.html": '<script type="module" src="/src/utils/planted.ts"></script>\n'},
        ),
        (
            "html entry script beside a commented one",
            {
                "autobot-frontend/planted.html": '<!-- <script src="/src/utils/old.ts"></script> -->\n'
                '<script type="module" src="/src/utils/planted.ts"></script>\n'
            },
        ),
    ],
)
def test_the_connected_twin_of_each_form_is_clean(label: str, importer: dict[str, str]) -> None:
    assert _found(importer) == [], label


@pytest.mark.parametrize(
    ("label", "decoy"),
    [
        ("a spec importing it", {"autobot-frontend/src/utils/planted.spec.ts": "import { X } from './planted'\n"}),
        (
            "a test directory importing it",
            {"autobot-frontend/src/__tests__/a.ts": "import { X } from '@/utils/planted'\n"},
        ),
        ("a line comment naming it", {"autobot-frontend/src/a.ts": "// import { X } from '@/utils/planted'\n"}),
        ("a block comment naming it", {"autobot-frontend/src/a.ts": "/* import { X } from '@/utils/planted' */\n"}),
        ("a vue template naming it", {"autobot-frontend/src/a.vue": "<template>'@/utils/planted'</template>\n"}),
        (
            "an html comment naming it",
            {
                "autobot-frontend/planted.html": '<!--\n<script type="module" src="/src/utils/planted.ts"></script>\n-->\n'
            },
        ),
        ("the file importing itself", {_SUBJECT: "import { X } from './planted'\nexport const X = 1\n"}),
    ],
)
def test_a_reference_that_does_not_count_leaves_the_file_unconnected(label: str, decoy: dict[str, str]) -> None:
    assert _found(decoy) == [_SUBJECT], label


@pytest.mark.parametrize(
    ("label", "call"),
    [
        ("relative glob", _glob("'./utils/*.ts'")),
        ("recursive glob", _glob("'./**/*.ts', { eager: true }")),
        ("alias glob", _glob("'@/utils/*.ts'")),
        ("rooted glob", _glob("'/src/utils/*.ts'")),
        ("array with a brace set", _glob("['./utils/{planted,other}.ts']")),
        ("typed call", _glob("'./utils/*.ts'", generic="<Record<string, unknown>>")),
    ],
)
def test_a_file_matched_by_a_glob_is_connected(label: str, call: str) -> None:
    assert _found({"autobot-frontend/src/a.ts": call}) == [], label


@pytest.mark.parametrize(
    ("label", "call"),
    [
        ("glob over a sibling directory", _glob("'./views/*.ts'")),
        ("glob of another extension", _glob("'./utils/*.json'")),
        ("single star does not cross a slash", _glob("'./*.ts'")),
        ("negated pattern", _glob("'!./utils/*.ts'")),
        ("glob in a comment", _glob("'./utils/*.ts'", comment=True)),
    ],
)
def test_a_glob_that_does_not_reach_the_file_leaves_it_unconnected(label: str, call: str) -> None:
    assert _found({"autobot-frontend/src/a.ts": call}) == [_SUBJECT], label


@pytest.mark.parametrize(
    ("label", "rel"),
    [
        ("entry point", "autobot-frontend/src/main.ts"),
        ("app shell", "autobot-frontend/src/App.vue"),
        ("declaration file", "autobot-frontend/src/types/shims.d.ts"),
        ("story", "autobot-frontend/src/components/Card.stories.ts"),
        ("spec", "autobot-frontend/src/utils/planted.spec.ts"),
        ("test helper", "autobot-slm-frontend/src/composables/api.testHelper.ts"),
        ("testing support directory", "autobot-slm-frontend/src/testing/mock.ts"),
        ("outside a frontend src tree", "libs/autobot-ui/src/planted.ts"),
    ],
)
def test_a_file_reached_only_by_its_own_glob_is_unconnected() -> None:
    """A glob counts only from ANOTHER file, as an ordinary reference does; the sibling twin is connected."""
    assert _found({_SUBJECT: _glob("'./*.ts'")}) == [_SUBJECT]
    assert _found({"autobot-frontend/src/utils/loader.ts": _glob("'./*.ts'")}) == []


def test_a_file_that_cannot_have_an_importer_is_not_a_candidate(label: str, rel: str) -> None:
    assert fe.candidates(Tree.of_files({rel: "export const X = 1\n"})) == [], label


def test_an_index_file_is_reached_through_its_directory_name() -> None:
    files = {
        "autobot-frontend/src/components/panel/index.ts": "export const X = 1\n",
        "autobot-frontend/src/a.ts": "import { X } from '@/components/panel'\n",
    }
    index = "autobot-frontend/src/components/panel/index.ts"
    assert index not in fe.unconnected(Tree.of_files(files))
    assert fe.unconnected(Tree.of_files({index: files[index]})) == [index]


@pytest.mark.parametrize(
    ("label", "importer", "spec"),
    [
        ("sibling ./index", "autobot-frontend/src/components/panel/consumer.ts", "./index"),
        ("sibling ./index.ts", "autobot-frontend/src/components/panel/consumer.ts", "./index.ts"),
        ("parent ../index", "autobot-frontend/src/components/panel/sub/consumer.ts", "../index"),
    ],
)
def test_a_relative_index_import_is_resolved_against_the_importer(label: str, importer: str, spec: str) -> None:
    """`./index` names the importer's directory; an `./index` in an unrelated directory does not reach this one."""
    index = "autobot-frontend/src/components/panel/index.ts"
    body = f"import {{ X }} from '{spec}'\n"
    assert index not in fe.unconnected(Tree.of_files({index: "export const X = 1\n", importer: body})), label
    elsewhere = {index: "export const X = 1\n", "autobot-frontend/src/views/other/consumer.ts": body}
    assert index in fe.unconnected(Tree.of_files(elsewhere)), label


def test_a_same_named_sibling_marks_the_file_connected_which_is_the_documented_under_report() -> None:
    other = {"autobot-frontend/src/a.ts": "import { X } from '@/views/planted'\n"}
    assert _found(other) == []  # the known limit: stem matching cannot tell the two planted files apart


@pytest.mark.parametrize(
    ("pattern", "matches", "misses"),
    [
        ("a/*.ts", "a/x.ts", "a/b/x.ts"),
        ("a/**/*.ts", "a/b/c/x.ts", "b/x.ts"),
        ("a/**/*.ts", "a/x.ts", "a/x.js"),
        ("a/{x,y}.ts", "a/y.ts", "a/z.ts"),
        ("a/?.ts", "a/x.ts", "a/xy.ts"),
    ],
)
def test_the_glob_translation_means_what_a_glob_means(pattern: str, matches: str, misses: str) -> None:
    regex = fe.glob_regex(pattern)
    assert regex.fullmatch(matches) and not regex.fullmatch(misses)
