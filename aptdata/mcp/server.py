"""FastMCP server exposing aptdata tools and resources.

The server allows AI agents (Claude Desktop, Copilot, Devin, …) to discover
and execute aptdata pipelines via the Model Context Protocol.
"""

from __future__ import annotations

import time
from threading import Lock
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP

    _MCP_AVAILABLE = True
except ImportError:
    FastMCP = None
    _MCP_AVAILABLE = False


class _MockMCP:
    """Fallback object for when MCP dependencies are missing."""

    def __init__(self, name: str) -> None:
        self.name = name

    def tool(self, *args: Any, **kwargs: Any) -> Any:
        def decorator(func: Any) -> Any:
            return func

        return decorator

    def resource(self, *args: Any, **kwargs: Any) -> Any:
        def decorator(func: Any) -> Any:
            return func

        return decorator

    def run(self, *args: Any, **kwargs: Any) -> None:
        raise ImportError(
            "The MCP server dependencies are not installed. "
            "Please run `pip install aptdata[ai]` to use mcp-start."
        )


from aptdata.core.lineage import (  # noqa: E402
    LineageEventType,
    LineageGraph,
    LineageNode,
)
from aptdata.plugins import registry  # noqa: E402
from aptdata.plugins.governance.rules import BusinessRule, RuleRegistry  # noqa: E402
from aptdata.plugins.local_fs import (  # noqa: E402
    CSVReader,
    CSVWriter,
    JSONReader,
    JSONWriter,
    ParquetReader,
    ParquetWriter,
)
from aptdata.plugins.manager import plugin_manager  # noqa: E402
from aptdata.plugins.postgres import PostgresReader, PostgresWriter  # noqa: E402
from aptdata.plugins.quality.report import (  # noqa: E402
    CheckResult,
    CheckStatus,
    QualityReport,
)
from aptdata.plugins.rest import APIReader  # noqa: E402
from aptdata.plugins.vector import QdrantWriter  # noqa: E402
from aptdata.telemetry.instrumentation import mask_telemetry_value  # noqa: E402

mcp = FastMCP("aptdata") if _MCP_AVAILABLE else _MockMCP("aptdata")
_MCP_REQUEST_COUNT = 0
_MCP_REQUEST_LOCK = Lock()


def _mark_request() -> None:
    global _MCP_REQUEST_COUNT
    with _MCP_REQUEST_LOCK:
        _MCP_REQUEST_COUNT += 1


def get_mcp_status() -> dict[str, Any]:
    """Return MCP activity status for TUI and diagnostics."""
    with _MCP_REQUEST_LOCK:
        request_count = _MCP_REQUEST_COUNT
    return {"active": True, "request_count": request_count}


def _register_builtin_plugins() -> None:
    plugin_manager.register_reader("csv_reader", CSVReader)
    plugin_manager.register_reader("json_reader", JSONReader)
    plugin_manager.register_reader("parquet_reader", ParquetReader)
    plugin_manager.register_reader("api_reader", APIReader)
    plugin_manager.register_reader("postgres_reader", PostgresReader)
    plugin_manager.register_writer("csv_writer", CSVWriter)
    plugin_manager.register_writer("json_writer", JSONWriter)
    plugin_manager.register_writer("parquet_writer", ParquetWriter)
    plugin_manager.register_writer("postgres_writer", PostgresWriter)
    plugin_manager.register_writer("qdrant_writer", QdrantWriter)


_register_builtin_plugins()


@mcp.tool()
def run_flow(flow_id: str) -> dict[str, Any]:
    """Execute a registered flow/system and return its status.

    Parameters
    ----------
    flow_id:
        The identifier of a system previously registered in the plugin
        registry (e.g. ``"pipeline_x"``).

    Returns
    -------
    dict
        A status dict with keys ``status``, ``flow_id``, and
        ``elapsed_seconds`` on success, or ``status`` and ``error`` on
        failure.
    """
    _mark_request()
    started_at = time.time()
    try:
        system_cls = registry.get(flow_id)
        if system_cls is None:
            return {
                "status": "error",
                "flow_id": flow_id,
                "error": f"Flow '{flow_id}' not found in registry.",
            }
        instance = system_cls(system_id=flow_id)
        instance.run()
        elapsed = round(time.time() - started_at, 3)
        return {
            "status": "completed",
            "flow_id": flow_id,
            "elapsed_seconds": elapsed,
        }
    except Exception as exc:  # noqa: BLE001
        elapsed = round(time.time() - started_at, 3)
        return {
            "status": "error",
            "flow_id": flow_id,
            "error": str(exc),
            "elapsed_seconds": elapsed,
        }


