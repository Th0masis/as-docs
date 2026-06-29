"""Parser for .pkg and .prg files — extracts POU metadata.

Supports two Automation Studio file formats:

AS4 format (.prg / .pkg):
  <Object Version="4" SubVersion="0" Name="MotorControl" ObjectType="661" ...>
  ObjectType 661 = PROGRAM, 665 = FUNCTION_BLOCK, 667 = FUNCTION

AS6 format:
  Package.pkg:
    <Package xmlns="http://br-automation.co.at/AS/Package">
      <Objects>
        <Object Type="Package">SubPkg</Object>
        <Object Type="Program" Language="IEC">MyProg</Object>
      </Objects>
    </Package>
  IEC.prg / IEC.fub / IEC.fun:
    <Program SubType="IEC" xmlns="http://br-automation.co.at/AS/Program">
    POU name is derived from the parent directory.
"""
from __future__ import annotations
import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import NamedTuple

from as_docs.model.graph import POUNode

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# AS4 constants
# ---------------------------------------------------------------------------

_OBJECT_TYPE_MAP = {
    "661": "PROGRAM",
    "665": "FUNCTION_BLOCK",
    "667": "FUNCTION",
}

_NAME_RE = re.compile(r'\bName\s*=\s*"([^"]+)"', re.IGNORECASE)
_OBJ_TYPE_RE = re.compile(r'\bObjectType\s*=\s*"([^"]+)"', re.IGNORECASE)

# ---------------------------------------------------------------------------
# AS6 constants
# ---------------------------------------------------------------------------

_AS6_PKG_NS = "http://br-automation.co.at/AS/Package"
_AS6_PKG_MARKER = f'xmlns="{_AS6_PKG_NS}"'

# IEC source manifest file stems (always named IEC.<ext> in AS6)
_AS6_IEC_STEMS = {"IEC"}

_AS6_EXT_TYPE_MAP = {
    ".prg": "PROGRAM",
    ".fub": "FUNCTION_BLOCK",
    ".fun": "FUNCTION",
}

# AS6 Package.pkg Object Type → POUNode pou_type
_AS6_OBJ_TYPE_MAP = {
    "Program": "PROGRAM",
    "FunctionBlock": "FUNCTION_BLOCK",
    "Function": "FUNCTION",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class PkgObject(NamedTuple):
    """An entry parsed from an AS6 Package.pkg <Object> element."""
    obj_type: str       # "Package", "Program", "Library", "File", "FunctionBlock", "Function"
    name: str
    description: str


def parse_as6_package_objects(path: Path) -> list[PkgObject]:
    """Parse an AS6 Package.pkg file and return its declared objects.

    Returns an empty list on any error (missing file, parse failure, wrong format).
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    if _AS6_PKG_MARKER not in text:
        return []  # Not an AS6 Package.pkg

    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        logger.warning("Failed to parse %s: %s", path, exc)
        return []

    # The root tag may include the namespace: {http://...}Package
    objects_elem = root.find(f"{{{_AS6_PKG_NS}}}Objects")
    if objects_elem is None:
        objects_elem = root.find("Objects")
    if objects_elem is None:
        return []

    result: list[PkgObject] = []
    for obj in objects_elem:
        # Strip namespace prefix from tag if present
        tag = obj.tag.split("}")[-1] if "}" in obj.tag else obj.tag
        if tag != "Object":
            continue
        obj_type = obj.get("Type", "")
        name = (obj.text or "").strip()
        description = obj.get("Description", "")
        if name:
            result.append(PkgObject(obj_type=obj_type, name=name, description=description))

    return result


def parse_pkg(path: Path) -> POUNode | None:
    """Parse a .pkg or .prg file and return a POUNode, or None if not a POU.

    Handles:
    - AS6 Package.pkg (package descriptor) → returns None
    - AS6 IEC.prg / IEC.fub / IEC.fun (POU manifest) → name from parent dir
    - AS4 .prg / .pkg with Name= attribute → name from attribute
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    # --- AS6 Package.pkg: not a POU, it's a package descriptor ---
    if path.name == "Package.pkg" and _AS6_PKG_MARKER in text:
        return None

    # --- AS6 IEC source manifest (IEC.prg, IEC.fub, IEC.fun) ---
    if path.stem.upper() in _AS6_IEC_STEMS:
        suffix = path.suffix.lower()
        pou_type = _AS6_EXT_TYPE_MAP.get(suffix, "PROGRAM")
        pou_name = path.parent.name  # parent directory IS the POU name
        if not pou_name:
            return None
        logger.debug("AS6 POU discovered: %s (%s) from %s", pou_name, pou_type, path)
        return POUNode(
            name=pou_name,
            pou_type=pou_type,  # type: ignore[arg-type]
            source_file=str(path),
        )

    # --- AS4 format: Name= and ObjectType= attributes ---
    name_match = _NAME_RE.search(text)
    if not name_match:
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
