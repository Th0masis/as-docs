"""as-cli command-line adapter for project discovery.

This module encapsulates all interaction with the as-cli executable.
It handles:
- Checking if as-cli is available (installed, in PATH)
- Managing daemon lifecycle (hybrid: auto-start on demand, persist for reuse)
- Executing commands (logical_list, symbol_search)
- Parsing JSON output
- Error handling and timeouts
"""
from __future__ import annotations
import json
import logging
import subprocess
from typing import Optional
import time

from .as_cli_models import (
    AsCliProjectData,
    parse_logical_list_output,
    parse_symbol_search_output,
)

logger = logging.getLogger(__name__)


# Exception Hierarchy

class AsCliError(Exception):
    """Base exception for all as-cli integration errors."""
    pass


class AsCliNotAvailableError(AsCliError):
    """as-cli executable not found or not available."""
    pass


class AsCliCommandError(AsCliError):
    """as-cli command returned non-zero exit code."""
    pass


class AsCliTimeoutError(AsCliError):
    """as-cli command timed out."""
    pass


class AsCliParseError(AsCliError):
    """Failed to parse as-cli JSON output."""
    pass


# Main Adapter

class AsCliAdapter:
    """
    Wrapper around as-cli command-line interface.
    
    Provides a Python interface to as-cli commands with:
    - Automatic daemon lifecycle management (hybrid: auto-start, persist)
    - JSON output parsing
    - Timeout handling
    - Error recovery
    """
    
    def __init__(self,
                 as_cli_path: str = "as-cli",
                 project_path: Optional[str] = None,
                 timeout_ms: int = 30000):
        """
        Initialize the adapter.
        
        Args:
            as_cli_path: Path to as-cli executable (default: auto-detect from PATH)
            project_path: Path to AS project (.apj or containing directory)
            timeout_ms: Timeout per command (milliseconds, default: 30s)
        """
        self.as_cli_path = as_cli_path
        self.project_path = project_path or "."
        self.timeout_ms = timeout_ms
        self._daemon_started = False
        self._daemon_check_count = 0
        
        logger.debug(
            f"AsCliAdapter initialized: path={as_cli_path}, "
            f"project={project_path}, timeout={timeout_ms}ms"
        )
    
    def is_available(self) -> bool:
        """
        Check if as-cli is available (installed and working).
        
        Returns:
            True if as-cli --version succeeds, False otherwise
        """
        try:
            result = subprocess.run(
                [self.as_cli_path, "--version"],
                timeout=5,
                capture_output=True,
                text=True
            )
            is_available = result.returncode == 0
            logger.debug(f"as-cli availability check: {is_available}")
            return is_available
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
            logger.debug(f"as-cli not available: {e}")
            return False
    
    def _ensure_daemon(self) -> bool:
        """
        Ensure as-cli daemon is running (hybrid lifecycle).
        
        Strategy:
        1. Try fast connectivity check (as-cli project status)
        2. If daemon running, return immediately
        3. If daemon not running, spawn it (one-time cost)
        4. Subsequent commands reuse the daemon
        
        Returns:
            True if daemon is running/started
        
        Raises:
            AsCliNotAvailableError: Failed to start daemon
        """
        if self._daemon_started:
            return True  # Already started in this session
        
        self._daemon_check_count += 1
        
        # Fast connectivity check: try project status (2s timeout)
        try:
            logger.debug("Checking for existing as-cli daemon...")
            result = subprocess.run(
                [self.as_cli_path, "--project", self.project_path,
                 "project", "status"],
                timeout=2,
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0:
                logger.debug("as-cli daemon already running (reusing)")
                self._daemon_started = True
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        # Daemon not running; try to start it
        logger.debug("Starting as-cli daemon...")
        try:
            result = subprocess.run(
                [self.as_cli_path, "--project", self.project_path,
                 "project", "status"],
                timeout=self.timeout_ms / 1000.0,
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0:
                logger.debug("as-cli daemon started successfully")
                self._daemon_started = True
                return True
            else:
                raise AsCliCommandError(
                    f"Failed to start as-cli daemon: {result.stderr}"
                )
        except subprocess.TimeoutExpired:
            raise AsCliTimeoutError(
                f"as-cli daemon startup timed out ({self.timeout_ms}ms)"
            )
        except Exception as e:
            raise AsCliNotAvailableError(
                f"Failed to start as-cli daemon: {e}"
            )
    
    def get_logical_list(self) -> dict:
        """
        Execute: as-cli logical list --format json
        
        Retrieves the logical view (modules, tasks, programs) of the project.
        
        Returns:
            Raw JSON dict from as-cli output
        
        Raises:
            AsCliNotAvailableError: as-cli not available or daemon failed
            AsCliTimeoutError: Command timed out
            AsCliCommandError: as-cli returned error
            AsCliParseError: Failed to parse JSON output
        """
        self._ensure_daemon()
        
        try:
            logger.debug("Executing: as-cli logical list --format json")
            start_time = time.time()
            
            result = subprocess.run(
                [self.as_cli_path, "--project", self.project_path,
                 "logical", "list", "--format", "json"],
                timeout=self.timeout_ms / 1000.0,
                capture_output=True,
                text=True,
                check=False
            )
            
            elapsed_ms = (time.time() - start_time) * 1000
            
            if result.returncode != 0:
                raise AsCliCommandError(
                    f"as-cli logical list failed: {result.stderr}"
                )
            
            try:
                data = json.loads(result.stdout)
                logger.debug(
                    f"as-cli logical list succeeded ({elapsed_ms:.0f}ms): "
                    f"{len(data.get('modules', []))} modules, "
                    f"{len(data.get('tasks', []))} tasks, "
                    f"{len(data.get('programs', []))} programs"
                )
                return data
            except json.JSONDecodeError as e:
                raise AsCliParseError(f"Failed to parse logical list JSON: {e}")
        
        except subprocess.TimeoutExpired:
            raise AsCliTimeoutError(
                f"as-cli logical list timed out ({self.timeout_ms}ms)"
            )
    
    def get_symbol_search(self, query: str = "*") -> dict:
        """
        Execute: as-cli symbol search <query> --format json
        
        Searches for symbols in the project.
        
        Args:
            query: Symbol search query (default "*" = all symbols)
        
        Returns:
            Raw JSON dict from as-cli output
        
        Raises:
            AsCliNotAvailableError: as-cli not available or daemon failed
            AsCliTimeoutError: Command timed out
            AsCliCommandError: as-cli returned error
            AsCliParseError: Failed to parse JSON output
        """
        self._ensure_daemon()
        
        try:
            logger.debug(f"Executing: as-cli symbol search {query} --format json")
            start_time = time.time()
            
            result = subprocess.run(
                [self.as_cli_path, "--project", self.project_path,
                 "symbol", "search", query, "--format", "json"],
                timeout=self.timeout_ms / 1000.0,
                capture_output=True,
                text=True,
                check=False
            )
            
            elapsed_ms = (time.time() - start_time) * 1000
            
            if result.returncode != 0:
                raise AsCliCommandError(
                    f"as-cli symbol search failed: {result.stderr}"
                )
            
            try:
                data = json.loads(result.stdout)
                logger.debug(
                    f"as-cli symbol search succeeded ({elapsed_ms:.0f}ms): "
                    f"{len(data.get('symbols', []))} symbols found"
                )
                return data
            except json.JSONDecodeError as e:
                raise AsCliParseError(f"Failed to parse symbol search JSON: {e}")
        
        except subprocess.TimeoutExpired:
            raise AsCliTimeoutError(
                f"as-cli symbol search timed out ({self.timeout_ms}ms)"
            )
    
    def scan_project(self) -> AsCliProjectData:
        """
        Scan the project using as-cli (convenience method).
        
        Executes both logical_list and symbol_search, combines results.
        
        Returns:
            AsCliProjectData with all discovered modules and symbols
        
        Raises:
            AsCliError: Any of the above errors
        """
        logger.info(f"Scanning project with as-cli: {self.project_path}")
        start_time = time.time()
        
        # Get logical structure
        raw_logical_list = self.get_logical_list()
        modules = parse_logical_list_output(raw_logical_list)
        
        # Get symbols
        raw_symbol_search = self.get_symbol_search("*")
        symbols = parse_symbol_search_output(raw_symbol_search)
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        project_data = AsCliProjectData(
            modules=modules,
            symbols=symbols,
            raw_logical_list=raw_logical_list,
            raw_symbol_search=raw_symbol_search,
            project_path=str(self.project_path),
            execution_time_ms=elapsed_ms
        )
        
        logger.info(
            f"as-cli scan complete ({elapsed_ms:.0f}ms): "
            f"{len(modules)} modules, {len(symbols)} symbols"
        )
        
        return project_data
