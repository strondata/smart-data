"""Tests for the workflow orchestration classes."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic.dataclasses import dataclass as pydantic_dataclass

from smart_data.core.context import EnvironmentConfig, ExecutionSessionContext
from smart_data.core.dataset import BaseDataset, IDataset
from smart_data.core.step import BaseStep
from smart_data.core.workflow import BaseWorkflow, IWorkflow, WorkflowNode


# ---------------------------------------------------------------------------
# Minimal concrete helpers used only within tests
# ---------------------------------------------------------------------------


@pydantic_dataclass
class _MemDataset(BaseDataset):
    def read(self) -> Any:
        return self.schema_metadata.get("value")

    def write(self, data: Any) -> None:
        self.schema_metadata["value"] = data


@pydantic_dataclass
class _PassthroughStep(BaseStep):
    """Step that passes its first input through, or returns a sentinel."""

    def validate_inputs(self, inputs: list[IDataset]) -> bool:
        return True

    def execute(self, inputs: list[IDataset]) -> IDataset:
        out = _MemDataset(uri="memory://out")
        if inputs:
            out.write(inputs[0].read())
        else:
            out.write("root")
        return out


@pydantic_dataclass
class _SimpleWorkflow(BaseWorkflow):
    """Minimal concrete workflow used for testing."""


# ---------------------------------------------------------------------------
# IWorkflow interface tests
# ---------------------------------------------------------------------------


class TestIWorkflow:
    def test_cannot_instantiate_interface(self):
        with pytest.raises(TypeError):
            IWorkflow()  # type: ignore[abstract]

    def test_concrete_is_instance_of_interface(self):
        wf = _SimpleWorkflow()
        assert isinstance(wf, IWorkflow)
        assert isinstance(wf, BaseWorkflow)


# ---------------------------------------------------------------------------
# WorkflowNode tests
# ---------------------------------------------------------------------------


class TestWorkflowNode:
    def test_workflow_back_reference_none_before_add(self):
        node = WorkflowNode(node_id="n1", step=_PassthroughStep(step_id="s1"))
        assert node.workflow is None

    def test_workflow_back_reference_set_after_add_node(self):
        node = WorkflowNode(node_id="n1", step=_PassthroughStep(step_id="s1"))
        wf = _SimpleWorkflow()
        wf.add_node(node)
        assert node.workflow is wf

    def test_node_id_stored(self):
        node = WorkflowNode(node_id="my_node", step=_PassthroughStep(step_id="s1"))
        assert node.node_id == "my_node"

    def test_node_step_accessible(self):
        step = _PassthroughStep(step_id="s2")
        node = WorkflowNode(node_id="n2", step=step)
        assert node.step is step

    def test_context_reachable_from_node(self):
        env = EnvironmentConfig(target="test", env_file=".env", variables={})
        ctx = ExecutionSessionContext(environment=env)
        wf = _SimpleWorkflow(context=ctx)
        node = WorkflowNode(node_id="n1", step=_PassthroughStep(step_id="s1"))
        wf.add_node(node)
        assert node.workflow is wf
        assert node.workflow.context is ctx  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# WorkflowEdge tests
# ---------------------------------------------------------------------------


class TestWorkflowEdge:
    def _make_workflow_with_two_nodes(
        self,
    ) -> tuple[_SimpleWorkflow, WorkflowNode, WorkflowNode]:
        wf = _SimpleWorkflow()
        node_a = WorkflowNode(node_id="a", step=_PassthroughStep(step_id="a"))
        node_b = WorkflowNode(node_id="b", step=_PassthroughStep(step_id="b"))
        wf.add_node(node_a)
        wf.add_node(node_b)
        return wf, node_a, node_b

    def test_edge_workflow_back_reference_set(self):
        wf, _, _ = self._make_workflow_with_two_nodes()
        edge = wf.add_edge("a", "b")
        assert edge.workflow is wf

    def test_edge_source_and_target_are_nodes(self):
        wf, node_a, node_b = self._make_workflow_with_two_nodes()
        edge = wf.add_edge("a", "b")
        assert edge.source is node_a
        assert edge.target is node_b

    def test_context_reachable_from_edge(self):
        env = EnvironmentConfig(target="test", env_file=".env", variables={})
        ctx = ExecutionSessionContext(environment=env)
        wf = _SimpleWorkflow(context=ctx)
        wf.add_node(WorkflowNode(node_id="a", step=_PassthroughStep(step_id="a")))
        wf.add_node(WorkflowNode(node_id="b", step=_PassthroughStep(step_id="b")))
        edge = wf.add_edge("a", "b")
        assert edge.workflow is wf
        assert edge.workflow.context is ctx  # type: ignore[union-attr]

    def test_add_edge_missing_source_raises(self):
        wf = _SimpleWorkflow()
        wf.add_node(WorkflowNode(node_id="b", step=_PassthroughStep(step_id="b")))
        with pytest.raises(KeyError, match="Source node 'missing'"):
            wf.add_edge("missing", "b")

    def test_add_edge_missing_target_raises(self):
        wf = _SimpleWorkflow()
        wf.add_node(WorkflowNode(node_id="a", step=_PassthroughStep(step_id="a")))
        with pytest.raises(KeyError, match="Target node 'missing'"):
            wf.add_edge("a", "missing")


# ---------------------------------------------------------------------------
# BaseWorkflow execution tests
# ---------------------------------------------------------------------------


class TestBaseWorkflow:
    def test_compile_and_run_no_error(self):
        wf = _SimpleWorkflow()
        wf.add_node(WorkflowNode(node_id="n1", step=_PassthroughStep(step_id="d1")))
        wf.compile()
        wf.run()  # should not raise

    def test_run_without_compile_raises(self):
        wf = _SimpleWorkflow()
        wf.add_node(WorkflowNode(node_id="n1", step=_PassthroughStep(step_id="d1")))
        with pytest.raises(RuntimeError, match="not compiled"):
            wf.run()

    def test_context_stored_and_accessible(self):
        env = EnvironmentConfig(target="staging", env_file=".env", variables={})
        ctx = ExecutionSessionContext(environment=env)
        wf = _SimpleWorkflow(context=ctx)
        assert wf.context is ctx

    def test_nodes_registered_in_internal_map(self):
        wf = _SimpleWorkflow()
        node = WorkflowNode(node_id="n1", step=_PassthroughStep(step_id="d1"))
        wf.add_node(node)
        assert "n1" in wf._nodes
        assert wf._nodes["n1"] is node

    def test_edges_registered_in_internal_list(self):
        wf = _SimpleWorkflow()
        wf.add_node(WorkflowNode(node_id="a", step=_PassthroughStep(step_id="a")))
        wf.add_node(WorkflowNode(node_id="b", step=_PassthroughStep(step_id="b")))
        edge = wf.add_edge("a", "b")
        assert len(wf._edges) == 1
        assert wf._edges[0] is edge

    def test_data_flows_from_root_to_downstream_node(self):
        """Root node output should be passed as input to a connected child node."""
        received: list[Any] = []

        @pydantic_dataclass
        class _CapturingStep(BaseStep):
            def validate_inputs(self, inputs: list[IDataset]) -> bool:
                return True

            def execute(self, inputs: list[IDataset]) -> IDataset:
                received.extend(inputs)
                out = _MemDataset(uri="memory://capture")
                out.write("captured")
                return out

        wf = _SimpleWorkflow()
        root = WorkflowNode(node_id="root", step=_PassthroughStep(step_id="r"))
        child = WorkflowNode(node_id="child", step=_CapturingStep(step_id="c"))
        wf.add_node(root)
        wf.add_node(child)
        wf.add_edge("root", "child")
        wf.compile()
        wf.run()

        # child must have received exactly one dataset produced by root
        assert len(received) == 1
        assert received[0].read() == "root"  # root sentinel value

    def test_before_and_after_run_hooks_called(self):
        calls: list[str] = []

        @pydantic_dataclass
        class _HookedWorkflow(BaseWorkflow):
            def before_run(self) -> None:
                calls.append("before")

            def after_run(self) -> None:
                calls.append("after")

        wf = _HookedWorkflow()
        wf.add_node(WorkflowNode(node_id="n1", step=_PassthroughStep(step_id="d1")))
        wf.compile()
        wf.run()
        assert calls == ["before", "after"]

    def test_compiled_flag_set_after_compile(self):
        wf = _SimpleWorkflow()
        assert wf._compiled is False
        wf.compile()
        assert wf._compiled is True

    def test_run_raises_when_validate_inputs_fails(self):
        @pydantic_dataclass
        class _RejectingStep(BaseStep):
            def validate_inputs(self, inputs: list[IDataset]) -> bool:
                return False

            def execute(self, inputs: list[IDataset]) -> IDataset:
                return _MemDataset(uri="memory://never")

        wf = _SimpleWorkflow()
        wf.add_node(WorkflowNode(node_id="bad", step=_RejectingStep(step_id="r")))
        wf.compile()
        with pytest.raises(RuntimeError, match="input validation failed"):
            wf.run()
