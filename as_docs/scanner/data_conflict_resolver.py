"""Data conflict resolution for filesystem vs as-cli sources.

This module merges project data from two sources (filesystem scanner and as-cli)
using a smart union strategy, detects conflicts, and generates a detailed report.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from .as_cli_models import AsCliProjectData

logger = logging.getLogger(__name__)


@dataclass
class Conflict:
    """Represents a single conflict between filesystem and as-cli data."""

    conflict_type: str
    """Type of conflict: 'path_mismatch', 'type_mismatch', 'scope_mismatch', etc."""

    pou_name: str
    """Name of the POU with conflict."""

    fs_value: str | None = None
    """Value from filesystem source."""

    as_cli_value: str | None = None
    """Value from as-cli source."""

    severity: str = "warning"
    """Severity level: 'info', 'warning', 'error'."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)


@dataclass
class ConflictReport:
    """Summary of merge results and conflicts between data sources."""

    conflicts: list[Conflict] = field(default_factory=list)
    """List of detected conflicts."""

    pou_count_fs: int = 0
    """Total POUs found in filesystem."""

    pou_count_as_cli: int = 0
    """Total POUs found in as-cli."""

    pou_count_merged: int = 0
    """Total POUs in merged result (union)."""

    fs_only_pous: list[str] = field(default_factory=list)
    """POUs found only in filesystem (may be stale)."""

    as_cli_only_pous: list[str] = field(default_factory=list)
    """POUs found only in as-cli (filesystem may have missed)."""

    agreed_pous: list[str] = field(default_factory=list)
    """POUs where both sources agree."""

    merge_timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    """ISO 8601 timestamp of merge."""

    @property
    def has_conflicts(self) -> bool:
        """Check if any conflicts were detected."""
        return len(self.conflicts) > 0

    @property
    def summary(self) -> str:
        """Human-readable summary of merge results."""
        conflict_types = {}
        for conflict in self.conflicts:
            ct = conflict.conflict_type
            conflict_types[ct] = conflict_types.get(ct, 0) + 1

        conflict_details = ""
        if conflict_types:
            conflict_details = "\n  " + "\n  ".join(
                f"{ct}: {count}" for ct, count in sorted(conflict_types.items())
            )

        return f"""
Merge Summary ({self.merge_timestamp}):
  Filesystem POUs: {self.pou_count_fs}
  as-cli POUs: {self.pou_count_as_cli}
  Merged (union): {self.pou_count_merged}
  
  POUs both sources agree on: {len(self.agreed_pous)}
  POUs filesystem only: {len(self.fs_only_pous)}
  POUs as-cli only: {len(self.as_cli_only_pous)}
  
  Conflicts detected: {len(self.conflicts)}{conflict_details}
""".strip()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "conflicts": [c.to_dict() for c in self.conflicts],
            "pou_count_fs": self.pou_count_fs,
            "pou_count_as_cli": self.pou_count_as_cli,
            "pou_count_merged": self.pou_count_merged,
            "fs_only_pous": self.fs_only_pous,
            "as_cli_only_pous": self.as_cli_only_pous,
            "agreed_pous": self.agreed_pous,
            "merge_timestamp": self.merge_timestamp,
            "summary": self.summary,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


