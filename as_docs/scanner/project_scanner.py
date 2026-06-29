"""Project scanner — walks the AS project directory tree and discovers files."""
from __future__ import annotations
import logging
from pathlib import Path

from as_docs.config import Config, find_project_root
from as_docs.model.graph import POUNode
from as_docs.model.project import ProjectModel, RawSTFile
from as_docs.scanner.pkg_parser import (
    parse_pkg,
    parse_as6_package_objects,
    _AS6_OBJ_TYPE_MAP,
    _AS6_PKG_MARKER,
)
from as_docs.scanner.var_parser import parse_var_file
from as_docs.scanner.typ_parser import parse_typ_file
from as_docs.scanner.per_parser import parse_per_file

logger = logging.getLogger(__name__)


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

    # Determine whether to use AS6 package-tree scanning
    root_pkg = logical / "Package.pkg"
    use_tree_scan = (
        config.scanner.recursive_packages
        and root_pkg.is_file()
        and _is_as6_package(root_pkg)
    )

    if use_tree_scan:
        logger.debug("Using AS6 package-tree scan from %s", root_pkg)
        visited: set[Path] = set()
        _scan_package_tree(
            pkg_dir=logical,
            model=model,
            config=config,
            ignore=ignore,
            ext_prefixes=ext_prefixes,
            visited=visited,
            depth=0,
            package_path="",
        )
    else:
        logger.debug("Using rglob scan under %s", logical)

    # Always walk with rglob for .var / .typ / .st files (needed in both modes).
    # In tree-scan mode, skip .pkg/.prg — already handled by tree traversal.
    for path in logical.rglob("*"):
        # Skip ignored directories
        if any(part in ignore for part in path.parts):
            continue

        # Handle Libraries/ separately
        if libraries_dir.is_dir() and _is_under(path, libraries_dir):
            if not config.scanner.scan_libraries:
                continue

        suffix = path.suffix.lower()

        if not use_tree_scan and suffix in (".pkg", ".prg") and path.is_file():
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
            pou_name = path.stem
            parent_name = path.parent.name
            matched_name = parent_name if parent_name in model.pous else pou_name
            model.st_files.append(
                RawSTFile(path=path, pou_name=matched_name, source=path.read_text(encoding="utf-8", errors="replace"))
            )


def _is_as6_package(pkg_file: Path) -> bool:
    """Return True if *pkg_file* is an AS6-format Package.pkg."""
    try:
        text = pkg_file.read_text(encoding="utf-8", errors="replace")
        return _AS6_PKG_MARKER in text
    except OSError:
        return False


def _scan_package_tree(
    pkg_dir: Path,
    model: ProjectModel,
    config: Config,
    ignore: set[str],
    ext_prefixes: list[str],
    visited: set[Path],
    depth: int,
    package_path: str,
) -> None:
    """Recursively scan an AS6 package directory tree.

    Args:
        pkg_dir: Directory that should contain a Package.pkg.
        model: ProjectModel to populate.
        config: Loaded config.
        ignore: Set of directory names to skip.
        ext_prefixes: External library name prefixes.
        visited: Set of already-visited Package.pkg canonical paths (cycle detection).
        depth: Current recursion depth.
        package_path: Dot-separated path of parent package names (for POUNode.package_path).
    """
    if depth > config.scanner.max_recursion_depth:
        logger.warning(
            "max_recursion_depth=%d reached at %s — stopping recursion",
            config.scanner.max_recursion_depth,
            pkg_dir,
        )
        return

    pkg_file = pkg_dir / "Package.pkg"
    if not pkg_file.is_file():
        return

    canonical = pkg_file.resolve()
    if canonical in visited:
        logger.warning("Circular package reference detected at %s — skipping", pkg_file)
        return
    visited.add(canonical)

    objects = parse_as6_package_objects(pkg_file)
    logger.debug(
        "[depth=%d] Scanning %s → %d objects",
        depth,
        pkg_file,
        len(objects),
    )

    for obj in objects:
        if obj.name in ignore:
            continue

        obj_type = obj.obj_type

        if obj_type == "Package":
            nested_dir = pkg_dir / obj.name
            if nested_dir.is_dir():
                nested_path = f"{package_path}.{obj.name}" if package_path else obj.name
                logger.debug(
                    "[depth=%d] → recurse into package '%s'",
                    depth,
                    obj.name,
                )
                _scan_package_tree(
                    pkg_dir=nested_dir,
                    model=model,
                    config=config,
                    ignore=ignore,
                    ext_prefixes=ext_prefixes,
                    visited=visited,
                    depth=depth + 1,
                    package_path=nested_path,
                )
            else:
                logger.warning(
                    "Package reference '%s' in %s does not exist as a directory",
                    obj.name,
                    pkg_file,
                )

        elif obj_type in _AS6_OBJ_TYPE_MAP:
            pou_type = _AS6_OBJ_TYPE_MAP[obj_type]
            pou_dir = pkg_dir / obj.name
            if pou_dir.is_dir():
                iec_file = _find_iec_file(pou_dir, obj_type)
                pou = POUNode(
                    name=obj.name,
                    pou_type=pou_type,  # type: ignore[arg-type]
                    source_file=str(iec_file or pou_dir),
                    description=obj.description,
                    package_path=package_path,
                )
                _apply_external_flag(pou, ext_prefixes)
                model.pous[pou.name] = pou
                logger.debug(
                    "[depth=%d] → found %s '%s' (package: %s)",
                    depth,
                    pou_type,
                    obj.name,
                    package_path or "<root>",
                )
            else:
                logger.warning(
                    "Program/FB/Function '%s' in %s has no directory",
                    obj.name,
                    pkg_file,
                )

        elif obj_type == "Library" and config.scanner.scan_libraries:
            lib_dir = pkg_dir / obj.name
            src = str(lib_dir) if lib_dir.is_dir() else str(pkg_dir / obj.name)
            pou = POUNode(
                name=obj.name,
                pou_type="FUNCTION_BLOCK",  # type: ignore[arg-type]
                source_file=src,
                description=obj.description,
                package_path=package_path,
                is_external_library=True,
            )
            _apply_external_flag(pou, ext_prefixes)
            model.pous[pou.name] = pou

        # "File" objects are plain files — not POUs, skip.


def _find_iec_file(pou_dir: Path, obj_type: str = "Program") -> Path | None:
    """Find the IEC source manifest file inside a POU directory.

    Returns the first matching IEC.prg / IEC.fub / IEC.fun, or None.
    """
    ext_map = {
        "Program": ".prg",
        "FunctionBlock": ".fub",
        "Function": ".fun",
    }
    preferred_ext = ext_map.get(obj_type)
    # Try preferred extension first
    if preferred_ext:
        candidate = pou_dir / f"IEC{preferred_ext}"
        if candidate.is_file():
            return candidate
    # Fall back: any IEC.* file
    for ext in (".prg", ".fub", ".fun"):
        candidate = pou_dir / f"IEC{ext}"
        if candidate.is_file():
            return candidate
    return None


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
