"""ST Analyzer — regex-based Structured Text analysis with B&R naming heuristics.

Strategy: targeted regex + B&R prefix heuristics. No full grammar parser.
Covers ~85–90% of cases — sufficient for documentation.

B&R naming conventions used as deterministic heuristics:
  g…        → Global variable (cross-check against GVL list)
  di… / si… → Digital/Safety Input — always READ, never WRITE target
  do…       → Digital Output — WRITE target in owning POU
  ai… / ao… / at… → Analog I/O
  p…        → Pointer (handle p^.Field dereference)
  SCREAMING_SNAKE_CASE → Constant — never on left side of :=
  *Type suffix → User-defined type reference, not a value
  *Enum type  → Enum literal on right side — READ of literal
  <FBType>_<suffix> → FB instance
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field

from as_docs.model.graph import Edge, Variable
from as_docs.model.project import RawSTFile

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_]*"

# FB call: Identifier( — not preceded by a keyword
_CALL_RE = re.compile(rf"(?<!\w)({_IDENTIFIER})\s*\(")
# Assignment left side
_WRITE_RE = re.compile(rf"(?<!\w)({_IDENTIFIER}(?:\.{_IDENTIFIER}|\^\.{_IDENTIFIER})?)\s*:=")
# Read: identifiers on right side or in conditions (post-filter)
_READ_RE = re.compile(rf"(?<!\w)({_IDENTIFIER})\b")
# Instance.Field input binding before FB call (assign-then-call)
_INSTANCE_BINDING_RE = re.compile(
    rf"^\s*({_IDENTIFIER})\.({_IDENTIFIER})\s*:=",
    re.MULTILINE,
)
# Section markers in .st files
_SECTION_RE = re.compile(
    r"(?:^|\n)\s*((?:\w+\s+)?(?:_INIT|_CYCLIC|_EXIT|PROGRAM|FUNCTION_BLOCK|FUNCTION)\b.*?)\s*(?=\n)",
    re.IGNORECASE,
)
# CASE / IF / FOR / WHILE for flow hints (used by call_graph)
_CASE_RE = re.compile(r"\bCASE\b", re.IGNORECASE)
_IF_RE = re.compile(r"\bIF\b", re.IGNORECASE)
_FOR_RE = re.compile(r"\bFOR\b", re.IGNORECASE)
_WHILE_RE = re.compile(r"\bWHILE\b", re.IGNORECASE)

# Keywords to exclude from variable/call detection
_ST_KEYWORDS = frozenset(
    w.upper() for w in (
        "IF", "THEN", "ELSE", "ELSIF", "END_IF", "CASE", "OF", "END_CASE",
        "FOR", "TO", "BY", "DO", "END_FOR", "WHILE", "END_WHILE", "REPEAT",
        "UNTIL", "END_REPEAT", "RETURN", "EXIT", "CONTINUE", "NOT", "AND",
        "OR", "XOR", "MOD", "TRUE", "FALSE", "VAR", "END_VAR", "VAR_INPUT",
        "VAR_OUTPUT", "VAR_IN_OUT", "PROGRAM", "FUNCTION_BLOCK", "FUNCTION",
        "END_PROGRAM", "END_FUNCTION_BLOCK", "END_FUNCTION", "STRUCT",
        "END_STRUCT", "TYPE", "END_TYPE", "ARRAY", "OF", "AT", "RETAIN",
    )
)

_SCREAMING_SNAKE = re.compile(r"^[A-Z][A-Z0-9_]*[_][A-Z0-9_]+$")
_TYPE_SUFFIX = re.compile(r"Type$")
_IO_READ_PREFIXES = ("di", "si", "ai", "at")


@dataclass
class STAnalysisResult:
    pou_name: str
    calls: list[str] = field(default_factory=list)          # POU names called
    writes: list[str] = field(default_factory=list)         # variable names written
    reads: list[str] = field(default_factory=list)          # variable names read
    instances: list[str] = field(default_factory=list)      # FB instance names
    # Flow hints for Level 4
    has_case: bool = False
    has_if: bool = False
    has_for: bool = False
    has_while: bool = False


def analyze_st(
    st_file: RawSTFile,
    known_pous: set[str],
    known_vars: set[str],
    external_prefixes: list[str] | None = None,
) -> STAnalysisResult:
    """Analyze a single .st file and return calls, reads, writes."""
    result = STAnalysisResult(pou_name=st_file.pou_name)
    source = _strip_comments(st_file.source)

    ext_prefixes = tuple(external_prefixes or [])

    # Detect flow structures
    result.has_case = bool(_CASE_RE.search(source))
    result.has_if = bool(_IF_RE.search(source))
    result.has_for = bool(_FOR_RE.search(source))
    result.has_while = bool(_WHILE_RE.search(source))

    # Find FB instances from VAR blocks in the source itself
    fb_instances = _extract_fb_instances(source)
    result.instances = list(fb_instances.keys())

    # Build set of instance names to avoid emitting them as calls/reads/writes
    instance_names = set(fb_instances.keys())

    # Identify assign-then-call groups (input bindings → don't emit as standalone writes)
    binding_prefixes = _find_binding_prefixes(source, instance_names)

    calls_found: set[str] = set()
    writes_found: set[str] = set()
    reads_found: set[str] = set()

    for line in source.splitlines():
        line_stripped = line.strip()
        if not line_stripped or line_stripped.startswith("//"):
            continue

        # Detect writes (left side of :=)
        for m in _WRITE_RE.finditer(line):
            raw = m.group(1)
            base = raw.split(".")[0].split("^")[0]

            # Skip if this is an input binding for an FB call
            if base in binding_prefixes:
                continue

            # Skip SCREAMING_SNAKE constants
            if _SCREAMING_SNAKE.match(base):
                continue

            # Skip I/O read-only prefixes
            if base.lower().startswith(_IO_READ_PREFIXES):
                continue

            # Skip type references
            if _TYPE_SUFFIX.search(base):
                continue

            target = base if "." not in raw else raw
            writes_found.add(target)

        # Detect calls (identifier followed by opening paren)
        for m in _CALL_RE.finditer(line):
            name = m.group(1)
            if name.upper() in _ST_KEYWORDS:
                continue
            if name.lower() in ("if", "for", "while", "case", "not"):
                continue
            if name in known_pous and name != st_file.pou_name:
                calls_found.add(name)
            elif name in instance_names:
                # FB instance call → CALLS edge to its type
                fb_type = fb_instances.get(name)
                if fb_type and fb_type in known_pous:
                    calls_found.add(fb_type)

        # Detect reads (identifiers on right side of :=, in conditions, etc.)
        # Simplified: collect all identifiers not on left side of :=
        # and filter to known vars + global vars
        write_targets = {m.group(1).split(".")[0] for m in _WRITE_RE.finditer(line)}
        for m in _READ_RE.finditer(line):
            name = m.group(1)
            if name.upper() in _ST_KEYWORDS:
                continue
            if name in write_targets or name in instance_names:
                continue
            if _SCREAMING_SNAKE.match(name):
                continue
            if name in known_vars:
                reads_found.add(name)

    result.calls = sorted(calls_found)
    result.writes = sorted(writes_found & (known_vars | _global_names(writes_found)))
    result.reads = sorted(reads_found - calls_found - instance_names)
    return result


def _strip_comments(source: str) -> str:
    """Remove (* ... *) block comments and // line comments."""
    # Block comments (non-nested)
    source = re.sub(r"\(\*.*?\*\)", " ", source, flags=re.DOTALL)
    # Line comments
    source = re.sub(r"//[^\n]*", " ", source)
    return source


