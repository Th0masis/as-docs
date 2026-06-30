#!/usr/bin/env python3
"""Test file reorganization script."""
import subprocess
from pathlib import Path

test_dir = Path("c:/100_Projects/as-docs/tests")

# Files to delete
to_delete = [
    "test_phase1.py",
    "test_phase2_cli.py",
    "test_phase3_mcp_server.py",
    "test_phase4_cli.py",
    "test_phase5_template_integration.py",
]

# Files to rename (old_name -> new_name)
to_rename = {
    "test_phase2_cache.py": "test_enrichment_cache.py",
    "test_phase2_config.py": "test_core_config.py",
    "test_phase2_copilot_auth.py": "test_copilot_auth.py",
    "test_phase2_enrichment.py": "test_enrichment.py",
    "test_phase2_providers.py": "test_ai_providers.py",
    "test_phase2_7_integration_validation.py": "test_integration_validation.py",
    "test_phase6_flow_pipeline.py": "test_flow_pipeline.py",
    "test_phase7_packaging.py": "test_packaging.py",
}

print("Deleting obsolete test files...")
for f in to_delete:
    path = test_dir / f
    if path.exists():
        subprocess.run(["git", "rm", "-f", str(path)], cwd=str(test_dir.parent))
        print(f"  - Deleted {f}")

print("\nRenaming test files...")
for old, new in to_rename.items():
    old_path = test_dir / old
    new_path = test_dir / new
    if old_path.exists():
        subprocess.run(["git", "mv", str(old_path), str(new_path)], cwd=str(test_dir.parent))
        print(f"  - Renamed {old} -> {new}")

print("\nFinal test files:")
for f in sorted(test_dir.glob("test_*.py")):
    print(f"  - {f.name}")
