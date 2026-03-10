"""CLI sub-commands for YAML configuration management."""

from __future__ import annotations

from pathlib import Path

import typer

from aptdata.cli.rendering.console import SmartConsole
from aptdata.cli.rendering.panels import yaml_preview
from aptdata.cli.rendering.tables import config_summary_table

config_app = typer.Typer(name="config", help="Manage declarative YAML configurations.")

_STARTER_YAML = """\
# aptdata declarative pipeline configuration
metadata:
  name: my_pipeline
  version: "1.0"
  description: A sample pipeline

system:
  system_id: my_pipeline
  flows:
    - flow_id: main_flow
      components:
        - component_id: extract
          metadata:
            kind: extract
            description: Extract raw data
        - component_id: transform
          metadata:
            kind: transform
            description: Transform data
        - component_id: load
          metadata:
            kind: load
            description: Load to destination
      edges:
        - source_id: extract
          target_id: transform
        - source_id: transform
          target_id: load
"""


@config_app.command("validate")
def config_validate(
    path: Path = typer.Argument(..., help="Path to YAML config file.", exists=True),
) -> None:
    """Parse and validate a YAML config file."""
    from aptdata.config.parser import YamlConfigParser  # noqa: PLC0415

    console = SmartConsole(json_mode=False)

    try:
        with console.spinner(f"Validating '{path}'..."):
            parser = YamlConfigParser()
            parsed = parser.parse_file(path)
        console.success(f"Config valid: system_id='{parsed.system.system_id}'")
    except Exception as exc:  # noqa: BLE001
        console.error(f"Validation failed: {exc}")
        raise typer.Exit(1) from exc


@config_app.command("init")
def config_init(
    output: Path = typer.Option(
        Path("pipeline.yaml"),
        "--output",
        "-o",
        help="Output file path.",
    ),
    template: bool = typer.Option(
        False, "--template", help="Use the starter template."
    ),
) -> None:
    """Generate a starter YAML configuration file."""
    console = SmartConsole(json_mode=False)

    if output.exists():
        console.error(f"File '{output}' already exists.")
        raise typer.Exit(1)

    output.write_text(_STARTER_YAML, encoding="utf-8")
    console.success(f"Config template written to '{output}'.")
    console.render(yaml_preview(_STARTER_YAML))


@config_app.command("show")
def config_show(
    path: Path = typer.Argument(..., help="Path to YAML config file.", exists=True),
) -> None:
    """Pretty-print a YAML config file with syntax highlighting."""
    console = SmartConsole(json_mode=False)
    content = path.read_text(encoding="utf-8")
    console.render(yaml_preview(content))


@config_app.command("run")
def config_run(
    path: Path = typer.Argument(..., help="Path to YAML config file.", exists=True),
    env: str = typer.Option("dev", "--env", "-e", help="Target environment."),
) -> None:
    """Parse a YAML config, register the system, and execute it."""
    from aptdata.config.parser import YamlConfigParser  # noqa: PLC0415
    from aptdata.plugins import registry  # noqa: PLC0415

    console = SmartConsole(json_mode=False)

    try:
        with console.spinner(f"Parsing '{path}'..."):
            parser = YamlConfigParser()
            parsed = parser.parse_file(path)

        system_id = parsed.system.system_id
        system_cls = type(parsed.system)
        registry.register(system_id, system_cls)

        console.render(config_summary_table(parsed))

        with console.spinner(f"Running '{system_id}' [{env}]..."):
            parsed.system.run()

        console.success(f"System '{system_id}' executed successfully.")
    except Exception as exc:  # noqa: BLE001
        console.error(f"Execution failed: {exc}")
        raise typer.Exit(1) from exc
