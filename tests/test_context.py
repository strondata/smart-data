"""Tests for execution session context dataclasses."""

from smart_data.core.context import EnvironmentConfig, ExecutionSessionContext


class TestEnvironmentConfig:
    def test_from_env_file_loads_variables(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "API_HOST=https://api.example.com\nTOKEN='secret'\n#comment\nINVALID\n",
            encoding="utf-8",
        )

        config = EnvironmentConfig.from_env_file(target="prod", env_file=str(env_file))

        assert config.target == "prod"
        assert config.variables["API_HOST"] == "https://api.example.com"
        assert config.variables["TOKEN"] == "secret"
        assert "INVALID" not in config.variables

    def test_from_env_file_missing_file_returns_empty_variables(self, tmp_path):
        config = EnvironmentConfig.from_env_file(
            target="dev",
            env_file=str(tmp_path / "missing.env"),
        )
        assert config.variables == {}


class TestExecutionSessionContext:
    def test_summary_is_concise_and_includes_runtime_metadata(self):
        context = ExecutionSessionContext(
            environment=EnvironmentConfig(
                target="staging",
                env_file=".env.staging",
                variables={"A": "1", "B": "2"},
            ),
            dry_run=True,
            verbosity=2,
        )

        summary = context.summary()

        assert summary["target_env"] == "staging"
        assert summary["env_file"] == ".env.staging"
        assert summary["env_vars_loaded"] == 2
        assert summary["verbosity"] == 2
