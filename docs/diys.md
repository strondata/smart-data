# DIYs & Snippets

Bem-vindo à seção **DIY (Do It Yourself)**! Aqui você encontra snippets e mini-tutoriais pragmáticos para resolver problemas reais de Engenharia de Dados utilizando o **aptdata**.

---

## 1. Transformador Minimalista com Pandas

Use o `PandasTransformer` para encapsular funções puras e reaproveitar código legado.

```python title="clean_data.py"
import pandas as pd
from typing import Any
from pydantic.dataclasses import dataclass as pydantic_dataclass
from aptdata.core import BaseDataset
from aptdata.plugins.transform import PandasTransformer

@pydantic_dataclass
class DataFrameDataset(BaseDataset):
    """Armazena um DataFrame Pandas."""
    def __post_init__(self):
        self._data = None

    def read(self) -> Any:
        return self._data

    def write(self, data: Any):
        self._data = data

# 1. Defina sua lógica padrão do Pandas
def drop_nulls_and_dedup(df: pd.DataFrame) -> pd.DataFrame:
    return df.dropna().drop_duplicates()

# 2. Encapsule a função
transformer = PandasTransformer("clean_data", drop_nulls_and_dedup)

# 3. Uso direto
raw_df = pd.DataFrame({"id": [1, 2, 2, None], "value": ["A", "B", "B", "C"]})
dataset = DataFrameDataset(uri="memory://raw")
dataset.write(raw_df)

# Saída do pipeline
result = transformer.transform(dataset)
print(result.read())
```

---

## 2. Aplicando Contratos de Schema (Fail-Fast)

Como abortar a execução imediatamente (`EnforcementMode.ABORT`) se a chave primária de um DataFrame estiver nula.

```python title="quality_check.py"
import pandas as pd
from aptdata.plugins.quality import (
    EnforcementMode, ExpectColumnToNotBeNull, QualityValidator
)

# Configura o validador com comportamento de falha estrita
validator = QualityValidator(
    expectations=[ExpectColumnToNotBeNull("id")],
    enforcement=EnforcementMode.ABORT, # Fail-Fast!
    name="pk_validator"
)

raw_df = pd.DataFrame({"id": [1, 2, None], "value": ["A", "B", "C"]})

try:
    clean_data = validator.validate(raw_df)
except ValueError as e:
    print(f"Validação falhou: {e}")
```

---

## 3. Extração Manual de Linhagem (Lineage)

Garantindo a rastreabilidade da origem (`READ`) e do destino (`WRITE`) dos dados.

```python title="lineage.py"
from aptdata.core.lineage import LineageGraph, LineageNode, LineageEventType
from aptdata.plugins.governance import LineageStore

# 1. Inicializa um Grafo para uma execução específica
graph = LineageGraph(run_id="run-1024", workflow_name="daily_etl")

# 2. Registra eventos I/O
graph.add_node(LineageNode(dataset_uri="s3://bronze/sales", event_type=LineageEventType.READ))
graph.add_node(LineageNode(dataset_uri="s3://silver/sales_clean", event_type=LineageEventType.WRITE))

# 3. Salva no repositório de governança (memória/logs por padrão)
store = LineageStore()
store.save(graph)

print("Linhagem gravada com sucesso.")
```

---

!!! tip "Execute no seu Navegador (Google Colab)"
    Quer testar o `aptdata` sem instalar nada localmente? Rode nosso ambiente *sandbox* interativo.

    [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/strondata/smart-data/blob/main/docs/notebooks/aptdata_quickstart.ipynb)
