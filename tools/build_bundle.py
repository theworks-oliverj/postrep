#!/usr/bin/env python3
"""
build_bundle.py - build the single-file Virgil Protocol bundle.

Why this exists
---------------
The protocol lives in the repo as small modules (protocol/*.md) plus a thin
entry file (START_HERE.md), so an AI agent can fetch only what it needs.
Some chat products cannot fetch from GitHub, though. For those, the user pastes
or uploads ONE file. This script generates that file:

    dist/VIRGIL_PROTOCOL_FULL.md

The modules stay the single source of truth. The bundle is generated: never
edit it by hand. CI runs `--check` to make sure it is not stale.

What it reads
-------------
protocol/index.json, shaped like:

    {
      "protocol": "Virgil Protocol",
      "version": "1.0.0",
      "raw_base": "https://raw.githubusercontent.com/<owner>/<repo>/main/",
      "entry": "START_HERE.md",
      "modules": [
        {"id": "preamble", "path": "protocol/preamble.md", "title": "...",
         "purpose": "...", "phase": "all", "inputs": [], "outputs": [],
         "depends_on": [], "load_when": "...", "bundle": true}
      ]
    }

What it writes
--------------
1. A header: title, version, "generated - do not edit; source: protocol/".
2. A table of contents (entry first, then bundled modules in index order).
3. The entry file, then each module with `"bundle": true`, in index order,
   each introduced by a marker line:

       <!-- MODULE:<id> path=<path> -->

   and an HTML anchor `<a id="module-<id>"></a>` so links can target it.
4. Link rewriting. Relative links inside any bundled file are resolved against
   that file's location, then:
     - target is bundled        -> `#module-<id>` (any #fragment is dropped,
                                   because heading anchors are not unique once
                                   many files share one page);
     - target is anywhere else  -> an absolute URL under `raw_base` (or the
                                   GitHub "tree" URL for directories).
   Absolute URLs, mailto: links and pure `#fragment` links are left alone, as is
   anything inside fenced code blocks or inline code spans.

Validation (always run, exit code 2 on failure)
-----------------------------------------------
- index.json is valid JSON with the required keys;
- module ids are unique and URL-safe ([a-z0-9][a-z0-9_-]*);
- every path (and the entry) exists inside the repo;
- every depends_on id exists;
- there are no dependency cycles (the cycle is printed).
Warnings (not errors) are printed for links to files that do not exist and for
bundled modules that depend on modules that are not bundled.

Usage
-----
    python3 tools/build_bundle.py            # write dist/VIRGIL_PROTOCOL_FULL.md
    python3 tools/build_bundle.py --check    # CI: exit 1 if the file is stale
    python3 tools/build_bundle.py --root DIR # build for another repo layout

Exit codes: 0 ok, 1 bundle missing/stale (--check only), 2 invalid index/input.

Requires only the Python 3.10+ standard library.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import posixpath
import re
import sys
from pathlib import Path

DEFAULT_INDEX = "protocol/index.json"
DEFAULT_OUT = "dist/VIRGIL_PROTOCOL_FULL.md"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
ENTRY_ID = "entry"


class InvalidIndex(Exception):
    """Raised when index.json or the files it points to are invalid."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


# --------------------------------------------------------------------------- #
# Loading and validation
# --------------------------------------------------------------------------- #

def load_index(index_path: Path) -> dict:
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise InvalidIndex([f"index file not found: {index_path}"])
    except json.JSONDecodeError as exc:
        raise InvalidIndex([f"{index_path} is not valid JSON: {exc}"])
    return data


def _safe_repo_path(root: Path, rel: str) -> tuple[Path | None, str | None]:
    """Resolve a repo-relative POSIX path; return (path, error)."""
    if not isinstance(rel, str) or not rel:
        return None, "path must be a non-empty string"
    if rel.startswith("/") or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", rel):
        return None, f"path must be relative to the repo root, got {rel!r}"
    norm = posixpath.normpath(rel)
    if norm == ".." or norm.startswith("../"):
        return None, f"path escapes the repo root: {rel!r}"
    return root / norm, None


