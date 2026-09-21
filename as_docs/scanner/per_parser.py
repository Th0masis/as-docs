"""Parser for Cpu.per XML — extracts task configurations.

B&R AS task config quirk: The <Task Name="..."> attribute is limited to
10 characters. Match tasks to programs using the <Source> path attribute,
not by name equality.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from as_docs.model.graph import TaskConfig

_TASK_TYPE_MAP = {
    "cyclic": "cyclic",
    "init": "init",
    "exit": "exit",
    "event": "cyclic",  # treat event tasks as cyclic for doc purposes
}

# Regex fallbacks for malformed XML
_TASK_RE = re.compile(
    r'<Task\s[^>]*Name\s*=\s*"([^"]*)"[^>]*>',
    re.IGNORECASE,
)


def parse_per_file(path: Path, configuration: str = "") -> list[TaskConfig]:
    """Parse Cpu.per and return TaskConfig objects for each task found."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    try:
        return _parse_xml(text, configuration)
    except ET.ParseError:
        return _parse_regex_fallback(text, configuration)


def _parse_xml(text: str, configuration: str) -> list[TaskConfig]:
    root = ET.fromstring(text)
    root_local = _local_name(root.tag)
    if root_local == "SwConfiguration":
        return _parse_sw_configuration(root, configuration)

    tasks: list[TaskConfig] = []

    # Strip namespace prefix for compatibility
    ns = _detect_namespace(root.tag)

    for task_el in root.iter(_tag(ns, "Task")):
        task_name = task_el.get("Name", "")
        task_type_raw = task_el.get("TaskClass", task_el.get("Type", "cyclic")).lower()
        cycle_time_str = task_el.get("CycleTime", task_el.get("Cycle", ""))
        cycle_time_ms = _parse_cycle_time(cycle_time_str)
        task_type = _TASK_TYPE_MAP.get(task_type_raw, "cyclic")

        programs: list[str] = []
        for prog_el in task_el.iter(_tag(ns, "Property")):
            source = prog_el.get("Source", "")
            if source:
                # Extract program name from path like "MainControl/Main.st" → "MainControl"
                prog_name = _program_name_from_source(source)
                if prog_name:
                    programs.append(prog_name)

        # Also check <ObjRef> elements used in some AS versions
        for ref_el in task_el.iter(_tag(ns, "ObjRef")):
            source = ref_el.get("Source", ref_el.text or "")
            prog_name = _program_name_from_source(source)
            if prog_name and prog_name not in programs:
                programs.append(prog_name)

        if task_name:
            tasks.append(
                TaskConfig(
                    name=task_name,
                    task_type=task_type,  # type: ignore[arg-type]
                    cycle_time_ms=cycle_time_ms,
                    programs=programs,
                    configuration=configuration,
                )
            )

    return tasks


def _parse_sw_configuration(root: ET.Element, configuration: str) -> list[TaskConfig]:
    """Parse AS6 Cpu.sw task layout.

    Shape:
      <SwConfiguration>
        <TaskClass Name="Cyclic#1">
          <Task Name="ProgAlias" Source="Infrastructure.Alarms.AlarmProg.prg" />
        </TaskClass>
      </SwConfiguration>
    """
    tasks: list[TaskConfig] = []
    ns = _detect_namespace(root.tag)

    for class_el in root.iter(_tag(ns, "TaskClass")):
        class_name = class_el.get("Name", "").strip()
        if not class_name:
            continue

        class_name_lower = class_name.lower()
        if class_name_lower.startswith("init"):
            task_type = "init"
        elif class_name_lower.startswith("exit"):
            task_type = "exit"
        else:
            task_type = "cyclic"

        cycle_time_ms = _parse_cycle_time(
            class_el.get("CycleTime", class_el.get("Cycle", ""))
        )
        programs: list[str] = []

        for task_el in class_el.iter(_tag(ns, "Task")):
            source = task_el.get("Source", "")
            prog_name = _program_name_from_source(source)
            if prog_name and prog_name not in programs:
                programs.append(prog_name)

        tasks.append(
            TaskConfig(
                name=class_name,
                task_type=task_type,  # type: ignore[arg-type]
                cycle_time_ms=cycle_time_ms,
                programs=programs,
                configuration=configuration,
            )
        )

    return tasks


def _parse_regex_fallback(text: str, configuration: str) -> list[TaskConfig]:
    tasks = []
    for m in _TASK_RE.finditer(text):
        tasks.append(
            TaskConfig(
                name=m.group(1),
                task_type="cyclic",
                cycle_time_ms=None,
                programs=[],
                configuration=configuration,
            )
        )
    return tasks


def _detect_namespace(tag: str) -> str:
    if tag.startswith("{"):
        return tag[1 : tag.index("}")]
    return ""


def _local_name(tag: str) -> str:
    if tag.startswith("{"):
        return tag[tag.index("}") + 1 :]
    return tag


def _tag(ns: str, local: str) -> str:
    return f"{{{ns}}}{local}" if ns else local


def _parse_cycle_time(raw: str) -> int | None:
    """Convert cycle time string to milliseconds.

    Handles formats like: "10ms", "0.01s", "10000us", "10"
    """
    raw = raw.strip().lower()
    if not raw:
        return None
    try:
        if raw.endswith("ms"):
            return int(float(raw[:-2]))
        if raw.endswith("us"):
            return max(1, int(float(raw[:-2]) / 1000))
        if raw.endswith("s"):
            return int(float(raw[:-1]) * 1000)
        # Plain number — assume microseconds (AS default for cycle time)
        val = int(raw)
        return max(1, val // 1000) if val > 10000 else val
    except (ValueError, OverflowError):
        return None


def _program_name_from_source(source: str) -> str | None:
    """Extract program/package name from a Source path attribute.

    Examples:
        "MainControl/Main.st"    → "MainControl"
        "Drive/ConvCtrl"         → "ConvCtrl"
        ":SEG:MainControl:Main"  → "MainControl"
    """
    source = source.strip()
    if not source:
        return None

    # Dotted AS6 path style: Infrastructure.Alarms.AlarmProg.prg -> AlarmProg
    if "/" not in source and "\\" not in source and "." in source:
        parts = source.split(".")
        if len(parts) >= 2:
            ext = parts[-1].lower()
            if ext in {"prg", "fub", "fun", "st"}:
                return parts[-2]

    # AS6 style ":SEG:Package:Program"
    if source.startswith(":"):
        parts = [p for p in source.split(":") if p]
        return parts[-2] if len(parts) >= 2 else (parts[0] if parts else None)
    # Path style "Package/Program.st" or "Package/Program"
    parts = source.replace("\\", "/").split("/")
    if len(parts) >= 2:
        return parts[-2]
    return parts[0].split(".")[0] if parts else None
