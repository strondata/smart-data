"""Workflow interface, node/edge dataclasses, and base implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from pydantic.dataclasses import dataclass as pydantic_dataclass

from smart_data.core.context import ExecutionSessionContext
from smart_data.core.step import IStep


@dataclass
class IWorkflow(ABC):
    """Dataclass interface for workflow orchestration.

    A workflow manages a directed acyclic graph (DAG) composed of
    :class:`WorkflowNode` objects (vertices) connected by
    :class:`WorkflowEdge` objects (arcs).  Concrete implementations must
    define how the graph is compiled and executed; the contract is agnostic
    to execution mode (batch, streaming, LLM, ML, …).
    """

    @abstractmethod
    def add_node(self, node: WorkflowNode) -> None:
        """Register *node* in the workflow graph."""

    @abstractmethod
    def add_edge(self, source_id: str, target_id: str) -> WorkflowEdge:
        """Create and register a directed edge from *source_id* to *target_id*."""

    @abstractmethod
    def compile(self) -> None:
        """Validate and compile the workflow graph before execution."""

    @abstractmethod
    def run(self) -> None:
        """Execute the compiled workflow."""


@dataclass
class WorkflowNode:
    """A vertex in the workflow DAG wrapping a single :class:`IStep` instance.

    After the node is added to a workflow via :meth:`IWorkflow.add_node` the
    :attr:`workflow` back-reference is populated so the full orchestration
    context is reachable from any node.
    """

    node_id: str
    step: IStep
    workflow: IWorkflow | None = field(default=None, repr=False)


@dataclass
class WorkflowEdge:
    """A directed arc connecting two :class:`WorkflowNode` objects.

    After the edge is created via :meth:`IWorkflow.add_edge` the
    :attr:`workflow` back-reference is populated so the full orchestration
    context is reachable from any edge.
    """

    source: WorkflowNode
    target: WorkflowNode
    workflow: IWorkflow | None = field(default=None, repr=False)


@pydantic_dataclass
class BaseWorkflow(IWorkflow):
    """Base workflow with built-in node/edge management and context support.

    Concrete workflow implementations should inherit from this class.  The
    default :meth:`compile` and :meth:`run` implementations provide a
    straightforward single-pass execution in node-registration order; override
    them for topological-sort execution, parallel dispatch, or other
    orchestration strategies.

    Lifecycle hooks :meth:`before_run` and :meth:`after_run` are no-ops by
    default and can be overridden to add monitoring, quality checks, or
    notifications without changing the core execution logic.
    """

    context: ExecutionSessionContext | None = None

    def __post_init__(self) -> None:
        self._nodes: dict[str, WorkflowNode] = {}
        self._edges: list[WorkflowEdge] = []
        self._compiled: bool = False

    # ------------------------------------------------------------------
    # IWorkflow implementation
    # ------------------------------------------------------------------

    def add_node(self, node: WorkflowNode) -> None:
        """Register *node* and set its :attr:`~WorkflowNode.workflow` back-reference."""
        node.workflow = self
        self._nodes[node.node_id] = node

    def add_edge(self, source_id: str, target_id: str) -> WorkflowEdge:
        """Create an edge between nodes *source_id* → *target_id* and register it."""
        if source_id not in self._nodes:
            raise KeyError(f"Source node '{source_id}' not found in workflow.")
        if target_id not in self._nodes:
            raise KeyError(f"Target node '{target_id}' not found in workflow.")
        edge = WorkflowEdge(
            source=self._nodes[source_id],
            target=self._nodes[target_id],
            workflow=self,
        )
        self._edges.append(edge)
        return edge

    def compile(self) -> None:
        """Validate and compile the workflow graph.

        Builds an adjacency list of incoming edges per node for efficient
        input resolution during :meth:`run`.
        """
        self._incoming: dict[str, list[WorkflowEdge]] = {
            node_id: [] for node_id in self._nodes
        }
        for edge in self._edges:
            self._incoming[edge.target.node_id].append(edge)
        self._compiled = True

    def run(self) -> None:
        """Execute workflow nodes in registration order.

        Outputs produced by each node are made available as inputs to
        downstream nodes connected by edges.  Root nodes (no incoming edges)
        receive an empty input list.

        Raises
        ------
        RuntimeError
            If the workflow has not been compiled or if a node's
            :meth:`~smart_data.core.step.IStep.validate_inputs` check fails.
        """
        if not self._compiled:
            raise RuntimeError("Workflow not compiled.")
        self.before_run()
        dataset_map: dict[str, Any] = {}
        for node in self._nodes.values():
            node_inputs = [
                dataset_map[e.source.node_id]
                for e in self._incoming[node.node_id]
                if e.source.node_id in dataset_map
            ]
            if not node.step.validate_inputs(node_inputs):
                raise RuntimeError(
                    f"Node '{node.node_id}' input validation failed."
                )
            result = node.step.execute(node_inputs)
            dataset_map[node.node_id] = result
        self.after_run()

    # ------------------------------------------------------------------
    # Lifecycle hooks (override in subclasses)
    # ------------------------------------------------------------------

    def before_run(self) -> None:
        """Hook called immediately before workflow execution begins."""

    def after_run(self) -> None:
        """Hook called immediately after workflow execution completes."""
