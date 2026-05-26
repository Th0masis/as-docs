"""Project scanner — walks the AS project directory tree and discovers files."""
from __future__ import annotations
from pathlib import Path

from as_docs.config import Config, find_project_root
from as_docs.model.graph import POUNode
from as_docs.model.project import ProjectModel, RawSTFile
from as_docs.scanner.pkg_parser import parse_pkg
from as_docs.scanner.var_parser import parse_var_file
from as_docs.scanner.typ_parser import parse_typ_file
from as_docs.scanner.per_parser import parse_per_file


def scan_project(config: Config, project_root: Path | None = None) -> ProjectModel:
    """Scan an AS project and return a populated ProjectModel.

    Args:
        config: Loaded .as-docs.yaml config.
        project_root: Explicit project root. If None, detected from config.
    """
    if project_root is None:
        project_root = _resolve_root(config)

    model = ProjectModel(
        project_root=project_root,
        project_name=config.project.name or project_root.name,
        as_version=config.project.as_version,
        active_configuration=config.scanner.active_configuration or "",
    )

    ignore = set(config.scanner.ignore_dirs)
    logical = project_root / "Logical"
    physical = project_root / "Physical"

    # -- Scan Logical/ for POUs, vars, types, ST sources -------------------
    if logical.is_dir():
        _scan_logical(logical, model, config, ignore)

    # -- Scan Physical/ for task config ------------------------------------
    if physical.is_dir():
        _scan_physical(physical, model, config)

    return model


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_root(config: Config) -> Path:
    root = Path(config.project.root).resolve()
    if (root / "Logical").is_dir() and (root / "Physical").is_dir():
        return root
    detected = find_project_root()
    if detected:
        return detected
    raise FileNotFoundError(
        "Cannot locate AS project root (Logical/ + Physical/ not found). "
        "Run 'as-docs init' from within the project directory."
    )


def _scan_logical(
    logical: Path,
    model: ProjectModel,
    config: Config,
    ignore: set[str],
) -> None:
    ext_prefixes = config.scanner.external_lib_prefixes
    libraries_dir = logical / "Libraries"

    for path in logical.rglob("*"):
        # Skip ignored directories
        if any(part in ignore for part in path.parts):
            continue

        # Handle Libraries/ separately
        if libraries_dir.is_dir() and _is_under(path, libraries_dir):
            if not config.scanner.scan_libraries:
                continue
            # External lib detection happens per-POU after pkg_parser runs

        suffix = path.suffix.lower()

        if suffix in (".pkg", ".prg") and path.is_file():
            pou = parse_pkg(path)
            if pou:
                _apply_external_flag(pou, ext_prefixes)
                model.pous[pou.name] = pou

        elif suffix == ".var" and path.is_file():
            vars_, gvl_name = parse_var_file(path)
            for v in vars_:
                model.global_vars[v.name] = v
                if gvl_name:
                    model.gvl_map.setdefault(gvl_name, []).append(v)

        elif suffix == ".typ" and path.is_file():
            types = parse_typ_file(path)
            for dt in types:
                model.data_types[dt.name] = dt

        elif suffix == ".st" and path.is_file():
            pou_name = path.stem  # e.g. Main.st → Main (resolved properly later)
            # Try to match to an existing POU by parent dir name
            parent_name = path.parent.name
            matched_name = parent_name if parent_name in model.pous else pou_name
            model.st_files.append(
                RawSTFile(path=path, pou_name=matched_name, source=path.read_text(encoding="utf-8", errors="replace"))
            )


def _scan_physical(physical: Path, model: ProjectModel, config: Config) -> None:
    active_config = config.scanner.active_configuration

    # Find active configuration directory
    config_dirs = sorted(
        [d for d in physical.iterdir() if d.is_dir()],
        key=lambda d: d.name,
    )
    if not config_dirs:
        return

    if active_config:
        chosen = next((d for d in config_dirs if d.name == active_config), None)
        if chosen is None:
            chosen = config_dirs[0]
    else:
        chosen = config_dirs[0]

    model.active_configuration = chosen.name

    # Find Cpu.per files inside chosen config
    for per_file in chosen.rglob("Cpu.per"):
        tasks = parse_per_file(per_file, configuration=chosen.name)
        for task in tasks:
            model.tasks[task.name] = task


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _apply_external_flag(pou: POUNode, ext_prefixes: list[str]) -> None:
    if any(pou.name.startswith(p) for p in ext_prefixes):
        pou.is_external_library = True
