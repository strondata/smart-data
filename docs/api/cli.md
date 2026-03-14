# Referência da CLI

A interface de linha de comando `aptdata` emite **JSON estruturado** em todas as saídas, sendo ideal para uso com orquestradores de IA, esteiras de CI/CD e shell scripts.

---

## `aptdata run`

Executa um sistema registrado pelo nome.

```
aptdata run PIPELINE [OPTIONS]
```

### Argumentos

| Nome | Obrigatório | Descrição |
|------|-------------|-----------|
| `PIPELINE` | ✅ | Identificador do sistema registrado no plugin registry |

### Opções

| Flag | Default | Descrição |
|------|---------|-----------|
| `--env`, `-e` | `dev` | Variável de ambiente alvo da execução (ex: `dev`, `staging`, `prod`) |
| `--dry-run` | `false` | Instancia componentes e compila fluxos, mas **não** dispara o `run()` |
| `--help` | | Exibe ajuda e encerra |

### Códigos de Saída (Exit Codes)

| Código | Significado |
|--------|-------------|
| `0` | Sistema executado com sucesso |
| `1` | Ocorreu um erro (sistema não encontrado, exceção de tempo de execução, etc.) |

### Eventos JSON

**`pipeline.started`** – emitido imediatamente após a CLI receber o comando:

```json
{
  "event": "pipeline.started",
  "pipeline": "my_pipeline",
  "env": "prod",
  "dry_run": false
}
```

**`pipeline.completed`** – emitido quando o sistema finaliza com sucesso:

```json
{
  "event": "pipeline.completed",
  "pipeline": "my_pipeline",
  "env": "prod",
  "dry_run": false,
  "elapsed_seconds": 1.234
}
```

**`pipeline.error`** – emitido em *stderr* quando ocorre um erro:

```json
{
  "event": "pipeline.error",
  "pipeline": "my_pipeline",
  "env": "prod",
  "error": "Pipeline 'my_pipeline' not found in registry.",
  "elapsed_seconds": 0.001
}
```

### Exemplos

```bash
# Executa no ambiente default (dev)
aptdata run my_pipeline

# Executa apontando para produção
aptdata run my_pipeline --env prod

# Valida sem executar de fato
aptdata run my_pipeline --dry-run

# Captura e faz parse da saída JSON usando jq
aptdata run my_pipeline | jq '.elapsed_seconds'
```

---

## `aptdata monitor`

Inicia o dashboard TUI (Text User Interface) interativo de monitoramento.

```
aptdata monitor [OPTIONS]
```

### Opções

| Flag | Default | Descrição |
|------|---------|-----------|
| `--refresh`, `-r` | `1.0` | Intervalo de auto-atualização do dashboard em segundos |
| `--help` | | Exibe ajuda e encerra |

### Atalhos de Teclado

| Tecla | Ação |
|-------|------|
| `r` | Atualizar manualmente todos os painéis |
| `q` / `Ctrl+C` | Sair |

### Exemplos

```bash
# Inicia com atualização a cada 1 segundo (default)
aptdata monitor

# Atualização mais rápida para fluxos de alta frequência
aptdata monitor --refresh 0.25
```

---

## `aptdata system`

Inspeciona e valida sistemas registrados.

### `aptdata system list [--json]`

Lista todos os sistemas no plugin registry.

```bash
aptdata system list
aptdata system list --json
```

### `aptdata system info NAME [--json]`

Exibe informações detalhadas sobre um sistema registrado (nome da classe, módulo, docstring).

```bash
aptdata system info my_pipeline
aptdata system info my_pipeline --json
```

### `aptdata system validate NAME`

Instancia o sistema e compila todos os seus fluxos sem executar.

```bash
aptdata system validate my_pipeline
```

---

## `aptdata plugin`

Gerencia e inspeciona plugins registrados (conectores, leitores, escritores).

### `aptdata plugin list [--json]`

Lista todos os conectores (plugins) registrados.

```bash
aptdata plugin list
aptdata plugin list --json
```

### `aptdata plugin inspect NAME [--json]`

Exibe o schema de argumentos (construtor Pydantic) de um plugin.

```bash
aptdata plugin inspect csv_reader
aptdata plugin inspect csv_reader --json
```

### `aptdata plugin preview READER [--limit N]`

Executa um dataset/plugin leitor e exibe as primeiras *N* linhas reais (default: 5).

```bash
aptdata plugin preview csv_reader --limit 10
```

### `aptdata plugin load MODULE_PATH`

Importa dinamicamente um módulo Python (útil para descoberta e registro de plugins manuais via CLI).

```bash
aptdata plugin load my_package.plugins
```

---

## `aptdata config`

Gerencia configurações declarativas de pipeline em YAML.

### `aptdata config validate PATH`

Faz o *parse* e valida um arquivo de configuração YAML.

```bash
aptdata config validate pipeline.yaml
```

### `aptdata config init [--output PATH]`

Gera um *template* inicial de arquivo `aptdata.yaml`.

```bash
aptdata config init
aptdata config init --output my_pipeline.yaml
```

### `aptdata config show PATH`

Exibe o arquivo YAML carregado com substituições de ambiente aplicadas e sintaxe destacada.

```bash
aptdata config show pipeline.yaml
```

### `aptdata config run PATH [--env ENV]`

Carrega a configuração YAML, registra os sistemas ativados e os executa de acordo com o ambiente.

```bash
aptdata config run pipeline.yaml
aptdata config run pipeline.yaml --env prod
```

---

## `aptdata telemetry`

Inspeciona a configuração de telemetria baseada em OpenTelemetry.

### `aptdata telemetry status [--json]`

Exibe o status da configuração do OpenTelemetry e qual o provedor de rastreamento (tracer) está ativo.

```bash
aptdata telemetry status
aptdata telemetry status --json
```

### `aptdata telemetry export [--format json]`

Esvazia o buffer em memória e exporta rastreamentos/métricas coletadas para o *exporter* ativo (ou stdout via JSON).

```bash
aptdata telemetry export
aptdata telemetry export --format json
```

---

## `aptdata interactive`

Inicia o assistente interativo guiado (Wizard Menu).

```bash
aptdata interactive
```

Consulte [Assistente Interativo da CLI](cli-interactive.md) para documentação completa.

---

## App module

::: aptdata.cli.app
    options:
      members:
        - run
        - monitor
