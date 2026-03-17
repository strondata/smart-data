# Primeiros Passos (Getting Started)

## Requisitos
- Python ≥ 3.10
- [Poetry](https://python-poetry.org/) (recomendado) **ou** `pip`

---

## Instalação

=== "Poetry"
    ```bash
    poetry add aptdata
    # Para plugins opcionais:
    poetry add "aptdata[pandas]"
    ```

=== "Pip"
    <div class="termy">
      <span data-ty="input">pip install aptdata</span>
      <span data-ty="progress"></span>
      <span data-ty>Successfully installed aptdata-0.1.0</span>
      <span data-ty></span>
      <span data-ty="input" data-ty-prompt=">"># Para plugins opcionais:</span>
      <span data-ty="input">pip install "aptdata[pandas]"</span>
    </div>

### Dependências Opcionais
- `pandas`: Suporte ao Pandas e `PandasTransformComponent`
- `spark`: Suporte ao PySpark
- `plugins`: Adaptadores REST, PostgreSQL, Parquet I/O
- `ai`: Servidor Model Context Protocol (MCP) para IA
- `all`: Instala tudo

---

## Verificando a Instalação

Rode no terminal:
```bash
aptdata --help
```

Saída esperada:
```text
Usage: aptdata [OPTIONS] COMMAND [ARGS]...

  Smart Data – framework declarativo de pipelines.

Options:
  --help  Exibe esta mensagem e encerra.

Commands:
  monitor   Abre o dashboard TUI de monitoramento.
  run       Executa um sistema registrado.
  scaffold  Inicializa um novo projeto aptdata.
  mesh      Orquestra componentes via mesh.yaml.
```

---

## Construindo seu Primeiro Sistema

O fluxo lógico de orquestração do framework segue cinco etapas principais:

```mermaid
flowchart LR
    %% Estilos Customizados (Design Premium)
    classDef default fill:#0b132b,stroke:#ff6a00,stroke-width:1px,color:#fff,rx:8px,ry:8px;

    DS["1️⃣ Dataset\nLeitura / Escrita (IDataset)"]
    CO["2️⃣ Component\nTransformação (IComponent)"]
    FL["3️⃣ Flow\nConexões Condicionais (IFlow)"]
    SY["4️⃣ System\nOrquestrador Base (ISystem)"]
    RG["5️⃣ Execução\nCLI ou Plugin Registry"]

    DS --> CO --> FL --> SY --> RG
```

### 1. Criar um Dataset
Um Dataset implementa as operações de leitura e escrita através do contrato `IDataset`. Herdando de `BaseDataset`, você recebe injeção de estado e validação via Pydantic.

```python
from pydantic.dataclasses import dataclass as pydantic_dataclass
from aptdata.core import BaseDataset

@pydantic_dataclass
class MemoryDataset(BaseDataset): # (1)!
    """Dataset em memória para propósitos de teste."""

    def __post_init__(self) -> None: # (2)!
        self._data = None

    def read(self): # (3)!
        return self._data

    def write(self, data) -> None:
        self._data = data
```

1. A herança de `BaseDataset` garante injeção do esquema Pydantic para validação robusta.
2. O método `__post_init__` é o local ideal para definir propriedades mutáveis ou privadas que não devem ser validadas como input do construtor.
3. O método `read()` é onde a lógica de extração real (ex: chamar a API do Pandas ou do Spark) acontece.

!!! tip "Uso Prático"
    No dia-a-dia, você não precisa recriar datasets em memória. Basta usar a classe core pronta:
    `from aptdata.plugins.dataset import InMemoryDataset`.

### 2. Criar um Componente
Um Componente (implementa `IComponent`) recebe uma lista de *inputs* validados, os processa, e retorna uma lista de *outputs* (permitindo múltiplas saídas ou fluxos paralelos).

```python
from pydantic.dataclasses import dataclass as pydantic_dataclass
from aptdata.core import BaseComponent, ComponentMeta, ComponentKind, IDataset
from aptdata.plugins.dataset import InMemoryDataset

@pydantic_dataclass
class DoubleComponent(BaseComponent):
    """Duplica todos os valores numéricos da lista."""

    def validate_inputs(self, inputs: list[IDataset]) -> bool:
        return len(inputs) == 1

    def execute(self, inputs: list[IDataset]) -> list[IDataset]:
        data = inputs[0].read()
        out = InMemoryDataset(uri="memory://output")
        out.write([x * 2 for x in data])
        return [out]

comp = DoubleComponent(
    component_id="double",
    metadata=ComponentMeta(kind=ComponentKind.TRANSFORM, tags=["math"]),
)
```

!!! tip "Dica de DX"
    Com a API Declarativa (decorators como `@pandas_component`), a instanciação manual do `InMemoryDataset` é feita pelo framework "por debaixo dos panos". Você codifica apenas a função recebendo e devolvendo DataFrames.

### 3. Criar um Fluxo (Flow)
Um Fluxo liga componentes em um Grafo Direcionado. Herdando de `BaseFlow`, as arestas suportam condicionais nativas (`FlowEdge`).

```python
from pydantic.dataclasses import dataclass as pydantic_dataclass
from aptdata.core import BaseFlow, IComponent, IDataset, FlowEdge, FlowNode
from typing import Callable

@pydantic_dataclass
class SimpleFlow(BaseFlow):
    def __post_init__(self) -> None:
        self._nodes: dict[str, FlowNode] = {}
        self._edges: list[FlowEdge] = []
        self._order: list[str] = []

    def add_component(self, c: IComponent) -> None:
        self._nodes[c.component_id] = FlowNode(component=c, flow=self)

    def connect(self, src: str, tgt: str, condition: Callable | None = None) -> None:
        self._edges.append(FlowEdge(source_id=src, target_id=tgt, condition=condition))

    def compile(self) -> None:
        targets = {e.target_id for e in self._edges}
        roots = [cid for cid in self._nodes if cid not in targets]
        queue = list(roots)
        while queue:
            current = queue.pop(0)
            self._order.append(current)
            for e in self._edges:
                if e.source_id == current:
                    queue.append(e.target_id)

    def run(self, inputs: list[IDataset]) -> list[IDataset]:
        outputs = inputs
        for cid in self._order:
            comp = self._nodes[cid].component
            if comp.validate_inputs(outputs):
                outputs = comp.execute(outputs)
        return outputs
```

### 4. Criar e Registrar um Sistema
```python
from pydantic.dataclasses import dataclass as pydantic_dataclass
from aptdata.core import BaseSystem, IFlow
from aptdata.plugins import registry

from aptdata.plugins.dataset import InMemoryDataset

@pydantic_dataclass
class MySystem(BaseSystem):
    def __post_init__(self) -> None:
        self._flows: list[IFlow] = []

    def register_flow(self, flow: IFlow) -> None:
        self._flows.append(flow)

    def run(self) -> None:
        ds = InMemoryDataset(uri="memory://input")
        ds.write([1, 2, 3])
        inputs = [ds]
        for flow in self._flows:
            inputs = flow.run(inputs)

# Registre no Plugin Registry global
registry.register("my_system", MySystem)
```

### 5. Executar via CLI
Com o seu componente registrado no entrypoint do módulo, execute:

```bash
aptdata run my_system
```

Eventos de ciclo de vida automáticos (`pre_execute`, `on_success`) são emitidos internamente pelo EventBus.

Saída esperada em formato JSON Lines:
```json
{"event": "pipeline.started", "pipeline": "my_system", "env": "dev", "dry_run": false}
{"event": "pipeline.completed", "pipeline": "my_system", "env": "dev", "dry_run": false, "elapsed_seconds": 0.001}
```

---

## Opções Úteis da CLI

=== "Execução (Run)"

    | Opção | Default | Descrição |
    |---|---|---|
    | `name` | *(obrigatório)* | Nome do sistema registrado (`registry.register`) |
    | `--env`, `-e` | `dev` | Variável de ambiente alvo da execução |
    | `--dry-run` | `false` | Instancia componentes mas **não** dispara o `run()` |

=== "Monitoramento (TUI)"

    | Opção | Default | Descrição |
    |---|---|---|
    | `--refresh`, `-r` | `1.0` | Intervalo em segundos de auto-atualização do terminal |

---

## Integração MCP com Agentes de IA

O framework inclui um servidor [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) (`aptdata mcp-start`) que permite a agentes de IA (Claude, Copilot, Devin) descobrirem e interagirem com seus pipelines.

Adicione ao `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "aptdata": {
      "command": "aptdata",
      "args": ["mcp-start"]
    }
  }
}
```

Agentes podem consultar metadados com as URIs `schema://datasets/{name}` e chamar tools como `run_flow` sem alucinações de schema.
