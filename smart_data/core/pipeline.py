"""Pipeline interface and base class."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from pydantic.dataclasses import dataclass as pydantic_dataclass

from smart_data.core.context import ExecutionSessionContext
from smart_data.core.step import IStep


@dataclass
class IPipeline(ABC):
    """Dataclass interface for pipeline types.

    A pipeline orchestrates a directed acyclic graph (DAG) of
    :class:`~smart_data.core.step.IStep` instances.  Concrete
    implementations must register steps, compile the execution graph
    and provide a ``run`` entry-point.
    """

    @abstractmethod
    def register_step(self, step: IStep) -> None:
        """Register a step into the pipeline."""

    @abstractmethod
    def compile_dag(self) -> None:
        """Compile and validate the DAG before execution."""

    @abstractmethod
    def run(self) -> None:
        """Execute the compiled pipeline."""


@pydantic_dataclass
class BasePipeline(IPipeline):
    """Base pipeline class.

    Concrete pipeline implementations must inherit from this class and
    implement the :meth:`register_step`, :meth:`compile_dag` and
    :meth:`run` abstract methods inherited from :class:`IPipeline`.
    """

    context: ExecutionSessionContext | None = None
