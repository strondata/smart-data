# smart-data

> **v0.0.1** · A declarative, extensible framework for building smart data pipelines in Python.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.0.1-orange)](CHANGELOG.md)

---

## Overview

**smart-data** provides a clean, two-layer contract system that separates
*what* a component must do (interfaces) from *what fields* it carries (base
classes):

```
IDataset / IStep / IPipeline       ← @dataclass + ABC  (pure interfaces)
         ↓
BaseDataset / BaseStep / BasePipeline  ← @pydantic_dataclass  (validated fields)
         ↓
Your concrete implementations
```

Every outcome from the CLI is emitted as a machine-readable JSON line, making
smart-data a natural fit for AI orchestrators, CI/CD pipelines and scripted
workflows.

---

## Requirements

- Python ≥ 3.10
- [Poetry](https://python-poetry.org/) (for development)

---

## Installation

```bash
git clone https://github.com/strondata/smart-data.git
cd smart-data
poetry install
```

---

## Quick start

```python
from pydantic.dataclasses import dataclass as pydantic_dataclass
from smart_data.core import BaseDataset, BaseStep, BasePipeline, IDataset, IStep

@pydantic_dataclass
class MemoryDataset(BaseDataset):
    def __post_init__(self): self._data = None
    def read(self): return self._data
    def write(self, data): self._data = data

@pydantic_dataclass
class DoubleStep(BaseStep):
    def validate_inputs(self, inputs: list[IDataset]) -> bool:
        return len(inputs) == 1
    def execute(self, inputs: list[IDataset]) -> IDataset:
        out = MemoryDataset(uri="memory://out")
        out.write([x * 2 for x in inputs[0].read()])
        return out

@pydantic_dataclass
class MyPipeline(BasePipeline):
    def __post_init__(self): self._steps: list[IStep] = []
    def register_step(self, step: IStep): self._steps.append(step)
    def compile_dag(self): pass
    def run(self):
        ds = MemoryDataset(uri="memory://in")
        ds.write([1, 2, 3])
        inputs = [ds]
        for step in self._steps:
            if step.validate_inputs(inputs):
                inputs = [step.execute(inputs)]

# Register and run via CLI
from smart_data.plugins import registry
registry.register("my_pipeline", MyPipeline)
```

```bash
smart-data run my_pipeline
# {"event": "pipeline.started", "pipeline": "my_pipeline", "env": "dev", "dry_run": false}
# {"event": "pipeline.completed", "pipeline": "my_pipeline", "env": "dev", "dry_run": false, "elapsed_seconds": 0.001}
```

---

## CLI reference

```
smart-data run PIPELINE [--env ENV] [--env-file PATH] [-v ...] [--dry-run]
smart-data monitor [--refresh SECONDS]
smart-data scaffold PROJECT_NAME [--output PATH]
```

---

## Development

```bash
make install   # install all dependencies
make test      # run the test suite
make lint      # lint with ruff
make docs      # build the documentation
```

---

## Documentation

Full documentation is available in the [`docs/`](docs/) directory and can be
served locally with:

```bash
mkdocs serve
```

---

## License

[MIT](LICENSE)
