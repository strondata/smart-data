### Static Analysis (Ruff)
```
All checks passed!

```

### Dead Code Analysis (Vulture)
```
aptdata/core/context.py:24: unused property 'telemetry' (60% confidence)
aptdata/core/context.py:69: unused property 'telemetry' (60% confidence)
aptdata/core/dataset.py:55: unused class 'IIterableDataset' (60% confidence)
aptdata/core/decorators.py:88: unused function 'pandas_component' (60% confidence)
aptdata/core/events.py:21: unused variable 'model_config' (60% confidence)
aptdata/core/events.py:34: unused variable 'status' (60% confidence)
aptdata/core/events.py:35: unused variable 'execution_time' (60% confidence)
aptdata/core/events.py:37: unused variable 'error_message' (60% confidence)
aptdata/core/events.py:43: unused method 'subscribe' (60% confidence)
aptdata/core/events.py:69: unused method 'subscribe' (60% confidence)
aptdata/core/lineage.py:20: unused variable 'READ' (60% confidence)
aptdata/core/lineage.py:21: unused variable 'TRANSFORM' (60% confidence)
aptdata/core/lineage.py:22: unused variable 'QUALITY_CHECK' (60% confidence)
aptdata/core/lineage.py:23: unused variable 'BUSINESS_RULE' (60% confidence)
aptdata/core/lineage.py:24: unused variable 'WRITE' (60% confidence)
aptdata/core/lineage.py:25: unused variable 'SCHEMA_CHANGE' (60% confidence)
aptdata/core/lineage.py:178: unused method 'add_node' (60% confidence)
aptdata/core/lineage.py:182: unused method 'get_upstream' (60% confidence)
aptdata/core/lineage.py:194: unused method 'get_downstream' (60% confidence)
aptdata/core/system.py:128: unused variable 'TRANSFORM' (60% confidence)
aptdata/core/system.py:129: unused variable 'FILTER' (60% confidence)
aptdata/core/system.py:130: unused variable 'AGGREGATE' (60% confidence)
aptdata/core/system.py:131: unused variable 'EXTRACT' (60% confidence)
aptdata/core/system.py:132: unused variable 'LOAD' (60% confidence)
aptdata/core/system.py:159: unused variable 'extra' (60% confidence)
aptdata/core/workflow.py:43: unused variable 'workflow' (60% confidence)
aptdata/core/workflow.py:84: unused variable 'workflow_id' (60% confidence)
aptdata/core/workflow.py:190: unused method 'add_step' (60% confidence)
aptdata/core/workflow.py:207: unused method 'resume' (60% confidence)
aptdata/core/yaml_builder.py:15: unused class 'YamlSystemBuilder' (60% confidence)
aptdata/core/yaml_builder.py:65: unused attribute 'telemetry' (60% confidence)

```