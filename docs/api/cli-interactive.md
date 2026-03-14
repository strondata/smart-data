# Assistente Interativo da CLI

O comando `aptdata interactive` inicia um assistente guiado baseado em menus que
expõe todos os recursos do framework sem a necessidade de decorar as
árvores de comandos.

---

## Iniciando o assistente

```bash
aptdata interactive
```

O assistente utiliza [questionary](https://github.com/tmbo/questionary) para
prompts interativos caso ele esteja instalado. O sistema faz *fallback* gracioso
para as funções `typer.prompt()` / `typer.confirm()` caso o `questionary` não
esteja disponível.

---

## Menu Principal

```
What would you like to do?
  🚀 Run a registered system
  📋 List systems / plugins
  🔍 Inspect a plugin
  📝 Config (validate / run YAML)
  🏗️  Scaffold a new project
  ⚙️  Telemetry status
  ❌ Exit
```

---

## Fluxos do Assistente

### 🚀 Execução (Run)

1. Seleciona um sistema registrado no *Registry*.
2. Escolhe o ambiente: `dev`, `staging` ou `prod`.
3. Confirma a simulação (*dry-run*) (yes → apenas compila, no → chama o `run()`).
4. Executa e exibe os logs ricos do `Rich` em tempo real.

### 📋 Listagem (List)

1. Escolhe o que listar: Sistemas, Leitores, Escritores ou Todos.
2. Visualiza a saída formatada em tabela rica.
3. Permite a inspeção imediata de um item ao final.

### 🔍 Inspeção (Inspect)

1. Seleciona um plugin entre os registrados.
2. Exibe o schema de argumentos Pydantic para instanciação do plugin.

### 📝 Configuração (Config)

1. Escolhe: Carregar um YAML existente ou gerar um novo arquivo de base.
2. Valida a sintaxe (exibe erros detalhados de esquema).
3. Pré-visualiza o YAML final carregado na tela.
4. Opção de execução automática e sequencial.

### 🏗️ Andaimes (Scaffold)

1. Recebe o nome do novo projeto.
2. Escolhe o *template*: `hello-world`, `medallion`, `rag-ingestion`, `data-quality-test`.
3. Informa o diretório destino (default: `.`).
4. Inicializa o pacote, configura e exibe *success*.

### ⚙️ Telemetria (Telemetry)

1. Exibe o *status* do provedor do OpenTelemetry.
2. Possibilidade opcional de enviar o buffer das métricas acumuladas.

---

## Configuração

O *wizard* reaproveita internamente as mesmas abstrações das flags de linha
de comando normais, o que assegura compatibilidade exata na visualização.

### Desabilitando o Questionary

Se for preciso forçar menus básicos (*plain prompts*) para terminais severamente
limitados sem usar o `questionary`, basta desinstalá-lo do seu ambiente:

```bash
pip uninstall questionary
```

O assistente cairá no *fallback* automaticamente usando a função `typer.prompt()`.