def find_cycle(graph: dict[str, list[str]]) -> list[str] | None:
    """Return one dependency cycle as [a, b, ..., a], or None."""
    WHITE, GREY, BLACK = 0, 1, 2
    colour = {node: WHITE for node in graph}
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        colour[node] = GREY
        stack.append(node)
        for dep in graph.get(node, []):
            if dep not in colour:
                continue  # unknown ids are reported separately
            if colour[dep] == GREY:
                return stack[stack.index(dep):] + [dep]
            if colour[dep] == WHITE:
                found = visit(dep)
                if found:
                    return found
        stack.pop()
        colour[node] = BLACK
        return None

    for node in graph:
        if colour[node] == WHITE:
            found = visit(node)
            if found:
                return found
    return None


def validate_index(index: dict, root: Path) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Errors make the build fail."""
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(index, dict):
        return ["index.json must contain a JSON object"], warnings

    for key in ("protocol", "version", "raw_base", "entry", "modules"):
        if key not in index:
            errors.append(f"index.json: missing required key {key!r}")
    if errors:
        return errors, warnings

    raw_base = index["raw_base"]
    if not isinstance(raw_base, str) or not raw_base.startswith(("http://", "https://")):
        errors.append("index.json: raw_base must be an http(s) URL")
    elif not raw_base.endswith("/"):
        errors.append("index.json: raw_base must end with '/'")

    entry_path, err = _safe_repo_path(root, index["entry"])
    if err:
        errors.append(f"entry: {err}")
    elif not entry_path.is_file():
        errors.append(f"entry: file does not exist: {index['entry']}")

    modules = index["modules"]
    if not isinstance(modules, list) or not modules:
        errors.append("index.json: 'modules' must be a non-empty list")
        return errors, warnings

    seen_ids: dict[str, int] = {}
    seen_paths: dict[str, str] = {}
    for pos, mod in enumerate(modules):
        label = f"modules[{pos}]"
        if not isinstance(mod, dict):
            errors.append(f"{label}: must be an object")
            continue
        mid = mod.get("id")
        if not isinstance(mid, str) or not ID_RE.match(mid):
            errors.append(f"{label}: id {mid!r} must match {ID_RE.pattern}")
            continue
        label = f"module {mid!r}"
        if mid == ENTRY_ID:
            errors.append(f"{label}: id 'entry' is reserved for the entry file")
        if mid in seen_ids:
            errors.append(f"{label}: duplicate id (also modules[{seen_ids[mid]}])")
        seen_ids[mid] = pos

        path, err = _safe_repo_path(root, mod.get("path"))
        if err:
            errors.append(f"{label}: {err}")
        else:
            if not path.is_file():
                errors.append(f"{label}: file does not exist: {mod['path']}")
            norm = posixpath.normpath(mod["path"])
            if norm in seen_paths:
                errors.append(f"{label}: path {norm!r} already used by module {seen_paths[norm]!r}")
            seen_paths[norm] = mid

        deps = mod.get("depends_on", [])
        if not isinstance(deps, list) or not all(isinstance(d, str) for d in deps):
            errors.append(f"{label}: depends_on must be a list of module ids")

    ids = set(seen_ids)
    for mod in modules:
        if not isinstance(mod, dict) or not isinstance(mod.get("id"), str):
            continue
        deps = mod.get("depends_on", [])
        if not isinstance(deps, list):
            continue
        for dep in deps:
            if dep not in ids:
                errors.append(f"module {mod['id']!r}: depends_on unknown module id {dep!r}")

    graph = {
        m["id"]: [d for d in m.get("depends_on", []) if isinstance(d, str)]
        for m in modules
        if isinstance(m, dict) and isinstance(m.get("id"), str) and isinstance(m.get("depends_on", []), list)
    }
    cycle = find_cycle(graph)
    if cycle:
        errors.append("dependency cycle: " + " -> ".join(cycle))

    by_id = {m["id"]: m for m in modules if isinstance(m, dict) and isinstance(m.get("id"), str)}
    for mid, mod in by_id.items():
        if mod.get("bundle") is True:
            for dep in graph.get(mid, []):
                if dep in by_id and by_id[dep].get("bundle") is not True:
                    warnings.append(f"module {mid!r} is bundled but depends on {dep!r}, which is not bundled")

    return errors, warnings


# --------------------------------------------------------------------------- #
# Link rewriting
# --------------------------------------------------------------------------- #

# [text](target "optional title")  and  ![alt](target)
INLINE_LINK_RE = re.compile(r"(\]\(\s*)(<[^>]*>|[^)\s]*)(\s+(?:\"[^\"]*\"|'[^']*'))?(\s*\))")
# [label]: target
REF_DEF_RE = re.compile(r"^(\s{0,3}\[[^\]]+\]:\s*)(<[^>]*>|\S+)(.*)$")
FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
CODE_SPAN_RE = re.compile(r"(`+)(?:(?!\1).)+?\1")
SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


class LinkRewriter:
    def __init__(self, root: Path, raw_base: str, bundled: dict[str, str]):
        """`bundled` maps normalised repo-relative path -> module id (or 'entry')."""
        self.root = root
        self.raw_base = raw_base
        self.bundled = bundled
        self.warnings: list[str] = []
        m = re.match(r"^https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/$", raw_base)
        self.tree_base = f"https://github.com/{m.group(1)}/{m.group(2)}/tree/{m.group(3)}/" if m else raw_base

    def rewrite_target(self, target: str, source_rel: str) -> str:
        """Return the new target for a link found in the file `source_rel`."""
        raw = target
        if raw.startswith("<") and raw.endswith(">"):
            raw = raw[1:-1]
        if not raw or raw.startswith("#") or raw.startswith("//") or SCHEME_RE.match(raw):
            return target

        path_part, _, fragment = raw.partition("#")
        path_part = path_part.split("?", 1)[0]
        if path_part.startswith("/"):
            resolved = posixpath.normpath(path_part.lstrip("/"))
        else:
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(source_rel), path_part))
        if resolved == ".." or resolved.startswith("../"):
            self.warnings.append(f"{source_rel}: link leaves the repo: {target}")
            return target
        if resolved == ".":
            resolved = ""

        if resolved in self.bundled:
            return f"#module-{self.bundled[resolved]}"

        fs_path = self.root / resolved
        if resolved and not fs_path.exists():
            self.warnings.append(f"{source_rel}: link to missing file: {target}")
        if fs_path.is_dir() or resolved == "":
            url = self.tree_base + (resolved.rstrip("/") + "/" if resolved else "")
        else:
            url = self.raw_base + resolved
        if fragment:
            url += "#" + fragment
        return url

    def rewrite_text(self, text: str, source_rel: str) -> str:
        out_lines: list[str] = []
        fence: str | None = None
        for line in text.split("\n"):
            m = FENCE_RE.match(line)
            if m:
                marker = m.group(1)
                if fence is None:
                    fence = marker[0] * 3
                elif marker[0] == fence[0] and len(marker) >= len(fence):
                    fence = None
                out_lines.append(line)
                continue
            if fence is not None:
                out_lines.append(line)
                continue
            out_lines.append(self._rewrite_line(line, source_rel))
        return "\n".join(out_lines)

    def _rewrite_line(self, line: str, source_rel: str) -> str:
        ref = REF_DEF_RE.match(line)
        if ref:
            return ref.group(1) + self.rewrite_target(ref.group(2), source_rel) + ref.group(3)

        # Split on inline code spans so links inside `code` are untouched.
        pieces: list[str] = []
        pos = 0
        for span in CODE_SPAN_RE.finditer(line):
            pieces.append(self._rewrite_inline(line[pos:span.start()], source_rel))
            pieces.append(span.group(0))
            pos = span.end()
        pieces.append(self._rewrite_inline(line[pos:], source_rel))
        return "".join(pieces)

    def _rewrite_inline(self, segment: str, source_rel: str) -> str:
        def sub(m: re.Match) -> str:
            new = self.rewrite_target(m.group(2), source_rel)
            return f"{m.group(1)}{new}{m.group(3) or ''}{m.group(4)}"

        return INLINE_LINK_RE.sub(sub, segment)


# --------------------------------------------------------------------------- #
# Bundle assembly
# --------------------------------------------------------------------------- #

def _read(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")


def _one_line(text: object) -> str:
    return " ".join(str(text).split())


def build(root: Path, index: dict) -> tuple[str, list[str]]:
    """Return (bundle_text, warnings). Assumes validate_index passed."""
    entry_rel = posixpath.normpath(index["entry"])
    bundled_mods = [m for m in index["modules"] if m.get("bundle") is True]

    bundled_map: dict[str, str] = {entry_rel: ENTRY_ID}
    for m in bundled_mods:
        bundled_map[posixpath.normpath(m["path"])] = m["id"]

    rewriter = LinkRewriter(root, index["raw_base"], bundled_map)

    title = f"{index['protocol']} - full bundle"
    out: list[str] = []
    out.append(f"# {title} (v{index['version']})")
    out.append("")
    out.append(
        "<!-- GENERATED FILE - DO NOT EDIT. "
        "Source: protocol/ (see protocol/index.json). "
        "Rebuild with: python3 tools/build_bundle.py -->"
    )
    out.append("")
    out.append(
        "> Generated file - do not edit. Source: `protocol/` and the entry file "
        f"`{index['entry']}`. This single file contains everything an AI chat needs "
        "when it cannot fetch files from GitHub. Start with the entry section, "
        "then load each module when its \"Load when\" condition applies. "
        "**AI: you are reading the full bundle. Do not fetch anything from GitHub; "
        "every module path below maps to its `module-<id>` section in this file.**"
    )
    out.append("")
    out.append("## Table of contents")
    out.append("")
    out.append(f"- [Entry: {index['entry']}](#module-{ENTRY_ID})")
    for m in bundled_mods:
        label = _one_line(m.get("title") or m["id"])
        line = f"- [{label}](#module-{m['id']}) (`{m['id']}`)"
        if m.get("purpose"):
            line += f": {_one_line(m['purpose'])}"
        out.append(line)
    out.append("")

    def add_section(mid: str, rel: str) -> None:
        body = rewriter.rewrite_text(_read(root / rel), rel)
        out.append("---")
        out.append("")
        out.append(f"<!-- MODULE:{mid} path={rel} -->")
        out.append(f'<a id="module-{mid}"></a>')
        out.append("")
        out.append(body)
        out.append("")

    add_section(ENTRY_ID, entry_rel)
    for m in bundled_mods:
        add_section(m["id"], posixpath.normpath(m["path"]))

    out.append("---")
    out.append("")
    out.append(f"<!-- END OF BUNDLE: {len(bundled_mods)} modules + entry -->")
    return "\n".join(out) + "\n", rewriter.warnings


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def run(argv: list[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="Build dist/VIRGIL_PROTOCOL_FULL.md from protocol/index.json.")
    ap.add_argument("--root", type=Path, default=default_root, help="repo root (default: parent of tools/)")
    ap.add_argument("--index", default=DEFAULT_INDEX, help=f"index path relative to root (default {DEFAULT_INDEX})")
    ap.add_argument("--out", default=DEFAULT_OUT, help=f"output path relative to root (default {DEFAULT_OUT})")
    ap.add_argument("--check", action="store_true", help="do not write; exit 1 if the bundle is missing or stale")
    args = ap.parse_args(argv)

    root: Path = args.root.resolve()
    out_path = root / args.out

    try:
        index = load_index(root / args.index)
        errors, warnings = validate_index(index, root)
        if errors:
            raise InvalidIndex(errors)
        text, link_warnings = build(root, index)
    except InvalidIndex as exc:
        print("build_bundle: invalid protocol index:", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2
    except (OSError, UnicodeDecodeError) as exc:
        print(f"build_bundle: cannot read input: {exc}", file=sys.stderr)
        return 2

    for w in warnings + link_warnings:
        print(f"warning: {w}", file=sys.stderr)

    if args.check:
        if not out_path.is_file():
            print(f"build_bundle --check: {args.out} does not exist; run: python3 tools/build_bundle.py", file=sys.stderr)
            return 1
        existing = out_path.read_text(encoding="utf-8")
        if existing != text:
            print(f"build_bundle --check: {args.out} is stale; run: python3 tools/build_bundle.py", file=sys.stderr)
            diff = difflib.unified_diff(
                existing.splitlines(), text.splitlines(), "existing", "fresh build", lineterm="", n=1
            )
            for i, line in enumerate(diff):
                if i >= 40:
                    print("  ... (diff truncated)", file=sys.stderr)
                    break
                print("  " + line, file=sys.stderr)
            return 1
        print(f"{args.out} is up to date.")
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(out_path.name + ".tmp")  # dist/*.tmp is git-ignored
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, out_path)
    print(f"Wrote {args.out} ({len(text.encode('utf-8')) // 1024} KiB, "
          f"{sum(1 for m in index['modules'] if m.get('bundle') is True)} modules + entry).")
    return 0


if __name__ == "__main__":
    sys.exit(run())
