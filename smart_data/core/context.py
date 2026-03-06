"""Execution session context dataclasses."""

from __future__ import annotations

import time
from dataclasses import field
from pathlib import Path

from pydantic.dataclasses import dataclass as pydantic_dataclass


@pydantic_dataclass
class EnvironmentConfig:
    """Environment settings loaded from ``.env`` files."""

    target: str = "dev"
    env_file: str = ".env"
    variables: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env_file(cls, *, target: str, env_file: str = ".env") -> "EnvironmentConfig":
        """Load key/value variables from *env_file* into a dataclass instance."""
        variables: dict[str, str] = {}
        path = Path(env_file)
        if path.exists():
            for raw_line in path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if not key:
                    continue
                clean_value = value.strip()
                if (
                    len(clean_value) >= 2
                    and clean_value[0] in {"'", '"'}
                    and clean_value[-1] == clean_value[0]
                ):
                    clean_value = clean_value[1:-1]
                variables[key] = clean_value
        return cls(target=target, env_file=env_file, variables=variables)


@pydantic_dataclass
class ExecutionSessionContext:
    """Execution-scoped context shared across pipeline tasks."""

    environment: EnvironmentConfig
    dry_run: bool = False
    verbosity: int = 0
    started_at: float = field(default_factory=time.time)

    @property
    def elapsed_seconds(self) -> float:
        """Return elapsed session time in seconds."""
        return round(time.time() - self.started_at, 3)

    def summary(self) -> dict[str, int | str]:
        """Return concise session metadata for CLI output."""
        return {
            "target_env": self.environment.target,
            "env_file": self.environment.env_file,
            "env_vars_loaded": len(self.environment.variables),
            "verbosity": self.verbosity,
        }
