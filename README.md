# aptdata

> **v0.0.2** · A declarative, extensible framework for building smart data pipelines in Python.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.0.2-orange)](CHANGELOG.md)

---

## Overview

**aptdata** is built around three universal abstractions — **System**,
**Flow**, and **Component** — that cover every data-processing paradigm in a
single, coherent model:

```mermaid
flowchart TD
    classDef default fill:rgba(255,255,255,0.02),stroke:#ff6a00,stroke-width:1px,color:inherit,rx:8px,ry:8px;
    I["IComponent / IFlow / ISystem\n@dataclass + ABC — pure interfaces"]
    B["BaseComponent / BaseFlow / BaseSystem\n@pydantic_dataclass — validated fields"]
    Y["Your concrete implementations"]

    I --> B --> Y
```

Datasets remain the fundamental data-exchange contract (`IDataset` /
`BaseDataset`).  Every outcome from the CLI is emitted as a machine-readable
JSON line, making aptdata a natural fit for AI orchestrators, CI/CD
pipelines and scripted workflows.

---

## Requirements

- Python ≥ 3.10
- [Poetry](https://python-poetry.org/) (for development)

---

## Installation

### From PyPI

```bash
pip install aptdata
```

### Optional extras

```bash
pip install aptdata[pandas]   # pandas support
pip install aptdata[spark]    # PySpark support
pip install aptdata[plugins]  # REST, PostgreSQL, Parquet I/O
pip install aptdata[ai]       # MCP server for AI agents
pip install aptdata[all]      # everything
```

### From source (development)

```bash
git clone https://github.com/strondata/smart-data.git
cd aptdata
poetry install
```

---

## Quick start

```python
from pydantic.dataclasses import dataclass as pydantic_dataclass
from aptdata.core import (
    BaseDataset, IDataset,
    BaseComponent, ComponentMeta, ComponentKind,
    BaseFlow, IFlow,
    BaseSystem,
)

@pydantic_dataclass
class MemoryDataset(BaseDataset):
    def __post_init__(self): self._data = None
    def read(self): return self._data
    def write(self, data): self._data = data

@pydantic_dataclass
class DoubleComponent(BaseComponent):
    def validate_inputs(self, inputs: list[IDataset]) -> bool:
        return len(inputs) == 1
    def execute(self, inputs: list[IDataset]) -> list[IDataset]:
        out = MemoryDataset(uri="memory://out")
        out.write([x * 2 for x in inputs[0].read()])
        return [out]

@pydantic_dataclass
class ETLFlow(BaseFlow):
    def __post_init__(self):
        self._nodes = {}
        self._edges = []
        self._compiled = False
    def add_component(self, c): self._nodes[c.component_id] = c
    def connect(self, src, tgt, condition=None): ...
    def compile(self): self._compiled = True
    def run(self, inputs): return inputs  # wire your logic here

@pydantic_dataclass
class MySystem(BaseSystem):
    def __post_init__(self): self._flows: list[IFlow] = []
    def register_flow(self, flow): self._flows.append(flow)
    def run(self):
        for flow in self._flows:
            flow.run([])

# Register and run via CLI
from aptdata.plugins import registry
registry.register("my_system", MySystem)
```

```bash
aptdata run my_system
# {"event": "pipeline.started", "pipeline": "my_system", "env": "dev", "dry_run": false, "trace_id": null}
# {"event": "pipeline.completed", "pipeline": "my_system", "env": "dev", "dry_run": false, "elapsed_seconds": 0.001, "trace_id": null}
```

---

## CLI reference

```
aptdata run SYSTEM_NAME [--env ENV] [--dry-run]
aptdata monitor [--refresh SECONDS]
aptdata scaffold PROJECT_NAME [--template TEMPLATE] [--output PATH]
aptdata schema export --output schema.json
aptdata system list [--json]
aptdata system info NAME [--json]
aptdata system validate NAME
aptdata plugin list [--json]
aptdata plugin inspect NAME [--json]
aptdata plugin preview READER [--limit N]
aptdata plugin load MODULE_PATH
aptdata config validate PATH
aptdata config init [--output PATH]
aptdata config show PATH
aptdata config run PATH [--env ENV]
aptdata telemetry status [--json]
aptdata telemetry export [--format json]
aptdata mesh list [--dir DIR] [--json]
aptdata mesh run COMPONENT [--dir DIR] [--dry-run] [--json]
aptdata mesh build COMPONENT [--dir DIR] [--json]
aptdata mcp-start [--transport TRANSPORT]
aptdata interactive
```

Every static command supports `--json` for machine-readable JSON line output
(backward compatible). Without `--json`, commands render Rich tables, panels,
and syntax-highlighted output.

### Scaffold templates

| Template              | Description                                         |
|-----------------------|-----------------------------------------------------|
| `hello-world`         | Minimal pandas pipeline (default)                   |
| `medallion`           | Bronze → Silver → Gold data lakehouse               |
| `rag-ingestion`       | RAG pipeline: extract → chunk → embed → load        |
| `data-quality-test`   | Schema contract + expectation suite                  |
| `job-wheel`           | Python wheel executor for portable job packaging     |
| `docker-compose-app`  | Multi-service Docker Compose application             |

```bash
aptdata scaffold my_lakehouse --template medallion
aptdata scaffold my_job --template job-wheel
aptdata scaffold my_service --template docker-compose-app
```

---

## Processing Engines

Engine-agnostic transformation wrappers for pandas and PySpark:

```python
from aptdata.plugins.transform import PandasTransformer

def clean(df):
    return df.dropna().drop_duplicates()

transformer = PandasTransformer("clean", clean)
result = transformer.transform(my_dataset)
```

See [Transform Engines docs](docs/transform-engines.md) for PySpark usage.

---

## Data Quality & Contracts

```python
from aptdata.plugins.quality import (
    EnforcementMode, ExpectColumnToNotBeNull,
    QualityValidator, SchemaContract,
)

validator = QualityValidator(
    expectations=[ExpectColumnToNotBeNull("id")],
    enforcement=EnforcementMode.ABORT,
)
clean_data = validator.validate(raw_df)
```

See [Quality docs](docs/quality.md) for all built-in expectations.

---

## Data Governance

```python
from aptdata.plugins.governance import (
    BusinessRule, DatasetCatalog, DatasetCatalogEntry, LineageStore,
)
from aptdata.core.lineage import LineageGraph, LineageNode, LineageEventType

# Lineage tracking
graph = LineageGraph(run_id="run-1", workflow_name="etl")
graph.add_node(LineageNode(dataset_uri="s3://raw/data", event_type=LineageEventType.READ))

store = LineageStore()
store.save(graph)
```

See [Governance docs](docs/governance.md) for the full API.

---

## AI Agents & MCP Server

aptdata ships with a built-in [Model Context Protocol](https://modelcontextprotocol.io/) server (`mcp-start`). This transforms AI assistants (like Claude, Copilot, or Devin) into autonomous data engineers with direct access to:

- **Pipeline Execution:** Trigger and monitor data flows (`run_flow`).
- **Data Quality:** Audit the latest quality test results (`quality://reports/...`).
- **Data Governance:** Read business rules to prevent violations (`governance://rules`).
- **Lineage:** Trace upstream dependencies and column-level provenance (`get_pipeline_lineage`).

```bash
aptdata mcp-start --transport stdio
```

See the [MCP Documentation](docs/mcp.md) for setup instructions.

---

## Release process

Releases are automated via the [Release workflow](.github/workflows/release.yml).
After a PR is merged into `main`, the CI reads its labels and bumps the version
accordingly.

| Label | Effect |
|---|---|
| `release:patch` | `0.0.1 → 0.0.2` |
| `release:minor` | `0.0.1 → 0.1.0` |
| `release:major` | `0.0.1 → 1.0.0` |
| `release:skip` | no release (explicit opt-out) |
| *(no label)* | no release (silent skip) |

The workflow will:
1. Detect the merged PR and its labels.
2. Run `bump-my-version bump <part>` to update `pyproject.toml` and
   `aptdata/__init__.py`.
3. Create a `chore(release): bump version to X.Y.Z` commit and a `vX.Y.Z` tag.
4. Push the commit and tag to `main`.
5. The tag push automatically triggers the **Publish to PyPI** workflow.

> **Branch protection note:** GitHub Actions must have *read and write
> permissions* (Settings → Actions → General → Workflow permissions) and, if
> branch protection is enabled on `main`, the rule must allow GitHub Actions
> to bypass it.

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
