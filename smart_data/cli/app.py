"""Typer-based static CLI for smart-data.

Design goals
------------
* Machine / AI-readable: every outcome is emitted as a single JSON line on
  stdout (success) or stderr (error).
* Exit codes: 0 = success, 1 = error.
* Self-documenting: Typer generates --help automatically from the docstrings
  and type annotations.
"""

from __future__ import annotations

import json
import inspect
import sys

import typer

from smart_data.cli.scaffold import scaffold
from smart_data.core.context import EnvironmentConfig, ExecutionSessionContext

app = typer.Typer(
    name="smart-data",
    help="Smart Data – declarative data-pipeline framework.",
    add_completion=False,
)


def _emit(payload: dict, *, error: bool = False) -> None:
    """Emit *payload* as a single JSON line to stdout or stderr."""
    line = json.dumps(payload, default=str)
    if error:
        print(line, file=sys.stderr, flush=True)
    else:
        print(line, flush=True)


@app.command()
def run(
    pipeline: str = typer.Argument(..., help="Pipeline name / identifier to run."),
    env: str = typer.Option("dev", "--env", "-e", help="Target execution environment."),
    env_file: str = typer.Option(
        ".env",
        "--env-file",
        help="Environment file used to build the execution context.",
    ),
    verbose: int = typer.Option(
        0,
        "--verbose",
        "-v",
        count=True,
        help="Increase CLI context verbosity level.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Validate and compile the pipeline without executing it.",
    ),
) -> None:
    """Run a registered data pipeline.

    Emits structured JSON logs and returns exit code 0 on success or 1 on
    failure so that orchestrators and AI agents can parse the outcome.

    Examples
    --------
    smart-data run pipeline_x --env prod
    smart-data run pipeline_x --env staging --dry-run
    """
    context = ExecutionSessionContext(
        environment=EnvironmentConfig.from_env_file(target=env, env_file=env_file),
        dry_run=dry_run,
        verbosity=verbose,
    )
    _emit(
        {
            "event": "pipeline.started",
            "pipeline": pipeline,
            "env": env,
            "dry_run": dry_run,
            "session": context.summary(),
        }
    )

    try:
        # Plugin registry look-up (stub – real implementations are in plugins/)
        from smart_data.plugins import registry  # noqa: PLC0415

        pipeline_cls = registry.get(pipeline)
        if pipeline_cls is None:
            raise LookupError(f"Pipeline '{pipeline}' not found in registry.")

        try:
            pipeline_signature = inspect.signature(pipeline_cls)
            accepts_context = "context" in pipeline_signature.parameters
        except (TypeError, ValueError):
            accepts_context = False

        instance = pipeline_cls(context=context) if accepts_context else pipeline_cls()
        if not accepts_context and hasattr(instance, "context"):
            instance.context = context
        instance.compile_dag()

        if not dry_run:
            instance.run()

        elapsed = context.elapsed_seconds
        _emit(
            {
                "event": "pipeline.completed",
                "pipeline": pipeline,
                "env": env,
                "dry_run": dry_run,
                "elapsed_seconds": elapsed,
                "session": context.summary(),
            }
        )
        raise SystemExit(0)

    except LookupError as exc:
        elapsed = context.elapsed_seconds
        _emit(
            {
                "event": "pipeline.error",
                "pipeline": pipeline,
                "env": env,
                "error": str(exc),
                "elapsed_seconds": elapsed,
            },
            error=True,
        )
        raise SystemExit(1) from exc

    except Exception as exc:  # noqa: BLE001
        elapsed = context.elapsed_seconds
        _emit(
            {
                "event": "pipeline.error",
                "pipeline": pipeline,
                "env": env,
                "error": str(exc),
                "elapsed_seconds": elapsed,
            },
            error=True,
        )
        raise SystemExit(1) from exc


@app.command()
def monitor(
    refresh: float = typer.Option(
        1.0,
        "--refresh",
        "-r",
        help="Dashboard refresh interval in seconds.",
    ),
) -> None:
    """Open the interactive TUI monitoring dashboard.

    Displays the pipeline DAG, memory usage and task status in real time.
    Press **q** or **Ctrl+C** to exit.

    Examples
    --------
    smart-data monitor
    smart-data monitor --refresh 0.5
    """
    from smart_data.tui.monitor import MonitorApp  # noqa: PLC0415

    app_instance = MonitorApp(refresh_interval=refresh)
    app_instance.run()


app.command()(scaffold)
