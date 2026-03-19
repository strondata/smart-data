"""CLI sub-commands for mesh component orchestration."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import typer

from aptdata.cli.rendering.console import SmartConsole
from aptdata.qa.agent import QAAgent

mesh_app = typer.Typer(
    name="mesh", help="Orchestrate mesh components (job-wheel, docker-compose-app, …)."
)

_MESH_FILE = "mesh.yaml"


def _load_mesh(path: Path) -> dict:
    """Load and parse a mesh.yaml file."""
    try:
        import yaml  # type: ignore[import]
    except ImportError:
        # Minimal YAML parser for simple key: value lines (no external dep required)
        import re

        # Minimal fallback parser: handles only top-level scalar key: value lines.
        # Does NOT support nested structures, lists, or multi-line values.
        # Install PyYAML (`pip install pyyaml`) for full YAML support.
        data: dict = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = re.match(r'^(\w[\w\-]*):\s*"?([^"]*)"?\s*$', line)
            if match:
                data[match.group(1)] = match.group(2).strip()
        return data

    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _find_mesh_yaml(directory: Path) -> Path | None:  # noqa: UP007
    """Return the path to mesh.yaml in *directory* or None if not found."""
    candidate = directory / _MESH_FILE
    return candidate if candidate.exists() else None


def _resolve_mesh_file(root: Path, component: str) -> Path | None:  # noqa: UP007
    """Find mesh.yaml for the given component (by name or direct path)."""
    component_path = root / component
    if component_path.is_dir():
        mesh_file = _find_mesh_yaml(component_path)
        if mesh_file:
            return mesh_file

    for candidate in root.rglob(_MESH_FILE):
        try:
            data = _load_mesh(candidate)
            if data.get("component") == component:
                return candidate
        except Exception:  # noqa: BLE001
            continue

    return None


@mesh_app.command("list")
def mesh_list(
    directory: Path = typer.Option(
        Path("."),
        "--dir",
        "-d",
        help="Directory to scan for mesh.yaml files.",
        exists=False,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit JSON lines."),
) -> None:
    """List mesh components found under *directory*.

    Recursively searches for mesh.yaml files and displays component metadata.

    Examples
    --------
    aptdata mesh list
    aptdata mesh list --dir ./projects
    """
    console = SmartConsole(json_mode=json_mode)
    root = directory.resolve()
    components: list[dict] = []

    for mesh_file in sorted(root.rglob(_MESH_FILE)):
        try:
            data = _load_mesh(mesh_file)
            components.append(
                {
                    "component": data.get("component", mesh_file.parent.name),
                    "type": data.get("type", "unknown"),
                    "version": data.get("version", ""),
                    "path": str(mesh_file.parent),
                }
            )
        except Exception as exc:  # noqa: BLE001
            components.append(
                {
                    "component": mesh_file.parent.name,
                    "type": "unknown",
                    "version": "",
                    "path": str(mesh_file.parent),
                    "error": str(exc),
                }
            )

    if json_mode:
        print(
            json.dumps({"components": components, "count": len(components)}), flush=True
        )
    else:
        if not components:
            console.warning(f"No mesh.yaml files found under '{root}'.")
            return

        from rich.table import Table  # noqa: PLC0415

        table = Table(title="Mesh Components", show_header=True)
        table.add_column("Component", style="cyan")
        table.add_column("Type", style="magenta")
        table.add_column("Version")
        table.add_column("Path", style="dim")
        for c in components:
            table.add_row(c["component"], c["type"], c["version"], c["path"])
        console.render(table)


@mesh_app.command("run")
def mesh_run(
    component: str = typer.Argument(
        ..., help="Component name or path containing mesh.yaml."
    ),
    directory: Path = typer.Option(
        Path("."),
        "--dir",
        "-d",
        help="Base directory to search for the component.",
        exists=False,
        resolve_path=True,
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would run without executing."
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit JSON lines."),
) -> None:
    """Run a mesh component by name.

    Locates the component's mesh.yaml, detects its type, and executes it.

    Supported types
    ---------------
    * ``job-wheel``          — runs the installed wheel entry-point
    * ``docker-compose-app`` — runs ``docker compose up`` in the component dir

    Examples
    --------
    aptdata mesh run my_job
    aptdata mesh run my_app --dry-run
    """
    console = SmartConsole(json_mode=json_mode)
    root = directory.resolve()

    mesh_file = _resolve_mesh_file(root, component)

    if mesh_file is None:
        msg = f"Component '{component}' not found. No mesh.yaml located under '{root}'."
        if json_mode:
            print(
                json.dumps(
                    {"event": "mesh.error", "component": component, "error": msg}
                ),
                flush=True,
            )
        else:
            console.error(msg)
        raise typer.Exit(1)

    config = _load_mesh(mesh_file)
    comp_type = config.get("type", "unknown")
    comp_dir = mesh_file.parent

    if json_mode:
        print(
            json.dumps(
                {
                    "event": "mesh.run.started",
                    "component": component,
                    "type": comp_type,
                    "dry_run": dry_run,
                }
            ),
            flush=True,
        )
    else:
        console.info(f"Running component [bold cyan]{component}[/] (type: {comp_type})")

    if dry_run:
        _show_dry_run(component, comp_type, comp_dir, config, json_mode, console)
        return

    try:
        if comp_type == "job-wheel":
            _run_job_wheel(component, comp_dir, config)
        elif comp_type == "docker-compose-app":
            _run_docker_compose(component, comp_dir, config)
        else:
            raise ValueError(f"Unsupported component type '{comp_type}'.")
    except Exception as exc:  # noqa: BLE001
        if json_mode:
            print(
                json.dumps(
                    {
                        "event": "mesh.run.error",
                        "component": component,
                        "error": str(exc),
                    }
                ),
                flush=True,
            )
        else:
            console.error(f"Failed to run '{component}': {exc}")
        raise typer.Exit(1) from exc

    if json_mode:
        print(
            json.dumps(
                {
                    "event": "mesh.run.completed",
                    "component": component,
                    "type": comp_type,
                }
            ),
            flush=True,
        )
    else:
        console.success(f"Component [bold cyan]{component}[/] finished successfully.")


@mesh_app.command("build")
def mesh_build(
    component: str = typer.Argument(
        ..., help="Component name or path containing mesh.yaml."
    ),
    directory: Path = typer.Option(
        Path("."),
        "--dir",
        "-d",
        help="Base directory to search for the component.",
        exists=False,
        resolve_path=True,
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit JSON lines."),
) -> None:
    """Build a mesh component.

    Supported types
    ---------------
    * ``job-wheel``          — builds the Python wheel (``pip wheel .``)
    * ``docker-compose-app`` — builds Docker images (``docker compose build``)

    Examples
    --------
    aptdata mesh build my_job
    aptdata mesh build my_app --json
    """
    console = SmartConsole(json_mode=json_mode)
    root = directory.resolve()

    mesh_file = _resolve_mesh_file(root, component)

    if mesh_file is None:
        msg = f"Component '{component}' not found. No mesh.yaml located under '{root}'."
        if json_mode:
            print(
                json.dumps(
                    {"event": "mesh.error", "component": component, "error": msg}
                ),
                flush=True,
            )
        else:
            console.error(msg)
        raise typer.Exit(1)

    config = _load_mesh(mesh_file)
    comp_type = config.get("type", "unknown")
    comp_dir = mesh_file.parent

    if json_mode:
        print(
            json.dumps(
                {
                    "event": "mesh.build.started",
                    "component": component,
                    "type": comp_type,
                }
            ),
            flush=True,
        )
    else:
        console.info(
            f"Building component [bold cyan]{component}[/] (type: {comp_type})"
        )

    try:
        if comp_type == "job-wheel":
            _build_job_wheel(component, comp_dir)
        elif comp_type == "docker-compose-app":
            _build_docker_compose(component, comp_dir)
        else:
            raise ValueError(f"Unsupported component type '{comp_type}'.")
    except Exception as exc:  # noqa: BLE001
        if json_mode:
            print(
                json.dumps(
                    {
                        "event": "mesh.build.error",
                        "component": component,
                        "error": str(exc),
                    }
                ),
                flush=True,
            )
        else:
            console.error(f"Failed to build '{component}': {exc}")
        raise typer.Exit(1) from exc

    if json_mode:
        print(
            json.dumps(
                {
                    "event": "mesh.build.completed",
                    "component": component,
                    "type": comp_type,
                }
            ),
            flush=True,
        )
    else:
        console.success(f"Component [bold cyan]{component}[/] built successfully.")


@mesh_app.command("lint")
def mesh_lint(
    deep: bool = typer.Option(False, "--deep", help="Run deep architectural analysis."),
    json_mode: bool = typer.Option(False, "--json", help="Emit JSON lines."),
    changed_files: str = typer.Option(
        None, "--changed-files", help="Comma-separated list of changed files."
    ),
) -> None:
    """Run QAAgent to review code standardization and detect bugs."""
    console = SmartConsole(json_mode=json_mode)
    if not json_mode:
        console.info("Starting QA/DX code hygiene checks...")

    agent = QAAgent()

    files_to_check = changed_files.split(",") if changed_files else None
    findings = agent.run_all_checks(changed_files=files_to_check)

    if json_mode:
        agent.emit_json_lines()
    else:
        for f in findings:
            msg = (
                f"[{f.get('tool', 'unknown')}] {f.get('file', '')}:"
                f"{f.get('line', '')} - {f.get('message', '')}"
            )
            if f.get("severity") == "critical":
                console.error(msg)
            elif f.get("severity") == "warning":
                console.warning(msg)
            else:
                console.info(msg)

        if not findings:
            console.success("No code hygiene issues found!")

    criticals = [f for f in findings if f.get("severity") == "critical"]
    if criticals:
        raise typer.Exit(1)


@mesh_app.command("clean")
def mesh_clean(
    deep: bool = typer.Option(False, "--deep", help="Run deep architectural analysis."),
    json_mode: bool = typer.Option(False, "--json", help="Emit JSON lines."),
    changed_files: str = typer.Option(
        None, "--changed-files", help="Comma-separated list of changed files."
    ),
) -> None:
    """Run QAAgent to review code standardization and detect bugs (alias for lint)."""
    mesh_lint(deep=deep, json_mode=json_mode, changed_files=changed_files)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _show_dry_run(
    component: str,
    comp_type: str,
    comp_dir: Path,
    config: dict,
    json_mode: bool,
    console: SmartConsole,
) -> None:
    if comp_type == "job-wheel":
        entrypoint = config.get("run", {}).get("entrypoint", component)
        cmd = [entrypoint] + config.get("run", {}).get("args", [])
    elif comp_type == "docker-compose-app":
        cmd = ["docker", "compose", "up"]
    else:
        cmd = ["<unknown>"]

    if json_mode:
        print(
            json.dumps(
                {
                    "event": "mesh.run.dry_run",
                    "component": component,
                    "type": comp_type,
                    "command": cmd,
                }
            ),
            flush=True,
        )
    else:
        console.info(f"[dry-run] Would execute: {' '.join(cmd)} in {comp_dir}")


def _run_job_wheel(component: str, comp_dir: Path, config: dict) -> None:
    run_cfg = config.get("run", {})
    if isinstance(run_cfg, dict):
        entrypoint = run_cfg.get("entrypoint", f"{component}-job")
        args = run_cfg.get("args", [])
    else:
        entrypoint = f"{component}-job"
        args = []
    cmd = [entrypoint, *args]
    result = subprocess.run(cmd, cwd=comp_dir, check=False)  # noqa: S603
    if result.returncode != 0:
        raise RuntimeError(f"Job '{component}' exited with code {result.returncode}.")


def _run_docker_compose(component: str, comp_dir: Path, config: dict) -> None:
    cmd = ["docker", "compose", "up"]
    result = subprocess.run(cmd, cwd=comp_dir, check=False)  # noqa: S603
    if result.returncode != 0:
        raise RuntimeError(
            f"Docker Compose app '{component}' exited with code {result.returncode}."
        )


def _build_job_wheel(component: str, comp_dir: Path) -> None:
    cmd = ["pip", "wheel", ".", "-w", "dist/", "--no-deps"]
    result = subprocess.run(cmd, cwd=comp_dir, check=False)  # noqa: S603
    if result.returncode != 0:
        raise RuntimeError(
            f"Wheel build for '{component}' failed with code {result.returncode}."
        )


def _build_docker_compose(component: str, comp_dir: Path) -> None:
    cmd = ["docker", "compose", "build"]
    result = subprocess.run(cmd, cwd=comp_dir, check=False)  # noqa: S603
    if result.returncode != 0:
        raise RuntimeError(
            f"Docker Compose build for '{component}' failed"
            f" with code {result.returncode}."
        )
