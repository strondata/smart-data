---
tags:
  - framework
  - pipelines
  - data
hide:
  - navigation
  - toc
---

<div align="center" style="margin-top: 40px; margin-bottom: 60px;">

  <h1 style="font-size: 4rem; font-weight: 900; background: -webkit-linear-gradient(45deg, var(--md-primary-fg-color), var(--md-accent-fg-color)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 0;">aptdata</h1>

  <div style="margin-top: 20px; margin-bottom: 20px;">
    <a href="https://github.com/strondata/smart-data"><img src="https://img.shields.io/github/stars/strondata/smart-data?style=social" alt="GitHub stars"></a>
    <a href="https://pypi.org/project/aptdata/"><img src="https://img.shields.io/pypi/v/aptdata?color=ff6a00&label=PyPI" alt="PyPI version"></a>
    <a href="https://github.com/strondata/smart-data/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/strondata/smart-data/ci.yml?branch=main" alt="Build Status"></a>
  </div>

  <p style="font-size: 1.5rem; color: var(--md-default-fg-color--light); max-width: 700px; margin: 20px auto; line-height: 1.4;">
    O framework declarativo e extensível para construção de pipelines de dados inteligentes.
  </p>

  <p style="font-size: 1.1rem; color: var(--md-default-fg-color--light); max-width: 600px; margin: 0 auto 30px auto;">
    Validação estrita, roteamento dinâmico e integração nativa com IA.
  </p>

  [🚀 Comece Agora](getting-started.md){ .md-button .md-button--primary style="margin-right: 10px;" }
  [🐙 GitHub](https://github.com/strondata/smart-data){ .md-button style="margin-right: 10px;" }
  [▶️ Google Colab](https://colab.research.google.com/github/strondata/smart-data){ .md-button }

</div>

---

## Por que escolher o aptdata?

<div class="grid cards" markdown>

-   :material-shield-check: **Type Safety & Contratos**

    ---

    Interfaces (`IDataset`, `IComponent`) combinadas com a validação em tempo de execução do **Pydantic**. Saiba exatamente o que entra e sai do seu pipeline antes de ir para produção.

-   :material-puzzle: **Agnóstico a Engines**

    ---

    Construa fluxos desacoplados da ferramenta de processamento. Use wrappers para Pandas ou escale nativamente para clusters PySpark sem alterar a arquitetura do fluxo.

-   :material-robot-outline: **Pronto para Agentes (AI Ready)**

    ---

    Integração nativa com IA. Construa roteamentos dinâmicos avançados baseados em predicados de metadados e orquestre agentes inteligentes diretamente no seu fluxo de dados.

-   :material-graph: **Rastreabilidade Completa**

    ---

    Monitore a linhagem dos dados e o estado de cada nó em tempo real. Identifique gargalos e depure falhas com metadados ricos injetados a cada etapa do DAG.

</div>
