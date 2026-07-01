"""Parser for .typ files — extracts STRUCT, ENUM, and ALIAS definitions."""

from __future__ import annotations
import re
from pathlib import Path

from as_docs.model.graph import DataType, DataTypeMember

_TYPE_BLOCK_RE = re.compile(
    r"TYPE\b(.*?)END_TYPE",
    re.IGNORECASE | re.DOTALL,
)
_STRUCT_BLOCK_RE = re.compile(
    r"(\w+)\s*:\s*STRUCT\b(.*?)END_STRUCT\s*;?",
    re.IGNORECASE | re.DOTALL,
)
_ENUM_BLOCK_RE = re.compile(
    r"(\w+)\s*:\s*\(\s*(.*?)\s*\)\s*;",
    re.IGNORECASE | re.DOTALL,
)
_ALIAS_RE = re.compile(
    r"(\w+)\s*:\s*(?:REFERENCE\s+TO\s+|ALIAS\s+)?(\w[\w\.]*)\s*;",
    re.IGNORECASE,
)
_MEMBER_LINE_RE = re.compile(
    r"^\s*(\w+)\s*:\s*([^;:=]+?)(?::=\s*([^;]+?))?\s*;(.*)$",
)
_COMMENT_RE = re.compile(r"\(\*\s*(.*?)\s*\)\s*$", re.DOTALL)
_UNIT_RE = re.compile(r"\[([^\]]+)\]")
_ENUM_VALUE_RE = re.compile(r"(\w+)(?:\s*:=\s*(\d+))?")


def parse_typ_file(path: Path) -> list[DataType]:
    """Parse a .typ file and return all DataType definitions found."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    source_file = str(path)
    results: list[DataType] = []

    for type_block in _TYPE_BLOCK_RE.finditer(text):
        body = type_block.group(1)

        # STRUCT definitions
        for struct_match in _STRUCT_BLOCK_RE.finditer(body):
            name = struct_match.group(1)
            members_text = struct_match.group(2)
            members = _parse_struct_members(members_text)
            results.append(
                DataType(
                    name=name,
                    kind="STRUCT",
                    members=members,
                    alias_target=None,
                    source_file=source_file,
                )
            )

        # ENUM definitions: TypeName : (VALUE1, VALUE2, VALUE3);
        for enum_match in _ENUM_BLOCK_RE.finditer(body):
            name = enum_match.group(1)
            if name.upper() in ("STRUCT", "END_STRUCT"):
                continue
            values_text = enum_match.group(2)
            members = _parse_enum_values(values_text)
            results.append(
                DataType(
                    name=name,
                    kind="ENUM",
                    members=members,
                    alias_target=None,
                    source_file=source_file,
                )
            )

        # ALIAS definitions (simple type aliases)
        remaining = _STRUCT_BLOCK_RE.sub("", body)
        remaining = _ENUM_BLOCK_RE.sub("", remaining)
        for alias_match in _ALIAS_RE.finditer(remaining):
            name = alias_match.group(1)
            target = alias_match.group(2)
            if name.upper() not in ("STRUCT", "ENUM", "TYPE", "END_TYPE"):
                results.append(
                    DataType(
                        name=name,
                        kind="ALIAS",
                        members=[],
                        alias_target=target,
                        source_file=source_file,
                    )
                )

    return results


def _parse_struct_members(text: str) -> list[DataTypeMember]:
    members = []
    for line in text.splitlines():
        m = _MEMBER_LINE_RE.match(line)
        if not m:
            continue
        name = m.group(1).strip()
        if name.upper() in ("END_STRUCT", "STRUCT", "TYPE", "END_TYPE"):
            continue
        member_type = m.group(2).strip()
        initial_value = m.group(3).strip() if m.group(3) else None
        trailing = m.group(4).strip()

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

        members.append(
            DataTypeMember(
                name=name,
                member_type=member_type,
                initial_value=initial_value,
                description=description,
                unit=unit,
            )
        )
    return members


def _parse_enum_values(text: str) -> list[DataTypeMember]:
    members = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        # Strip inline comments
        part_clean = re.sub(r"\(\*.*?\*\)", "", part).strip()
        m = _ENUM_VALUE_RE.match(part_clean)
        if m:
            members.append(
                DataTypeMember(
                    name=m.group(1),
                    member_type="ENUM_VALUE",
                    initial_value=m.group(2),
                )
            )
    return members