def _extract_fb_instances(source: str) -> dict[str, str]:
    """Find FB instance declarations: instance_name : FBType in VAR block.

    Returns dict mapping instance_name → FBType.
    """
    instances: dict[str, str] = {}
    in_var_block = False
    for line in source.splitlines():
        line_upper = line.strip().upper()
        if line_upper.startswith("VAR"):
            in_var_block = True
            continue
        if line_upper.startswith("END_VAR"):
            in_var_block = False
            continue
        if in_var_block:
            m = re.match(rf"^\s*({_IDENTIFIER})\s*:\s*({_IDENTIFIER})\s*;", line)
            if m:
                inst_name, type_name = m.group(1), m.group(2)
                # Heuristic: FB instances follow <FBType>_<suffix> convention
                # or the type contains letters that suggest it's a FB, not a primitive
                if not _is_primitive_type(type_name):
                    instances[inst_name] = type_name
    return instances


def _find_binding_prefixes(source: str, instance_names: set[str]) -> set[str]:
    """Find instance names used in assign-then-call input binding patterns."""
    return {m.group(1) for m in _INSTANCE_BINDING_RE.finditer(source) if m.group(1) in instance_names}


def _is_primitive_type(name: str) -> bool:
    primitives = frozenset(
        "BOOL INT UINT SINT USINT DINT UDINT LINT ULINT REAL LREAL "
        "BYTE WORD DWORD LWORD STRING WSTRING TIME DATE DT TOD".split()
    )
    return name.upper() in primitives


def _global_names(names: set[str]) -> set[str]:
    """Return names that look like global variables (g-prefix)."""
    return {n for n in names if n.startswith("g") and len(n) > 1 and n[1].isupper()}
