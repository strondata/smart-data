"""Tests for the CLI (smart_data.cli.app)."""

from __future__ import annotations

import json

from pydantic.dataclasses import dataclass as pydantic_dataclass
from typer.testing import CliRunner

from smart_data.cli.app import app
from smart_data.core.dataset import BaseDataset
from smart_data.core.pipeline import BasePipeline
from smart_data.core.step import BaseStep
from smart_data.plugins import registry


runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers – minimal pipeline registered for CLI tests
# ---------------------------------------------------------------------------


@pydantic_dataclass
class _MockDataset(BaseDataset):
    def read(self):
        return []

    def write(self, data):
        pass


@pydantic_dataclass
class _MockStep(BaseStep):
    def validate_inputs(self, inputs):
        return True

    def execute(self, inputs):
        return _MockDataset(uri="memory://out")


@pydantic_dataclass
class _MockPipeline(BasePipeline):
    def __post_init__(self) -> None:
        self._compiled = False

    def register_step(self, step):
        pass

    def compile_dag(self):
        self._compiled = True

    def run(self):
        pass  # no-op for tests


# Register at module level so tests share it
registry.register("mock_pipeline", _MockPipeline)


# ---------------------------------------------------------------------------
# `smart-data run` tests
# ---------------------------------------------------------------------------


class TestRunCommand:
    def test_help(self):
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "pipeline" in result.output.lower()

    def test_run_known_pipeline_exits_0(self):
        result = runner.invoke(app, ["run", "mock_pipeline"])
        assert result.exit_code == 0
        # stdout should contain two JSON events
        lines = [line for line in result.output.strip().splitlines() if line.strip()]
        assert len(lines) >= 2
        started = json.loads(lines[0])
        completed = json.loads(lines[-1])
        assert started["event"] == "pipeline.started"
        assert completed["event"] == "pipeline.completed"

    def test_run_with_env_option(self):
        result = runner.invoke(app, ["run", "mock_pipeline", "--env", "prod"])
        assert result.exit_code == 0
        lines = [line for line in result.output.strip().splitlines() if line.strip()]
        started = json.loads(lines[0])
        assert started["env"] == "prod"

    def test_run_dry_run_flag(self):
        result = runner.invoke(app, ["run", "mock_pipeline", "--dry-run"])
        assert result.exit_code == 0
        lines = [line for line in result.output.strip().splitlines() if line.strip()]
        started = json.loads(lines[0])
        assert started["dry_run"] is True

    def test_run_builds_context_from_env_file(self, tmp_path):
        captured: dict[str, object] = {}

        @pydantic_dataclass
        class _ContextAwarePipeline(BasePipeline):
            def __post_init__(self) -> None:
                self._compiled = False
                captured["context"] = self.context

            def register_step(self, step):
                pass

            def compile_dag(self):
                self._compiled = True

            def run(self):
                pass

        registry.register("context_pipeline", _ContextAwarePipeline)
        env_file = tmp_path / ".env"
        env_file.write_text("API_TOKEN=abc123\n# ignore line\n", encoding="utf-8")

        result = runner.invoke(
            app,
            [
                "run",
                "context_pipeline",
                "--env",
                "prod",
                "--env-file",
                str(env_file),
                "-v",
            ],
        )

        assert result.exit_code == 0
        lines = [line for line in result.output.strip().splitlines() if line.strip()]
        started = json.loads(lines[0])
        assert started["session"]["target_env"] == "prod"
        assert started["session"]["env_vars_loaded"] == 1
        assert started["session"]["verbosity"] == 1
        assert "context" in captured
        context = captured["context"]
        assert context is not None
        assert context.environment.variables["API_TOKEN"] == "abc123"

    def test_run_unknown_pipeline_exits_1(self):
        result = runner.invoke(app, ["run", "nonexistent_pipeline"])
        assert result.exit_code == 1

    def test_run_unknown_pipeline_emits_error_json(self):
        result = runner.invoke(app, ["run", "nonexistent_pipeline"])
        # stderr and stdout are merged by the test runner
        lines = [line for line in result.output.strip().splitlines() if line.strip()]
        assert len(lines) >= 1
        error_event = json.loads(lines[-1])
        assert error_event["event"] == "pipeline.error"
        assert "nonexistent_pipeline" in error_event["error"]


# ---------------------------------------------------------------------------
# Plugin registry tests
# ---------------------------------------------------------------------------


class TestPluginRegistry:
    def test_register_and_get(self):
        from smart_data.plugins import _PipelineRegistry

        reg = _PipelineRegistry()
        reg.register("p1", _MockPipeline)
        assert reg.get("p1") is _MockPipeline

    def test_get_missing_returns_none(self):
        from smart_data.plugins import _PipelineRegistry

        reg = _PipelineRegistry()
        assert reg.get("missing") is None

    def test_list_pipelines(self):
        from smart_data.plugins import _PipelineRegistry

        reg = _PipelineRegistry()
        reg.register("b", _MockPipeline)
        reg.register("a", _MockPipeline)
        assert reg.list_pipelines() == ["a", "b"]


class TestScaffoldCommand:
    def test_scaffold_creates_hello_world_project(self, tmp_path):
        project_name = "selecao_demo"
        result = runner.invoke(
            app, ["scaffold", project_name, "--output", str(tmp_path)]
        )

        assert result.exit_code == 0
        lines = [line for line in result.output.strip().splitlines() if line.strip()]
        assert len(lines) >= 2
        assert json.loads(lines[0])["event"] == "scaffold.started"
        completed_event = json.loads(lines[-1])
        assert completed_event["event"] == "scaffold.completed"

        project_dir = tmp_path / project_name
        assert (project_dir / "main.py").exists()
        assert (project_dir / "requirements.txt").exists()
        assert (project_dir / "data" / "selecao_brasileira.json").exists()
        assert (project_dir / "output").exists()

    def test_scaffold_rejects_invalid_project_name(self):
        result = runner.invoke(app, ["scaffold", "123-invalid"])
        assert result.exit_code == 1
        lines = [line for line in result.output.strip().splitlines() if line.strip()]
        assert json.loads(lines[-1])["event"] == "scaffold.error"

    def test_scaffold_fails_if_directory_exists(self, tmp_path):
        project_dir = tmp_path / "existing_project"
        project_dir.mkdir()

        result = runner.invoke(
            app, ["scaffold", "existing_project", "--output", str(tmp_path)]
        )
        assert result.exit_code == 1
        lines = [line for line in result.output.strip().splitlines() if line.strip()]
        assert json.loads(lines[-1])["event"] == "scaffold.error"
