#!/usr/bin/env python3
"""Tests for tools/build_bundle.py. Uses a temporary fake repo; no real protocol needed.

Run:  python3 tools/test_build_bundle.py   (or: python3 -m unittest tools.test_build_bundle)
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_bundle as bb  # noqa: E402

RAW = "https://raw.githubusercontent.com/example/repo/main/"


def make_repo(root: Path, modules: list[dict] | None = None, files: dict[str, str] | None = None) -> None:
    files = files if files is not None else {
        "START_HERE.md": "# Start\n\nRead [the preamble](protocol/preamble.md) then [schemas](schemas/) "
                         "and [a script](scripts/merge.py). See `[code](protocol/preamble.md)`.\n",
        "protocol/preamble.md": "# Preamble\n\nBack to [start](../START_HERE.md#top) and on to "
                                "[search](search.md#wave) or [templates](templates/x.md).\n\n"
                                "```\n[in fence](search.md)\n```\n",
        "protocol/search.md": "# Search\n\n![img](../docs/assets/flow.png)\n\n[ext](https://example.org/a) [top](#x)\n",
        "protocol/optional.md": "# Optional\n",
        "protocol/templates/x.md": "template\n",
        "docs/assets/flow.png": "png",
        "scripts/merge.py": "print()\n",
        "schemas/a.json": "{}",
    }
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    if modules is None:
        modules = [
            {"id": "preamble", "path": "protocol/preamble.md", "title": "Preamble", "purpose": "p",
             "depends_on": [], "bundle": True},
            {"id": "search", "path": "protocol/search.md", "title": "Search", "purpose": "s",
             "depends_on": ["preamble"], "bundle": True},
            {"id": "optional", "path": "protocol/optional.md", "title": "Optional", "purpose": "o",
             "depends_on": [], "bundle": False},
        ]
    index = {"protocol": "Test Protocol", "version": "9.9.9", "raw_base": RAW,
             "entry": "START_HERE.md", "modules": modules}
    (root / "protocol").mkdir(exist_ok=True)
    (root / "protocol" / "index.json").write_text(json.dumps(index), encoding="utf-8")


def run_cli(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = bb.run(list(argv))
    return code, out.getvalue(), err.getvalue()


class BuildTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def build_text(self) -> str:
        code, _, err = run_cli("--root", str(self.root))
        self.assertEqual(code, 0, err)
        return (self.root / "dist" / "VIRGIL_PROTOCOL_FULL.md").read_text(encoding="utf-8")

    def test_structure_and_order(self):
        make_repo(self.root)
        text = self.build_text()
        self.assertIn("# Test Protocol - full bundle (v9.9.9)", text)
        self.assertIn("GENERATED FILE - DO NOT EDIT", text)
        self.assertIn("## Table of contents", text)
        i_entry = text.index("<!-- MODULE:entry path=START_HERE.md -->")
        i_pre = text.index("<!-- MODULE:preamble path=protocol/preamble.md -->")
        i_search = text.index("<!-- MODULE:search path=protocol/search.md -->")
        self.assertTrue(i_entry < i_pre < i_search)
        self.assertNotIn("MODULE:optional", text)  # bundle: false is skipped
        self.assertIn('<a id="module-search"></a>', text)

    def test_link_rewriting(self):
        make_repo(self.root)
        text = self.build_text()
        # bundled targets become anchors (fragments dropped)
        self.assertIn("[the preamble](#module-preamble)", text)
        self.assertIn("[start](#module-entry)", text)
        self.assertIn("[search](#module-search)", text)
        # non-bundled files and directories go to raw_base / tree URLs
        self.assertIn(f"[templates]({RAW}protocol/templates/x.md)", text)
        self.assertIn(f"[a script]({RAW}scripts/merge.py)", text)
        self.assertIn("[schemas](https://github.com/example/repo/tree/main/schemas/)", text)
        self.assertIn(f"![img]({RAW}docs/assets/flow.png)", text)
        # untouched: external, pure fragment, code span, fenced code
        self.assertIn("[ext](https://example.org/a)", text)
        self.assertIn("[top](#x)", text)
        self.assertIn("`[code](protocol/preamble.md)`", text)
        self.assertIn("[in fence](search.md)", text)

    def test_deterministic_and_check(self):
        make_repo(self.root)
        first = self.build_text()
        self.assertEqual(first, self.build_text())
        code, out, _ = run_cli("--root", str(self.root), "--check")
        self.assertEqual(code, 0)
        self.assertIn("up to date", out)
        # make it stale
        (self.root / "protocol" / "search.md").write_text("# Search\n\nchanged\n", encoding="utf-8")
        code, _, err = run_cli("--root", str(self.root), "--check")
        self.assertEqual(code, 1)
        self.assertIn("stale", err)
        # check must not modify the file
        self.assertEqual((self.root / "dist" / "VIRGIL_PROTOCOL_FULL.md").read_text(encoding="utf-8"), first)

    def test_check_missing_bundle(self):
        make_repo(self.root)
        code, _, err = run_cli("--root", str(self.root), "--check")
        self.assertEqual(code, 1)
        self.assertIn("does not exist", err)


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def expect_error(self, modules: list[dict], needle: str):
        make_repo(self.root, modules=modules)
        code, _, err = run_cli("--root", str(self.root))
        self.assertEqual(code, 2, err)
        self.assertIn(needle, err)

    def test_duplicate_ids(self):
        m = {"id": "a", "path": "protocol/preamble.md", "depends_on": [], "bundle": True}
        self.expect_error([m, dict(m, path="protocol/search.md")], "duplicate id")

    def test_missing_path(self):
        self.expect_error([{"id": "a", "path": "protocol/nope.md", "depends_on": [], "bundle": True}],
                          "file does not exist")

    def test_unknown_dependency(self):
        self.expect_error([{"id": "a", "path": "protocol/preamble.md", "depends_on": ["ghost"], "bundle": True}],
                          "unknown module id 'ghost'")

    def test_cycle_reported_clearly(self):
        self.expect_error(
            [{"id": "a", "path": "protocol/preamble.md", "depends_on": ["b"], "bundle": True},
             {"id": "b", "path": "protocol/search.md", "depends_on": ["c"], "bundle": True},
             {"id": "c", "path": "protocol/optional.md", "depends_on": ["a"], "bundle": True}],
            "dependency cycle: a -> b -> c -> a")

    def test_path_escape_rejected(self):
        self.expect_error([{"id": "a", "path": "../outside.md", "depends_on": [], "bundle": True}],
                          "escapes the repo root")

    def test_bad_id(self):
        self.expect_error([{"id": "Bad Id", "path": "protocol/preamble.md", "depends_on": [], "bundle": True}],
                          "must match")

    def test_invalid_json(self):
        make_repo(self.root)
        (self.root / "protocol" / "index.json").write_text("{nope", encoding="utf-8")
        code, _, err = run_cli("--root", str(self.root))
        self.assertEqual(code, 2)
        self.assertIn("not valid JSON", err)

    def test_missing_index(self):
        code, _, err = run_cli("--root", str(self.root))
        self.assertEqual(code, 2)
        self.assertIn("index file not found", err)

    def test_find_cycle_acyclic(self):
        self.assertIsNone(bb.find_cycle({"a": ["b"], "b": [], "c": ["a", "b"]}))


if __name__ == "__main__":
    unittest.main()