class DataConflictResolver:
    """
    Merges filesystem and as-cli project data using smart union strategy.

    Strategy (Phase 0 Decision 0.5):
    1. Union all POUs from both sources
    2. For POUs in both: compare paths/types, flag conflicts
    3. Mark source for each POU (fs_only, as_cli_only, both)
    4. Generate detailed ConflictReport
    5. Return merged data + report for user review
    """

    def __init__(self):
        """Initialize resolver."""
        self.logger = logging.getLogger(__name__)

    def merge(
        self, fs_pous: dict[str, Any], as_cli_data: AsCliProjectData
    ) -> tuple[dict[str, Any], ConflictReport]:
        """
        Merge filesystem and as-cli project data intelligently.

        Args:
            fs_pous: Dictionary of POUs from filesystem scanner
                     Maps POU name -> POU object with attributes:
                     - name, source_file, pou_type, etc.
            as_cli_data: AsCliProjectData with modules and symbols from as-cli

        Returns:
            (merged_pous, conflict_report) where:
            - merged_pous: Union of all POUs with source metadata
            - conflict_report: Detailed ConflictReport

        Raises:
            ValueError: If input data is invalid
        """
        if not isinstance(fs_pous, dict):
            raise TypeError("fs_pous must be a dictionary")
        if not isinstance(as_cli_data, AsCliProjectData):
            raise TypeError("as_cli_data must be AsCliProjectData instance")

        merged_pous = {}
        conflicts = []
        agreed_pous = []
        fs_only_pous = []
        as_cli_only_pous = []

        # Step 1: Add all filesystem POUs
        self.logger.debug(f"Processing {len(fs_pous)} filesystem POUs")

        for pou_name, pou in fs_pous.items():
            merged_pous[pou_name] = pou

            # Add metadata tracking source
            if not hasattr(pou, "metadata") or pou.metadata is None:
                pou.metadata = {}

            pou.metadata["source"] = "filesystem"

        # Step 2: Process as-cli modules, check for conflicts
        self.logger.debug(f"Processing {len(as_cli_data.modules)} as-cli modules")

        for as_cli_module in as_cli_data.modules:
            pou_name = as_cli_module.name

            if pou_name in merged_pous:
                # Conflict: both sources have this POU
                fs_pou = merged_pous[pou_name]
                self.logger.debug(f"POU {pou_name} found in both sources")

                # Check path agreement
                fs_path = getattr(fs_pou, "source_file", None)
                as_cli_path = as_cli_module.path

                if fs_path != as_cli_path:
                    conflict = Conflict(
                        conflict_type="path_mismatch",
                        pou_name=pou_name,
                        fs_value=fs_path,
                        as_cli_value=as_cli_path,
                        severity="warning",
                    )
                    conflicts.append(conflict)
                    self.logger.warning(
                        f"Path mismatch for {pou_name}: "
                        f"fs={fs_path}, as_cli={as_cli_path}"
                    )

                # Check type agreement
                fs_type = getattr(fs_pou, "pou_type", None)
                as_cli_type = as_cli_module.pou_type

                if fs_type != as_cli_type:
                    conflict = Conflict(
                        conflict_type="type_mismatch",
                        pou_name=pou_name,
                        fs_value=fs_type,
                        as_cli_value=as_cli_type,
                        severity="warning",
                    )
                    conflicts.append(conflict)
                    self.logger.warning(
                        f"Type mismatch for {pou_name}: "
                        f"fs={fs_type}, as_cli={as_cli_type}"
                    )

                # Use as-cli data as source of truth (more authoritative)
                # Copy over attributes from as_cli_module to fs_pou
                fs_pou.source_file = as_cli_module.path
                fs_pou.pou_type = as_cli_module.pou_type
                fs_pou.metadata["source"] = "both"
                fs_pou.metadata["as_cli_verified"] = True

                agreed_pous.append(pou_name)

            else:
                # New POU from as-cli (fs missed it)
                self.logger.debug(f"POU {pou_name} found only in as-cli")

                # Create a minimal POU object with as-cli data
                pou_dict = {
                    "name": as_cli_module.name,
                    "source_file": as_cli_module.path,
                    "pou_type": as_cli_module.pou_type,
                    "metadata": {"source": "as_cli_only", "discovered_by_as_cli": True},
                }

                merged_pous[pou_name] = pou_dict
                as_cli_only_pous.append(pou_name)

        # Step 3: Identify fs-only POUs
        for pou_name in fs_pous:
            if pou_name not in agreed_pous and pou_name not in as_cli_only_pous:
                fs_only_pous.append(pou_name)
                self.logger.debug(f"POU {pou_name} found only in filesystem")

        # Step 4: Create conflict report
        report = ConflictReport(
            conflicts=conflicts,
            pou_count_fs=len(fs_pous),
            pou_count_as_cli=len(as_cli_data.modules),
            pou_count_merged=len(merged_pous),
            fs_only_pous=sorted(fs_only_pous),
            as_cli_only_pous=sorted(as_cli_only_pous),
            agreed_pous=sorted(agreed_pous),
            merge_timestamp=datetime.now(UTC).isoformat(),
        )

        # Step 5: Log summary
        if report.has_conflicts:
            self.logger.warning(f"Merge detected conflicts:\n{report.summary}")
        else:
            self.logger.info(
                f"Merge clean: "
                f"fs={report.pou_count_fs}, "
                f"as_cli={report.pou_count_as_cli}, "
                f"merged={report.pou_count_merged}"
            )

        if fs_only_pous:
            self.logger.info(
                f"POUs in filesystem only (may be stale): {fs_only_pous[:5]}..."
            )

        if as_cli_only_pous:
            self.logger.info(
                f"POUs in as-cli only (filesystem may have missed): "
                f"{as_cli_only_pous[:5]}..."
            )

        return merged_pous, report
