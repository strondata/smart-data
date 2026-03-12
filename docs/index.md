---
hide:
  - navigation
  - toc
---

<div align="center" style="margin-top: 40px; margin-bottom: 60px;">

  <h1 style="font-size: 4rem; font-weight: 900; background: -webkit-linear-gradient(45deg, var(--md-primary-fg-color), var(--md-accent-fg-color)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 0;">aptdata</h1>

  <p style="font-size: 1.5rem; color: var(--md-default-fg-color--light); max-width: 700px; margin: 20px auto; line-height: 1.4;">
    O framework declarativo e extensível para construção de pipelines de dados inteligentes.
  </p>

  <p style="font-size: 1.1rem; color: var(--md-default-fg-color--light); max-width: 600px; margin: 0 auto 30px auto;">
    Validação estrita, roteamento dinâmico e integração nativa com IA.
  </p>

  [🚀 Comece Agora](getting-started.md){ .md-button .md-button--primary style="margin-right: 10px;" }
  [🐙 GitHub](https://github.com/strondata/smart-data){ .md-button }

  <br><br>

  [![PyPI Version](https://img.shields.io/pypi/v/aptdata.svg)](https://pypi.org/project/aptdata/)
  [![Python Versions](https://img.shields.io/pypi/pyversions/aptdata.svg)](https://pypi.org/project/aptdata/)
  [![License](https://img.shields.io/github/license/strondata/smart-data.svg)](https://github.com/strondata/smart-data/blob/main/LICENSE)
  [![GitHub Stars](https://img.shields.io/github/stars/strondata/smart-data.svg)](https://github.com/strondata/smart-data/stargazers)

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
