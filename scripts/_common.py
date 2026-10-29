"""
_common.py - shared helpers for the virgil-protocol scripts.

PURPOSE
    Everything that more than one script needs lives here so the CLIs stay short:
      * the run-directory layout (one place to change a path),
      * JSON schema validation (uses the `jsonschema` package if it is installed,
        otherwise a small built-in validator that covers the keywords our schemas use),
      * crash-safe file writing (temp file + fsync + os.replace, with a .bak copy),
      * a tiny cross-platform file lock (so parallel agents can update run_state.json),
      * scoring helpers (state vector totals, '?' handling) and name normalisation.

NOT A CLI. Import only:   from _common import ...
    (Each script adds its own folder to sys.path first, so this works no matter
     which directory you launch it from.)

DESIGN RULES (why the code looks the way it does)
    * Standard library only, Python 3.10+. Non-experts must be able to run it anywhere.
    * Validation never "fixes" data silently. It reports; the caller decides.
    * Setting the environment variable VIRGIL_BUILTIN_VALIDATOR=1 forces the built-in
      validator even when `jsonschema` is installed. The test-suite uses this to prove
      both code paths agree.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import json
import os
import re
import shutil
import sys
import tempfile
import time
import unicodedata
from pathlib import Path
from typing import Any, Iterable, NamedTuple
from urllib.parse import urljoin, urlparse

# --------------------------------------------------------------------------- constants

PROTOCOL_VERSION = "1.0.0"      # semantic version of the protocol text; stamped into run_state and merged.json
RUBRIC_VERSION = "1.0"          # version of the 0-3 state-vector rubric AND the gate rubrics (shown as LP-1.0 / PM-1.0)
SCHEMA_BASE = "https://virgil-protocol.example/schemas/"
REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = REPO_ROOT / "schemas"

# The three scored axes of a state vector. WHY these names: they mirror the protocol
# (protocol/sessions/s3_scope_brief.md). The third axis is deliberately NOT "research": it
# covers every kind of pathway (supervisors, industry partners, placements, professional bodies).
AXES = ("funding", "programme", "pathway")

# Phases of a run, in order (run_state.current_phase and state_vector.phase use the same words).
PHASES = ["init", "life_plan", "map", "scope", "search", "followups", "merge", "verify", "deliverables", "done"]

# The two quality gates that must pass before any search ("no gate, no search", rule R3):
# rubric name -> (PATHS key of its score sheet, short label used in the "Where we are" brief).
GATES = {"life_plan": ("life_plan_score", "Life Plan"), "pathway_map": ("map_score", "Map")}

# Exit codes shared by every script (documented in each script's docstring).
EXIT_OK = 0
EXIT_PROBLEMS = 1     # the script ran, but found validation errors / failed a rule
EXIT_USAGE = 2        # bad arguments, missing file, unreadable JSON

# Every file the protocol knows about, keyed by a short name. Relative to RUN_DIR.
PATHS = {
    "run_state": "run_state.json",
    "orientation_notes": "00_orientation/notes.md",
    "interview_notes": "01_life_plan/interview_notes.md",
    "life_plan_md": "01_life_plan/life_plan.md",
    "life_plan": "01_life_plan/life_plan.json",
    "life_plan_score": "01_life_plan/life_plan_score.json",
    "map_interview_notes": "02_map/interview_notes.md",
    "pathway_map_md": "02_map/pathway_map.md",
    "study_pathway_map": "02_map/study_pathway_map.json",
    "map_score": "02_map/map_score.json",
    "benchmarks": "02_map/benchmarks.json",
    "search_plan": "03_scope/search_plan.json",
    "agent_brief": "03_scope/AGENT_BRIEF.md",
    "countries_dir": "04_search/countries",
    "followups_dir": "04_search/followups",
    "crosscuts_dir": "04_search/crosscuts",
    "overrides": "04_search/overrides.json",
    "orchestrator_notes": "04_search/orchestrator_notes.md",
    "followup_plan": "04_search/followup_plan.json",
    "rejected": "04_search/rejected_records.jsonl",
    "merged": "05_merge/merged.json",
    "merge_report": "05_merge/merge_report.json",
    "verification_sample": "06_verify/verification_sample.json",
    "verification": "06_verify/verification.json",
    "rundown_tables": "07_deliverables/rundown_tables.md",
    "options_rundown": "07_deliverables/options_rundown.md",
    "due_diligence": "07_deliverables/due_diligence.md",
    "session_log": "logs/session_log.jsonl",
}

LAYOUT_DIRS = ["00_orientation", "01_life_plan", "02_map", "03_scope", "04_search/countries",
               "04_search/followups", "04_search/crosscuts", "05_merge", "06_verify",
               "07_deliverables", "logs"]


def rp(run_dir: str | Path, key: str) -> Path:
    """Resolve a PATHS key to an absolute path inside RUN_DIR."""
    return Path(run_dir) / PATHS[key]


# --------------------------------------------------------------------------- time

def now_iso() -> str:
    """UTC timestamp, second precision, e.g. 2026-10-27T14:03:11Z."""
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today_iso() -> str:
    return dt.date.today().isoformat()


def parse_date(s: Any) -> dt.date | None:
    """Parse YYYY-MM-DD (or the date part of a timestamp). None if unparseable."""
    if not isinstance(s, str):
        return None
    try:
        return dt.date.fromisoformat(s[:10])
    except ValueError:
        return None


# --------------------------------------------------------------------------- JSON I/O

class UsageError(Exception):
    """Raised for problems the caller should see as exit code 2 (not a stack trace)."""


def load_json(path: str | Path) -> Any:
    p = Path(path)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise UsageError(f"file not found: {p}")
    except json.JSONDecodeError as e:
        raise UsageError(f"invalid JSON in {p}: {e}")


def dumps(obj: Any) -> str:
    # ensure_ascii=False keeps accents readable (Universite de Lausanne etc.).
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def atomic_write_text(path: str | Path, text: str, keep_backup: bool = True) -> None:
    """Crash-safe write.

    WHY: agents are cut off by usage limits at arbitrary moments. If we wrote the
    final file directly, a cut during the write would leave half a JSON file and lose
    the whole country. Instead we write a temp file in the SAME directory, fsync it,
    and os.replace() it over the target - on POSIX and Windows this swap is atomic.
    The previous version is copied to <name>.bak first so one bad write is reversible.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if keep_backup and path.exists():
            shutil.copy2(path, path.with_name(path.name + ".bak"))
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise
    # Best effort: persist the directory entry too (not supported on Windows).
    with contextlib.suppress(Exception):
        dfd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)