@mcp.tool()
def list_registered_systems() -> dict[str, Any]:
    """Return the names of all systems available in the plugin registry.

    Returns
    -------
    dict
        A dict with ``systems`` (list of names) and ``count``.
    """
    _mark_request()
    systems = registry.list_systems()
    return {"systems": systems, "count": len(systems)}


@mcp.tool()
def list_available_plugins() -> dict[str, Any]:
    """Return all installed plugins grouped by readers and writers."""
    _mark_request()
    plugins = plugin_manager.list_plugins()
    return {
        "plugins": plugins,
        "count": len(plugins["readers"]) + len(plugins["writers"]),
    }


@mcp.tool()
def get_plugin_schema(plugin_name: str) -> dict[str, Any]:
    """Return constructor argument schema for a specific plugin."""
    _mark_request()
    try:
        return plugin_manager.get_plugin_schema(plugin_name)
    except KeyError as exc:
        return {"status": "error", "error": str(exc), "plugin_name": plugin_name}


@mcp.tool()
def preview_dataset(plugin: str, **reader_config: Any) -> dict[str, Any]:
    """Execute a reader plugin and return the first five rows."""
    _mark_request()
    try:
        rows = plugin_manager.preview_dataset(plugin, **reader_config)
        return {
            "status": "ok",
            "plugin": plugin,
            "rows": mask_telemetry_value(rows),
            "format": "json",
        }
    except KeyError as exc:
        return {
            "status": "error",
            "plugin": plugin,
            "error": str(exc),
            "error_type": "KeyError",
        }
    except ValueError as exc:
        return {
            "status": "error",
            "plugin": plugin,
            "error": str(exc),
            "error_type": "ValueError",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "plugin": plugin,
            "error": str(exc),
            "error_type": type(exc).__name__,
        }


@mcp.resource("schema://datasets/{dataset_name}")
def get_dataset_schema(dataset_name: str) -> str:
    """Return metadata for a dataset registered under *dataset_name*.

    This is a placeholder resource – concrete implementations should query
    a dataset catalogue or registry.  For now it returns a JSON string
    describing the dataset name so that agents can discover schema
    information.
    """
    import json

    return json.dumps(
        {
            "dataset": dataset_name,
            "fields": [],
            "description": (
                f"Schema metadata for '{dataset_name}' (no catalogue loaded)."
            ),
        }
    )


@mcp.resource("quality://reports/{workflow_name}/latest")
def get_latest_quality_report(workflow_name: str) -> str:
    """Allow the AI to audit quality failures in the latest run."""
    import json

    # Placeholder logic to fetch the latest QualityReport JSON.
    # In a real scenario, this would query a QualityStore or an external catalog.
    report = QualityReport(
        dataset_uri="unknown",
        workflow_name=workflow_name,
        checks=[
            CheckResult(
                expectation_name="MockExpectation",
                status=CheckStatus.PASSED,
                message="This is a mock quality report.",
            )
        ],
    )
    # Using json.dumps on the summary for now, or building a dictionary.
    # QualityReport is a dataclass without a direct model_dump_json method.
    from dataclasses import asdict

    return json.dumps(asdict(report))


@mcp.resource("governance://rules")
def list_business_rules() -> str:
    """Allow the AI to learn about registered business rules."""
    import json

    registry = RuleRegistry()
    # Return the catalog of data rules for the AI to build pipelines without violations.
    # Here we return a mock rule for demonstration since registry is empty.
    registry.register(
        BusinessRule(
            rule_id="BR-MOCK-001",
            name="Mock Rule",
            description="A mock business rule for AI context.",
        )
    )

    rules = [
        {
            "rule_id": r.rule_id,
            "name": r.name,
            "description": r.description,
            "expression": r.expression,
        }
        for r in registry.list_rules()
    ]
    return json.dumps({"rules": rules})


@mcp.tool()
def get_pipeline_lineage(flow_id: str) -> dict[str, Any]:
    """Return the dependency tree (DAG) and column traceability (Lineage)."""
    _mark_request()

    # Query aptdata.core.lineage to understand how a column was generated.
    # Placeholder: return a dummy lineage graph for the requested flow_id.
    graph = LineageGraph(run_id="mock-run-1", workflow_name=flow_id)
    node = LineageNode(
        dataset_uri="mock://dataset",
        event_type=LineageEventType.READ,
        workflow_name=flow_id,
    )
    graph.add_node(node)

    return graph.to_dict()


@mcp.tool()
def run_code_hygiene() -> dict[str, Any]:
    """Run the QAAgent to clean dead code and fix formatting."""
    _mark_request()
    try:
        from aptdata.agents.qa import QAAgent
    except ImportError as exc:
        return {"status": "error", "error": "QAAgent could not be imported."}

    agent = QAAgent()
    try:
        report = agent.run(deep=True)
        return {
            "status": "success",
            "items_removed": report.items_removed,
            "semantic_deviations": report.semantic_deviations,
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}
