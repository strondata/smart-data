# Qualidade de Dados (Data Quality)

O `aptdata` oferece uma camada nativa de qualidade de dados compatível tanto com **Pandas** quanto com **PySpark** DataFrames, abstraindo a diferença de engines.

---

## Contratos de Schema (`SchemaContract`)

Um `SchemaContract` declara rigorosamente o formato esperado, a tipagem estática e o nível de sensibilidade dos dados antes da ingestão.

```python
from aptdata.plugins.quality import (
    ColumnClassification,
    ColumnContract,
    EnforcementMode,
    SchemaContract,
)

contract = SchemaContract(
    name="orders_v1",
    version="1.0.0",
    owner="data-engineering",
    description="Customer order records.",
    enforcement=EnforcementMode.ABORT,
    columns=[
        ColumnContract(name="id",     dtype="int64",   nullable=False),
        ColumnContract(name="email",  dtype="str",     nullable=False, pii=True,
                       classification=ColumnClassification.PII),
        ColumnContract(name="amount", dtype="float64", nullable=True),
    ],
)

# Métodos utilitários
pii_cols   = contract.get_pii_columns()
pii_tagged = contract.get_columns_by_classification(ColumnClassification.PII)
```

### Classificação de Colunas (`ColumnClassification`)

| Valor (`Enum`) | Descrição e Nível de Acesso |
|---|---|
| `PUBLIC` | Sem restrições de visibilidade. |
| `INTERNAL` | Uso exclusivamente interno da corporação. |
| `CONFIDENTIAL`| Acesso estritamente baseado em necessidade (Need-to-know). |
| `PII` | Dados Pessoais Identificáveis (Lei Geral de Proteção de Dados - LGPD). |
| `PHI` | Dados de Saúde Protegidos (HIPAA). |
| `FINANCIAL` | Transações Financeiras (PCI DSS). |
| `SENSITIVE` | Dados sensíveis genéricos. |

---

## Verificações (`Expectations`)

As `Expectations` (`BaseExpectation`) focam em atributos de coluna gerando um `CheckResult`. Cada expectativa isola `validate_pandas` e `validate_spark`, detectando a *engine* nativa em runtime sem dependência de adaptadores de domínio cruzados.

<div class="grid cards" markdown>

-   :material-null: **`ExpectColumnToNotBeNull`**

    Verifica se não existem valores nulos ou vazios na coluna.
    ```python
    ExpectColumnToNotBeNull("age").validate(df)
    ```

-   :material-arrow-left-right: **`ExpectColumnValuesInRange`**

    Verifica se todos os valores estão contidos entre `min_val` e `max_val` (inclusivo).
    ```python
    ExpectColumnValuesInRange("score", min_val=0, max_val=100).validate(df)
    ```

-   :material-fingerprint: **`ExpectColumnValuesToBeUnique`**

    Garante unicidade total (Chave Primária).
    ```python
    ExpectColumnValuesToBeUnique("id").validate(df)
    ```

-   :material-regex: **`ExpectColumnValuesToMatchRegex`**

    Assegura que a string está aderente a um padrão Regex estrito.
    ```python
    ExpectColumnValuesToMatchRegex("code", pattern=r"[A-Z]\d{3}").validate(df)
    ```

</div>

---

## Validador Orquestrado (`QualityValidator`)

O `QualityValidator` executa um *suite* inteiro de expectativas e aplica a política definida em `EnforcementMode`.

```python
from aptdata.plugins.quality import (
    EnforcementMode,
    ExpectColumnToNotBeNull,
    ExpectColumnValuesToBeUnique,
    QualityValidator,
)

validator = QualityValidator(
    expectations=[
        ExpectColumnToNotBeNull("id"),
        ExpectColumnValuesToBeUnique("id"),
        ExpectColumnToNotBeNull("email"),
    ],
    enforcement=EnforcementMode.ABORT,
    name="order_validator",
)

# Integração nativa como um step no pipeline
from aptdata.core.workflow import Workflow

wf = Workflow("quality_pipeline")
wf.add_step(validator.validate)
clean_data = wf.execute(raw_data)
```

### Modos de Punição (`Enforcement Modes`)

| Modo | Comportamento no Pipeline |
|---|---|
| `ABORT` | Bloqueia o fluxo. Levanta um `ValueError` imediatamente na primeira *Expectation* que falhar. |
| `WARN` | Não bloqueia. Emite um log de alerta via `warnings.warn` e prossegue o fluxo. |
| `TAG` | Invisível. Apenas anota a estrutura `schema_metadata["quality_report"]` no dataset para consulta posterior. |

---

## Relatório de Qualidade (`QualityReport`)

O validador orquestrado produz um `QualityReport` imutável. `passed` avalia como `True` unicamente se falhas (`FAILED`) inexistirem.

```python
from aptdata.plugins.quality.report import QualityReport

report = QualityReport(dataset_uri="s3://bucket/data.parquet")
# (Checks são apendados dinamicamente pelo QualityValidator...)

print(report.passed)    # True / False
print(report.summary)   # {"PASSED": 3, "FAILED": 1, "WARNING": 0}
```

---

## Integração OTel

Para governança e observabilidade em painéis externos (como Grafana ou Datadog), o `QualityValidator` emite um *span* do tipo OTel com os seguintes *tags*:

| Atributo OTel | Descrição |
|---|---|
| `aptdata.quality.validator_name` | Identificador único do Validador |
| `aptdata.quality.enforcement` | Estratégia de falha (ABORT, WARN) |
| `aptdata.quality.num_expectations` | Total de regras configuradas |
| `aptdata.quality.passed` | Sucesso global Booleano |
| `aptdata.quality.num_checks` | Quantidade absoluta de verificações feitas |
| `aptdata.quality.failed_checks` | Quantidade absoluta de falhas detectadas |
