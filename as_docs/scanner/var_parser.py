"""Parser for .var files — extracts variable declarations."""

from __future__ import annotations
import re
from pathlib import Path

from as_docs.model.graph import Variable

# .var file structure (simplified):
#
# (* GVL_Drive *)
# VAR_GLOBAL
#     gMotorSpeed : REAL := 0.0;  (* Actual motor speed [rpm] *)
#     gFault      : BOOL;
# END_VAR
#
# Local .var files do not have the GVL header and use VAR / VAR_INPUT etc.

_BLOCK_RE = re.compile(
    r"(VAR_GLOBAL|VAR_INPUT|VAR_OUTPUT|VAR_IN_OUT|VAR)\b(.*?)END_VAR",
    re.IGNORECASE | re.DOTALL,
)
_VAR_LINE_RE = re.compile(
    r"^\s*(\w+)\s*:\s*([^;:=]+?)(?::=\s*([^;]+?))?\s*;(.*)$",
)
_COMMENT_RE = re.compile(r"\(\*\s*(.*?)\s*\)\s*$", re.DOTALL)
_UNIT_RE = re.compile(r"\[([^\]]+)\]")
_GVL_HEADER_RE = re.compile(r"\(\*\s*(\w+)\s*\*\)", re.MULTILINE)


def parse_var_file(path: Path) -> tuple[list[Variable], str | None]:
    """Parse a .var file.

    Returns:
        (variables, gvl_name) — gvl_name is None for local VAR files.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [], None

    # Detect GVL name from leading comment (* GVL_Drive *)
    gvl_name: str | None = None
    header_match = _GVL_HEADER_RE.search(text[:500])
    if header_match:
        candidate = header_match.group(1)
        # Only treat as GVL name if it looks like one (not a generic comment)
        if not candidate.lower().startswith(("local", "global", "var")):
            gvl_name = candidate

    # Also infer gvl_name from filename for GVL files
    stem = path.stem
    if gvl_name is None and stem.upper().startswith("GVL"):
        gvl_name = stem

    variables: list[Variable] = []

    for block_match in _BLOCK_RE.finditer(text):
        block_keyword = block_match.group(1).upper()
        block_body = block_match.group(2)
        var_class = _keyword_to_class(block_keyword)
        scope = "GLOBAL" if block_keyword == "VAR_GLOBAL" else "LOCAL"

        for line in block_body.splitlines():
            var = _parse_var_line(line, scope, gvl_name, var_class)
            if var:
                variables.append(var)

    return variables, gvl_name


def _keyword_to_class(keyword: str) -> str:
    mapping = {
        "VAR_GLOBAL": "VAR",
        "VAR_INPUT": "VAR_INPUT",
        "VAR_OUTPUT": "VAR_OUTPUT",
        "VAR_IN_OUT": "VAR_IN_OUT",
        "VAR": "VAR",
    }
    return mapping.get(keyword, "VAR")


def _parse_var_line(
    line: str,
    scope: str,
    gvl_name: str | None,
    var_class: str,
) -> Variable | None:
    # Strip inline comment for parsing, but keep it for description
    # Inline comment may span after the semicolon: name : TYPE := val; (* desc *)
    m = _VAR_LINE_RE.match(line)
    if not m:
        return None

    name = m.group(1).strip()
    var_type = m.group(2).strip()
    initial_value = m.group(3).strip() if m.group(3) else None
    trailing = m.group(4).strip()

    # Skip keywords accidentally matched
    if name.upper() in (
        "END_VAR",
        "VAR",
        "VAR_GLOBAL",
        "VAR_INPUT",
        "VAR_OUTPUT",
        "VAR_IN_OUT",
    ):
        return None

    description = ""
    unit: str | None = None

    comment_match = _COMMENT_RE.search(trailing)
    if comment_match:
        raw_desc = comment_match.group(1)
        unit_match = _UNIT_RE.search(raw_desc)
        if unit_match:
            unit = unit_match.group(1).strip()
            raw_desc = _UNIT_RE.sub("", raw_desc).strip()
        description = raw_desc

    return Variable(
        name=name,
        var_type=var_type,
        scope=scope,  # type: ignore[arg-type]
        gvl_name=gvl_name if scope == "GLOBAL" else None,
        initial_value=initial_value,
        var_class=var_class,  # type: ignore[arg-type]
        description=description,
        unit=unit,
    )
