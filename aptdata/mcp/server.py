"""FastMCP server exposing aptdata tools and resources.

The server allows AI agents (Claude Desktop, Copilot, Devin, …) to discover
and execute aptdata pipelines via the Model Context Protocol.
"""

from __future__ import annotations

import time
from threading import Lock
from typing import Any

from aptdata.core.lineage import (
    LineageEventType,
    LineageGraph,
    LineageNode,
)
from aptdata.plugins import registry
from aptdata.plugins.governance.rules import BusinessRule, RuleRegistry
from aptdata.plugins.local_fs import (
    CSVReader,
    CSVWriter,
    JSONReader,
    JSONWriter,
    ParquetReader,
    ParquetWriter,
)
from aptdata.plugins.manager import plugin_manager
from aptdata.plugins.postgres import PostgresReader, PostgresWriter
from aptdata.plugins.quality.report import (
    CheckResult,
    CheckStatus,
    QualityReport,
)
from aptdata.plugins.rest import APIReader
from aptdata.plugins.vector import QdrantWriter
from aptdata.qa.agent import QAAgent
from aptdata.telemetry.instrumentation import mask_telemetry_value

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
    """Execute a registered flow/system and return its status."""
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
    """Return the names of all systems available in the plugin registry."""
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
    """Return metadata for a dataset registered under *dataset_name*."""
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
    from dataclasses import asdict

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
    return json.dumps(asdict(report))


@mcp.resource("governance://rules")
def list_business_rules() -> str:
    """Allow the AI to learn about registered business rules."""
    import json

    registry = RuleRegistry()
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

    graph = LineageGraph(run_id="mock-run-1", workflow_name=flow_id)
    node = LineageNode(
        dataset_uri="mock://dataset",
        event_type=LineageEventType.READ,
        workflow_name=flow_id,
    )
    graph.add_node(node)

    return graph.to_dict()


@mcp.tool()
def run_code_hygiene(changed_files: str | None = None) -> list[dict]:
    """Run QAAgent code hygiene checks via MCP.

    Args:
        changed_files: Comma-separated list of changed files to analyze.
    """
    agent = QAAgent()
    files = changed_files.split(",") if changed_files else None
    findings = agent.run_all_checks(changed_files=files)
    return findings
