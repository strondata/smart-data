from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aptdata.core.dataset import IDataset
from aptdata.core.system import IExecutor
from aptdata.core.workflow import BaseWorkflow

if TYPE_CHECKING:
    from aptdata.core.workflow import IWorkflow

logger = logging.getLogger(__name__)


class SparkExecutor(IExecutor):
    """Execution engine that uses PySpark to process a BaseWorkflow DAG.

    This executor leverages an external Spark cluster or local Spark session
    to distribute processing, addressing the local orchestration bottleneck.
    """

    def __init__(self, app_name: str = "aptdata-spark-executor") -> None:
        try:
            from pyspark.sql import SparkSession
        except ImportError as exc:
            raise ImportError(
                "PySpark is required for SparkExecutor. Install it via "
                "`pip install pyspark`."
            ) from exc

        self.app_name = app_name
        self.spark = SparkSession.builder.appName(self.app_name).getOrCreate()

    def execute_flow(
        self, flow: IWorkflow, initial_inputs: list[IDataset]
    ) -> list[IDataset]:
        """Execute the flow graph using PySpark as the backend engine.

        Note: True parallel execution of disjoint branches would use PySpark's
        async actions or thread pools. This implementation iterates through
        the topological sort order.
        """
        if not isinstance(flow, BaseWorkflow):
            raise TypeError("SparkExecutor only supports BaseWorkflow")

        if not flow._compiled:
            flow.compile()

        pending_inputs: dict[str, list[IDataset]] = {
            component_id: [] for component_id in flow._execution_order
        }

        if flow._execution_order:
            pending_inputs[flow._execution_order[0]] = list(initial_inputs)

        terminal_outputs: list[IDataset] = list(initial_inputs)

        for component_id in flow._execution_order:
            node = flow._nodes[component_id]
            component = node.component
            inputs = pending_inputs.get(component_id, [])

            if not component.validate_inputs(inputs):
                logger.debug(f"Component {component_id} validation failed, skipping.")
                continue

            # Assuming the component is compatible with Spark dataframes or
            # extracts them from the datasets.
            outputs = component.execute(inputs)

            outgoing = flow._adjacency.get(component_id, [])
            if not outgoing:
                terminal_outputs = outputs
                continue

            traversed = False
            for edge in outgoing:
                if edge.condition is None or edge.condition(outputs):
                    pending_inputs[edge.target_id].extend(outputs)
                    traversed = True

            if not traversed:
                terminal_outputs = outputs

        return terminal_outputs
