# Configuração YAML (Configuration)

O `aptdata` suporta a configuração declarativa de pipelines via arquivo `aptdata.yaml`, permitindo que você defina, valide e orquestre a execução de sistemas sem precisar escrever código de inicialização (*bootstrap*) em Python.

---

## Formato do Arquivo

O *schema* principal utiliza a seguinte estrutura:

```yaml
version: "1"           # Versão do schema de configuração (obrigatório)
env: dev               # Ambiente de destino (default: dev)

systems:
  - name: my_system    # Nome registrado no Plugin Registry (registry.register)
    enabled: true      # Defina como 'false' para pular a execução

plugins:
  - module: my_package.systems  # Módulo Python injetado antes da resolução dos sistemas

telemetry:
  enabled: true
  exporter: console    # console | otlp
  endpoint: ""         # Endpoint OTLP (usado quando exporter: otlp)
```

!!! note "Exemplo Mínimo"
    ```yaml
    version: "1"
    env: production

    plugins:
      - module: my_project.systems

    systems:
      - name: etl_pipeline
        enabled: true
      - name: quality_checks
        enabled: true
    ```

---

## Comandos da CLI (`config`)

<div class="grid cards" markdown>

-   :material-check-decagram: **`config validate`**

    Valida a sintaxe de um `aptdata.yaml` contra o schema Pydantic sem rodar os pipelines.
    ```bash
    aptdata config validate aptdata.yaml
    ```

-   :material-file-document-plus: **`config init`**

    Gera um `aptdata.yaml` inicial no diretório atual ou especificado.
    ```bash
    aptdata config init [--output /path/]
    ```

-   :material-eye-outline: **`config show`**

    Exibe a configuração carregada e parseada (com as substituições de variáveis de ambiente aplicadas).
    ```bash
    aptdata config show aptdata.yaml
    ```

-   :material-play-network: **`config run`**

    Carrega o arquivo e dispara todos os sistemas listados onde `enabled: true`.
    ```bash
    aptdata config run aptdata.yaml [--env production]
    ```

</div>

---

## Substituição de Variáveis de Ambiente (Secret Manager)

Referências `YAML` na sintaxe `${VAR_NAME}` resolvem dinamicamente variáveis de ambiente instanciadas (`SecretManager.resolve`).

```yaml
telemetry:
  endpoint: "${OTEL_EXPORTER_OTLP_ENDPOINT}"
```

!!! tip "Resolução Opcional de `.env`"
    Se o pacote `python-dotenv` estiver instalado no seu ambiente, o framework carregará automaticamente as variáveis de um arquivo `.env` localizado na raiz da execução.

---

## Integração com Templates

A infraestrutura `scaffold` preenche o `aptdata.yaml` na raiz baseando-se no `template` escolhido.

```bash
aptdata scaffold my_project --template medallion
# Cria my_project/aptdata.yaml já pré-configurado
```