def atomic_write_json(path: str | Path, obj: Any, keep_backup: bool = True) -> None:
    atomic_write_text(path, dumps(obj), keep_backup=keep_backup)


def append_jsonl(path: str | Path, obj: Any) -> None:
    """Append one JSON line (used for logs). Single write() call + fsync so lines never interleave."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


@contextlib.contextmanager
def file_lock(path: str | Path, timeout: float = 30.0, stale_after: float = 60.0):
    """Advisory lock using an exclusive-create lock file (works on every OS).

    WHY: several agents run in parallel and all update the shared run_state.json.
    Without a lock two read-modify-write cycles can overlap and one update is lost.
    A lock older than `stale_after` seconds is assumed to belong to a crashed agent
    and is removed.
    """
    lock = Path(str(path) + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + timeout
    while True:
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > stale_after:
                    lock.unlink()
                    continue
            except FileNotFoundError:
                continue
            if time.time() > deadline:
                raise UsageError(f"could not obtain lock {lock} within {timeout}s")
            time.sleep(0.05)
    try:
        yield
    finally:
        with contextlib.suppress(FileNotFoundError):
            lock.unlink()


def read_json_arg(json_str: str | None, file_path: str | None) -> Any:
    """Accept a record as --json STRING, --file PATH ('-' = stdin) or piped stdin."""
    if json_str is not None:
        text = json_str
    elif file_path is not None:
        text = sys.stdin.read() if file_path == "-" else Path(file_path).read_text(encoding="utf-8")
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        raise UsageError("no record supplied: use --json '{...}', --file PATH, or pipe JSON on stdin")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise UsageError(f"record is not valid JSON: {e}")


# --------------------------------------------------------------------------- text / scoring helpers

def norm_text(s: Any) -> str:
    """Lower-case, strip accents and punctuation. Used for every duplicate check."""
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def record_key(rec: dict, with_track: bool = True) -> str:
    """Exact-dedupe key: institution | programme [| track], all normalised."""
    parts = [norm_text(rec.get("institution")), norm_text(rec.get("programme"))]
    if with_track:
        parts.append(norm_text(rec.get("track")))
    return " | ".join(parts)


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", norm_text(s)).strip("_")


def score_int(v: Any) -> int | None:
    """0-3 integer or None. The string '?' means 'insufficient evidence' = missing, not zero."""
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def vector_total(sv: dict | None) -> int | None:
    """Unweighted sum of the scored axes; '?' axes are skipped (None if all are '?').

    CAVEAT (reported in due_diligence.md): skipping '?' lowers the sum of unscored
    records, i.e. it biases against them. That is why `_unscored_axes` is stored too.
    """
    sv = sv or {}
    nums = [score_int(sv.get(a)) for a in AXES]
    if all(n is None for n in nums):
        return None
    return sum(n for n in nums if n is not None)


def unscored_axes(sv: dict | None) -> int:
    sv = sv or {}
    return sum(score_int(sv.get(a)) is None for a in AXES)


def rank_sort_key(rec: dict):
    """Sort key: total desc, then pathway desc, then funding desc, then id (stable).
    (Order from protocol/sessions/s8_merge_verify.md: "rank (total, then pathway, then funding)".)

    '?' sorts below 0 so unscored axes never win a tie-break by accident.
    """
    sv = rec.get("state_vector") or {}
    total = vector_total(sv)
    w, f = score_int(sv.get("pathway")), score_int(sv.get("funding"))
    return (-(total if total is not None else -1), -(w if w is not None else -1),
            -(f if f is not None else -1), str(rec.get("id")))


# --------------------------------------------------------------------------- plan / gate helpers

# Default cap_n (full records per country) when search_plan.countries[].cap_n is absent.
# Only depth 'quick' has a protocol-defined default; for other depths cap_n should be stated.
DEFAULT_CAP_N = {"quick": 4}


def cap_n_of(country: dict) -> int | None:
    """cap_n of a search_plan country entry, falling back to DEFAULT_CAP_N[depth] (None if unknown)."""
    return country.get("cap_n") or DEFAULT_CAP_N.get(country.get("depth"))


def exclusion_text(x: Any) -> str:
    """search_plan.exclusions entries may be plain strings or {country, reason} objects."""
    if isinstance(x, dict):
        return f"{x.get('country', '?')}: {x.get('reason', '')}".strip().rstrip(":")
    return str(x)


def is_url(v: Any) -> bool:
    """True only for http(s) URLs. Descriptive text such as 'official' is NOT a URL."""
    return isinstance(v, str) and v.strip().lower().startswith(("http://", "https://"))


def gate_state(run_dir: str | Path, rubric: str) -> str:
    """'pass' | 'fail' | 'pending' for the life_plan / pathway_map gate.

    pending = the score sheet is missing or was never evaluated by rubric.py (a freshly
    initialised sheet has no `problems` key); fail = evaluated and not passed; pass = passed.
    """
    p = rp(run_dir, GATES[rubric][0])
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "pending"
    if d.get("passed") is True:
        return "pass"
    return "fail" if "problems" in d else "pending"


def get_path(obj: Any, dotted: str) -> Any:
    """Read 'a.b.0.c' from nested dict/list. Raises KeyError/IndexError if absent."""
    cur = obj
    for part in dotted.split("."):
        cur = cur[int(part)] if isinstance(cur, list) else cur[part]
    return cur


def set_path(obj: Any, dotted: str, value: Any) -> Any:
    """Set 'a.b.0.c' creating missing dict keys. Returns the previous value (or None)."""
    parts = dotted.split(".")
    cur = obj
    for part in parts[:-1]:
        if isinstance(cur, list):
            cur = cur[int(part)]
        else:
            cur = cur.setdefault(part, {})
    last = parts[-1]
    if isinstance(cur, list):
        old = cur[int(last)]
        cur[int(last)] = value
    else:
        old = cur.get(last)
        cur[last] = value
    return old


# --------------------------------------------------------------------------- file discovery

FOLLOWUP_RE = r"^{slug}_followup(?:_[A-Za-z0-9]+)*\.json$"


def list_json(directory: Path) -> list[Path]:
    return sorted(p for p in directory.glob("*.json")) if directory.is_dir() else []


def followups_for(run_dir: str | Path, slug: str) -> list[Path]:
    rx = re.compile(FOLLOWUP_RE.format(slug=re.escape(slug)))
    return [p for p in list_json(rp(run_dir, "followups_dir")) if rx.match(p.name)]


# --------------------------------------------------------------------------- schema validation

class VError(NamedTuple):
    path: str       # e.g. candidates[2].state_vector.funding  ('' = document root)
    kind: str       # JSON-Schema keyword that failed: required, enum, type, pattern, ...
    message: str
    value: Any = None


_SCHEMA_CACHE: dict[str, dict] = {}


def load_schemas() -> dict[str, dict]:
    """Load every schemas/*.schema.json once; keyed by file stem ('candidate_record')."""
    if not _SCHEMA_CACHE:
        for p in sorted(SCHEMAS_DIR.glob("*.schema.json")):
            _SCHEMA_CACHE[p.name[: -len(".schema.json")]] = json.loads(p.read_text(encoding="utf-8"))
    return _SCHEMA_CACHE


def fmt_path(parts: Iterable[Any]) -> str:
    out = ""
    for p in parts:
        out += f"[{p}]" if isinstance(p, int) else (("." if out else "") + str(p))
    return out


def _type_ok(inst: Any, t: str) -> bool:
    if t == "object":
        return isinstance(inst, dict)
    if t == "array":
        return isinstance(inst, list)
    if t == "string":
        return isinstance(inst, str)
    if t == "boolean":
        return isinstance(inst, bool)
    if t == "null":
        return inst is None
    if t == "integer":
        return (isinstance(inst, int) and not isinstance(inst, bool)) or (isinstance(inst, float) and inst.is_integer())
    if t == "number":
        return isinstance(inst, (int, float)) and not isinstance(inst, bool)
    return False


def _json_eq(a: Any, b: Any) -> bool:
    """Equality where True != 1 (Python's == would say they are equal)."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    return a == b


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?([Zz]|[+-]\d{2}:\d{2})?$")


class _MiniValidator:
    """Minimal JSON-Schema (2020-12 subset) validator.

    Supports: type, enum, const, pattern, minimum, maximum, minLength, minItems,
    maxItems, minProperties, uniqueItems, items, properties, patternProperties,
    additionalProperties, required, allOf, anyOf, oneOf, $ref (+ $defs fragments)
    and format date / date-time. That is every keyword our schemas use.
    """

    def __init__(self, schemas: dict[str, dict]):
        # Index by $id so relative $refs ("state_vector.schema.json") resolve.
        self.store = {s["$id"]: s for s in schemas.values() if "$id" in s}

    def resolve(self, ref: str, base: str):
        url, _, frag = urljoin(base, ref).partition("#")
        doc = self.store.get(url)
        if doc is None:
            raise KeyError(f"unresolvable $ref {ref!r} (base {base})")
        node: Any = doc
        for part in [p for p in frag.split("/") if p]:
            node = node[part.replace("~1", "/").replace("~0", "~")]
        return node, url

    def check(self, inst: Any, schema: dict, base: str) -> list[VError]:
        out: list[VError] = []
        self._walk(inst, schema, base, [], out)
        return out

    def _walk(self, inst, schema, base, path, out):
        if schema is True or schema == {}:
            return
        if "$id" in schema:
            base = schema["$id"]
        if "$ref" in schema:
            target, nbase = self.resolve(schema["$ref"], base)
            self._walk(inst, target, nbase, path, out)
        err = lambda kind, msg: out.append(VError(fmt_path(path), kind, msg, inst if not isinstance(inst, (dict, list)) else None))

        t = schema.get("type")
        if t is not None:
            types = t if isinstance(t, list) else [t]
            if not any(_type_ok(inst, x) for x in types):
                err("type", f"expected {'/'.join(types)}, got {type(inst).__name__}")
                return
        if "const" in schema and not _json_eq(inst, schema["const"]):
            err("const", f"must equal {schema['const']!r}")
        if "enum" in schema and not any(_json_eq(inst, e) for e in schema["enum"]):
            err("enum", f"{inst!r} is not one of {schema['enum']}")
        for sub in schema.get("allOf", []):
            self._walk(inst, sub, base, path, out)
        if "anyOf" in schema:
            if not any(not self._sub(inst, s, base, path) for s in schema["anyOf"]):
                err("anyOf", f"{inst!r} does not match any allowed form")
        if "oneOf" in schema:
            n = sum(1 for s in schema["oneOf"] if not self._sub(inst, s, base, path))
            if n != 1:
                err("oneOf", f"{inst!r} must match exactly one allowed form (matched {n})")

        if isinstance(inst, str):
            if "pattern" in schema and not re.search(schema["pattern"], inst):
                err("pattern", f"{inst!r} does not match /{schema['pattern']}/")
            if "minLength" in schema and len(inst) < schema["minLength"]:
                err("minLength", f"shorter than {schema['minLength']}")
            fmt = schema.get("format")
            if fmt == "date" and not (_DATE_RE.match(inst) and _valid_date(inst)):
                err("format", f"{inst!r} is not a YYYY-MM-DD date")
            if fmt == "date-time" and not _DATETIME_RE.match(inst):
                err("format", f"{inst!r} is not an ISO date-time")
        if _type_ok(inst, "number") and not isinstance(inst, bool):
            if "minimum" in schema and inst < schema["minimum"]:
                err("minimum", f"{inst} < {schema['minimum']}")
            if "maximum" in schema and inst > schema["maximum"]:
                err("maximum", f"{inst} > {schema['maximum']}")
        if isinstance(inst, list):
            if "minItems" in schema and len(inst) < schema["minItems"]:
                err("minItems", f"needs at least {schema['minItems']} items, has {len(inst)}")
            if "maxItems" in schema and len(inst) > schema["maxItems"]:
                err("maxItems", f"allows at most {schema['maxItems']} items, has {len(inst)}")
            if schema.get("uniqueItems"):
                seen = [json.dumps(x, sort_keys=True) for x in inst]
                if len(set(seen)) != len(seen):
                    err("uniqueItems", "items must be unique")
            if "items" in schema:
                for i, item in enumerate(inst):
                    self._walk(item, schema["items"], base, path + [i], out)
        if isinstance(inst, dict):
            for req in schema.get("required", []):
                if req not in inst:
                    out.append(VError(fmt_path(path), "required", f"missing required field '{req}'", req))
            if "minProperties" in schema and len(inst) < schema["minProperties"]:
                err("minProperties", f"needs at least {schema['minProperties']} properties")
            props = schema.get("properties", {})
            pats = schema.get("patternProperties", {})
            extra = []
            for k, v in inst.items():
                matched = False
                if k in props:
                    matched = True
                    self._walk(v, props[k], base, path + [k], out)
                for pat, sub in pats.items():
                    if re.search(pat, k):
                        matched = True
                        self._walk(v, sub, base, path + [k], out)
                if not matched:
                    extra.append(k)
            ap = schema.get("additionalProperties", True)
            if extra and ap is False:
                out.append(VError(fmt_path(path), "additionalProperties", f"unexpected field(s): {', '.join(sorted(extra))}", extra))
            elif extra and isinstance(ap, dict):
                for k in extra:
                    self._walk(inst[k], ap, base, path + [k], out)

    def _sub(self, inst, schema, base, path):
        tmp: list[VError] = []
        self._walk(inst, schema, base, path, tmp)
        return tmp


def _valid_date(s: str) -> bool:
    try:
        dt.date.fromisoformat(s)
        return True
    except ValueError:
        return False


_LIB = None  # cached (jsonschema, registry) or False


def _jsonschema_lib():
    """Return (jsonschema module, referencing registry) or None if unavailable/disabled."""
    global _LIB
    if os.environ.get("VIRGIL_BUILTIN_VALIDATOR"):
        return None
    if _LIB is None:
        try:
            import jsonschema  # type: ignore
            from referencing import Registry, Resource  # type: ignore
            from referencing.jsonschema import DRAFT202012  # type: ignore
            res = [(s["$id"], Resource.from_contents(s, default_specification=DRAFT202012))
                   for s in load_schemas().values() if "$id" in s]
            _LIB = (jsonschema, Registry().with_resources(res))
        except Exception:        # ImportError or an old jsonschema without `referencing`
            _LIB = False
    return _LIB or None


def validator_name() -> str:
    return "jsonschema" if _jsonschema_lib() else "built-in"


def validate(instance: Any, schema_name: str) -> list[VError]:
    """Validate `instance` against schemas/<schema_name>.schema.json. Empty list = valid."""
    schemas = load_schemas()
    if schema_name not in schemas:
        raise UsageError(f"unknown schema {schema_name!r}; available: {', '.join(sorted(schemas))}")
    schema = schemas[schema_name]
    lib = _jsonschema_lib()
    if lib:
        jsonschema, registry = lib
        v = jsonschema.Draft202012Validator(schema, registry=registry,
                                            format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER)
        errs = [VError(fmt_path(e.absolute_path), e.validator, e.message,
                       e.instance if not isinstance(e.instance, (dict, list)) else None)
                for e in v.iter_errors(instance)]
    else:
        errs = _MiniValidator(schemas).check(instance, schema, schema.get("$id", ""))
    return sorted(errs, key=lambda e: (e.path, e.kind, e.message))


# Fields we REQUIRE when an agent writes a candidate through checkpoint.py but which the
# schema only recommends (so older / converted data still validates). See candidate_record
# schema description of `sources`.
def write_time_problems(candidate: dict) -> list[VError]:
    out = []
    for i, s in enumerate(candidate.get("sources") or []):
        for f in ("source_type", "accessed_date"):
            if f not in s:
                out.append(VError(f"sources[{i}]", "required", f"missing '{f}' (mandatory when writing new records)", f))
    return out
