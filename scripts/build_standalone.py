from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from as_docs.packaging import build_standalone_plan


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the optional standalone as-docs executable.")
    parser.add_argument("--project-root", default=Path(__file__).resolve().parents[1], type=Path)
    parser.add_argument("--dist-dir", default=None, type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Print the PyInstaller command without running it.")
    args = parser.parse_args()

    plan = build_standalone_plan(args.project_root, dist_dir=args.dist_dir)
    print("Standalone packaging plan:")
    print(f"  project_root: {plan.project_root}")
    print(f"  entrypoint:   {plan.entrypoint}")
    print(f"  dist_dir:     {plan.dist_dir}")
    print(f"  spec_file:    {plan.spec_file}")
    print(f"  output:       {plan.output_binary}")
    print(f"  executable:   {plan.executable_name}")
    print("  command:")
    print("    " + " ".join(plan.command))

    if args.dry_run:
        return 0

    if shutil.which("pyinstaller") is None:
        raise FileNotFoundError("pyinstaller is not installed or not on PATH")

    completed = subprocess.run(plan.command, cwd=plan.project_root)
    if completed.returncode != 0:
        return completed.returncode

    if not plan.output_binary.exists():
        raise FileNotFoundError(f"Expected standalone binary was not created: {plan.output_binary}")

    print(f"Built standalone binary: {plan.output_binary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())