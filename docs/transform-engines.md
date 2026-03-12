# Motores de Transformação (Transform Engines)

O `aptdata` fornece **wrappers agnósticos de engine** que se integram perfeitamente com a classe `Workflow`, emitem rastreamento (*spans*) para o OpenTelemetry e lidam com serialização transparente para o `InMemoryDataset`.

Para utilizá-los, instale o grupo opcional correspondente:

```bash
pip install "aptdata[pandas]"
pip install "aptdata[spark]"
```

!!! tip "Imports Preguiçosos (Lazy Imports)"
    O framework isola dependências pesadas. A importação do módulo (`from aptdata.plugins.transform import PandasTransformer`) sempre funciona, e o `PluginDependencyError` só é levantado caso você tente instanciar a classe e o pacote falte no ambiente.

---

## Comparativo de Engines

=== "PandasTransformer"

    O `PandasTransformer` empacota funções puras do tipo `(pd.DataFrame) -> pd.DataFrame`, interceptando o *input/output* para conversão automática quando necessário.

    ```python
    import pandas as pd
    from aptdata.plugins.transform import PandasTransformer
    from aptdata.core.workflow import Workflow

    def clean(df: pd.DataFrame) -> pd.DataFrame:
        """Função de negócio pura, isolada do framework."""
        return df.dropna().drop_duplicates()

    transformer = PandasTransformer("clean_records", clean)

    wf = Workflow("my_pipeline")
    wf.add_step(transformer.transform)
    result = wf.execute(my_dataset)
    ```

    **Resolução Automática de Tipos:**

    | Input Recebido | Comportamento do Wrapper |
    |---|---|
    | `InMemoryDataset` | Extrai `.read()` para DataFrame, roda a função e repacota a saída no `InMemoryDataset`. |
    | `pd.DataFrame` | Executa diretamente; Retorna um `pd.DataFrame`. |
    | `list[dict]` | Converte para DataFrame temporário; Retorna um `pd.DataFrame`. |

=== "PySparkTransformer"

    O `PySparkTransformer` empacota funções do tipo `(SparkSession, DataFrame) -> DataFrame`.

    ```python
    from pyspark.sql import functions as F
    from aptdata.plugins.transform import PySparkTransformer
    from aptdata.core.workflow import Workflow

    def compute_revenue(spark, df):
        return df.withColumn("revenue", F.col("price") * F.col("quantity"))

    transformer = PySparkTransformer("compute_revenue", compute_revenue, app_name="ETL_Job")

    wf = Workflow("spark_pipeline")
    wf.add_step(transformer.transform)
    result = wf.execute(spark_df)
    ```

---

## Atributos de Telemetria (OTel)

A injeção dos transformadores no `Workflow` garante observabilidade imediata de performance.

| Atributo Padrão OTel | Descrição |
|---|---|
| `aptdata.transformer.name` | Identificador humano do step. |
| `aptdata.transformer.engine` | Engine detectada (`pandas` ou `pyspark`). |
| `aptdata.transformer.rows_in` | Contagem de linhas antes da transformação. |
| `aptdata.transformer.rows_out`| Contagem de linhas após a transformação. |
| `aptdata.transformer.compute_time_ms`| Tempo efetivo de execução da função encapsulada. |

Atributos exclusivos do **Spark**:

| Atributo OTel | Descrição |
|---|---|
| `aptdata.spark.app_name` | Nome da aplicação (Session). |
| `aptdata.spark.ui_url` | URL do Spark UI (se em execução). |

---

## Orquestração (`Workflow`)

Ambos implementam a abstração `BaseTransformer` e são compatíveis com `Workflow.add_step()` de forma intercalada a validadores de qualidade.

```mermaid
flowchart LR
    classDef default fill:rgba(255,255,255,0.02),stroke:#ff6a00,stroke-width:1px,color:inherit,rx:8px,ry:8px;
    DS["📥 Dataset\n(InMemoryDataset)"]
    PT["⚙️ PandasTransformer\nou PySparkTransformer"]
    QV["✅ QualityValidator"]
    OUT["📤 Dataset Limpo"]

    DS --> PT --> QV --> OUT
```
