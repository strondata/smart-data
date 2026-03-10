import inspect
from collections.abc import Callable
from typing import Any

from aptdata.core.context import IContext
from aptdata.core.dataset import IDataset
from aptdata.core.registry import ComponentRegistry
from aptdata.core.system import BaseComponent


class FunctionComponentAdapter(BaseComponent):
    """Adapter to make a simple python function behave like a BaseComponent."""
    def __init__(self, func: Callable, name: str, **kwargs: Any):
        # Determine component_id. User might have passed it in kwargs via yaml builder.
        # Otherwise fallback to the decorator's name
        comp_id = kwargs.pop('component_id', name)
        super().__init__(component_id=comp_id, **kwargs)
        self._func = func

    def validate_inputs(self, inputs: list[IDataset]) -> bool:
        """Default validation passes everything."""
        return True

    def execute(self, inputs: list[IDataset]) -> list[IDataset]:
        return self._execute(inputs)

    def _execute(self, inputs: list[IDataset]) -> list[IDataset]:
        # For simple functional components, we assume the signature can be:
        # func(inputs: list[IDataset], context: IContext) -> list[IDataset]
        # or just func(inputs: list[IDataset]) -> list[IDataset]

        sig = inspect.signature(self._func)
        kwargs = {}

        # Determine if the function expects context
        has_context_param = False
        for param_name, param in sig.parameters.items():
            if param.annotation == IContext or param_name == "context":
                kwargs[param_name] = self.context
                has_context_param = True
            elif param_name == "inputs":
                kwargs[param_name] = inputs

        # If the parameter isn't explicitly named "inputs", we'll just pass inputs as the first arg if it takes positional args
        if "inputs" not in kwargs and len(sig.parameters) > 0:
            first_param = list(sig.parameters.keys())[0]
            if first_param != "context" or not has_context_param:
                kwargs[first_param] = inputs

        return self._func(**kwargs)


def component(name: str | None = None) -> Callable:
    """Decorator to register a component class or a function in the global ComponentRegistry.

    If used on a function, it wraps it in an adapter that implements BaseComponent.
    """
    def decorator(target: type[BaseComponent] | Callable) -> type[BaseComponent] | Callable:
        # Determine registry name
        registry_name = name or target.__name__

        if isinstance(target, type) and issubclass(target, BaseComponent):
            # Target is a component class
            ComponentRegistry.register(registry_name, target)
            return target
        else:
            # Target is a function
            # We must create a dynamically generated subclass to easily instantiate later.
            class DynamicFunctionComponent(FunctionComponentAdapter):
                def __init__(self, **kwargs):
                    super().__init__(func=target, name=registry_name, **kwargs)

            # Change the __name__ to match
            DynamicFunctionComponent.__name__ = target.__name__ + "Component"
            ComponentRegistry.register(registry_name, DynamicFunctionComponent)
            return target

    return decorator

def pandas_component(name: str | None = None) -> Callable:
    """Decorator to register a pandas-specific function in the global ComponentRegistry.

    The decorated function should take a pd.DataFrame and optionally an IContext,
    and return a pd.DataFrame. The adapter will handle unwrapping/wrapping IDataset.
    """
    def decorator(target: Callable) -> Callable:
        registry_name = name or target.__name__

        class DynamicPandasComponent(FunctionComponentAdapter):
            def __init__(self, **kwargs):
                super().__init__(func=target, name=registry_name, **kwargs)

            def _execute(self, inputs: list[IDataset]) -> list[IDataset]:
                from aptdata.plugins.dataset import InMemoryDataset

                if not inputs:
                    raise ValueError(f"Pandas component '{self.component_id}' requires at least one input dataset.")

                # Unwrap the first input dataset to a pandas DataFrame
                df = inputs[0].read()

                sig = inspect.signature(self._func)
                kwargs = {}

                for param_name, param in sig.parameters.items():
                    if param.annotation == IContext or param_name == "context":
                        kwargs[param_name] = self.context
                    else:
                        kwargs[param_name] = df

                if len(kwargs) == 0 and len(sig.parameters) > 0:
                    first_param = list(sig.parameters.keys())[0]
                    kwargs[first_param] = df

                # Execute user function
                result_df = self._func(**kwargs)

                # Wrap the result back into an IDataset
                out_ds = InMemoryDataset(uri=f"memory://{self.component_id}_out")
                out_ds.write(result_df)
                return [out_ds]

        DynamicPandasComponent.__name__ = target.__name__ + "PandasComponent"
        ComponentRegistry.register(registry_name, DynamicPandasComponent)
        return target

    return decorator
