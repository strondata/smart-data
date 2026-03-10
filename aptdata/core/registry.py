import logging

from aptdata.core.system import BaseComponent

logger = logging.getLogger(__name__)


class ComponentRegistry:
    """Global registry for dynamically registering and resolving components by name."""

    _components: dict[str, type[BaseComponent]] = {}

    @classmethod
    def register(cls, name: str, component_class: type[BaseComponent]) -> None:
        """Register a component class with a specific name."""
        if name in cls._components:
            logger.warning(f"Component '{name}' is already registered. Overwriting.")
        cls._components[name] = component_class
        logger.debug(f"Registered component '{name}' -> {component_class.__name__}")

    @classmethod
    def get(cls, name: str) -> type[BaseComponent]:
        """Retrieve a component class by name."""
        if name not in cls._components:
            raise KeyError(f"Component '{name}' is not registered.")
        return cls._components[name]

    @classmethod
    def clear(cls) -> None:
        """Clear all registered components."""
        cls._components.clear()
