import pandas as pd
import pytest

from aptdata.core.context import ExecutionContext, IContext
from aptdata.core.decorators import component, pandas_component
from aptdata.core.registry import ComponentRegistry
from aptdata.core.system import BaseComponent
from aptdata.plugins.dataset import InMemoryDataset


@pytest.fixture(autouse=True)
def clear_registry():
    """Clear registry before and after tests."""
    ComponentRegistry.clear()
    yield
    ComponentRegistry.clear()


def test_registry_registration_and_retrieval():
    class TestComponent(BaseComponent):
        def _execute(self, inputs):
            return inputs

    ComponentRegistry.register("my_comp", TestComponent)

    retrieved = ComponentRegistry.get("my_comp")
    assert retrieved is TestComponent

    with pytest.raises(KeyError):
        ComponentRegistry.get("non_existent")


def test_component_decorator_function():
    @component("test_func")
    def my_func(inputs, context):
        assert isinstance(context, IContext)
        return inputs

    # Test registry
    comp_class = ComponentRegistry.get("test_func")
    assert comp_class.__name__ == "my_funcComponent"

    # Test execution
    context = ExecutionContext()
    comp_instance = comp_class(component_id="inst1")
    comp_instance.context = context

    ds = InMemoryDataset(uri="mem://test")
    res = comp_instance.execute([ds])

    assert res == [ds]


def test_pandas_component_decorator():
    @pandas_component("test_pandas")
    def my_pandas_func(df, context):
        assert isinstance(df, pd.DataFrame)
        assert isinstance(context, IContext)
        df['new_col'] = 1
        return df

    comp_class = ComponentRegistry.get("test_pandas")

    # Test execution
    context = ExecutionContext()
    comp_instance = comp_class(component_id="inst2")
    comp_instance.context = context

    ds = InMemoryDataset(uri="mem://test")
    df = pd.DataFrame({"a": [1, 2]})
    ds.write(df)

    res = comp_instance.execute([ds])

    assert len(res) == 1
    out_df = res[0].read()
    assert "new_col" in out_df.columns
    assert out_df["new_col"].tolist() == [1, 1]


import yaml

from aptdata.core.yaml_builder import YamlSystemBuilder


def test_yaml_builder(tmp_path):
    # Create dummy component module
    comp_mod = tmp_path / "my_comps.py"
    comp_mod.write_text("""
from aptdata.core.decorators import component
@component("dummy")
def dummy_func(inputs):
    return inputs
""")

    # Create YAML manifest
    manifest_path = tmp_path / "pipeline.yaml"
    manifest_data = {
        "system": {
            "id": "test_sys",
            "flows": [
                {
                    "id": "flow1",
                    "components": [
                        {"name": "my_dummy", "ref": "dummy"}
                    ]
                }
            ]
        },
        "imports": [str(comp_mod.name)]
    }
    with open(manifest_path, 'w') as f:
        yaml.dump(manifest_data, f)

    builder = YamlSystemBuilder(str(manifest_path))
    system = builder.build()

    assert system.system_id == "test_sys"
    assert len(system._flows) == 1
    flow = system._flows[0]
    assert flow.flow_id == "flow1"

    # Run the system, it builds the flow graph inside flow.run() -> flow.compile() -> flow.build()
    # Or we can just call build directly since DynamicFlow overrides it to add components
    flow.build()
    assert "my_dummy" in flow._nodes
