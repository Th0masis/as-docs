"""Parser for .pkg and .prg files — extracts POU metadata."""
from __future__ import annotations
import re
from pathlib import Path

from as_docs.model.graph import POUNode

# .prg / .pkg files use a quasi-XML format with an <Object> root element.
# Example:
#   <?xml version="1.0" encoding="utf-8"?>
#   <Object Version="4" SubVersion="0" Name="MotorControl" ...
#     ObjectType="661" ...>
# ObjectType values (observed):
#   661 → PROGRAM
#   665 → FUNCTION_BLOCK
#   667 → FUNCTION
#   Other / absent → PROGRAM (default)

_OBJECT_TYPE_MAP = {
    "661": "PROGRAM",
    "665": "FUNCTION_BLOCK",
    "667": "FUNCTION",
}

_NAME_RE = re.compile(r'\bName\s*=\s*"([^"]+)"', re.IGNORECASE)
_OBJ_TYPE_RE = re.compile(r'\bObjectType\s*=\s*"([^"]+)"', re.IGNORECASE)


def parse_pkg(path: Path) -> POUNode | None:
    """Parse a .pkg or .prg file and return a POUNode, or None if not a POU."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    name_match = _NAME_RE.search(text)
    if not name_match:
        # Fall back to file stem
        name = path.stem
    else:
        name = name_match.group(1)

    obj_type_match = _OBJ_TYPE_RE.search(text)
    raw_type = obj_type_match.group(1) if obj_type_match else ""
    pou_type = _OBJECT_TYPE_MAP.get(raw_type, "PROGRAM")

    return POUNode(
        name=name,
        pou_type=pou_type,  # type: ignore[arg-type]
        source_file=str(path),
    )
