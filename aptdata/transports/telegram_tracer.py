"""Telegram tracer — one-liner de rastreio num canal próprio do Telegram.

Gap do PR4 (renome viz→studio): o plano original pedia que o
``transports/telegram.py`` assinasse o EventBus e postasse um one-liner
num canal próprio a cada ação relevante (PR/deploy/modificação). Este
módulo entrega a peça que faltava — mas assina o :class:`Observer`
(que cobre mais eventos: routing.decision, agent.dispatch, app.started,
pipeline.error, etc.) ao invés do EventBus (só lifecycle de componentes).

Design
------
* Configuração vem de ``.aptdata/agents.yaml`` (seção
  ``transports.telegram.tracing``) — nunca do repo: token via env,
  chat_id pode ser string literal (não é segredo, mas é separado do
  chat principal).
* Instanciado uma vez no boot do CLI/studio (``install``). Vira
  subscriber do :class:`Observer` — recebe ``(kind, payload, agent_id)``.
* Filtra por lista de eventos (default: ``app.started``, ``pipeline.error``,
  ``agent.response`` com ``ok=False``). Roteamento é muito ruidoso pra
  rastrear por padrão.
* Best-effort: erros de rede/log são engolidos (contrato no-throw herdado
  do Observer). O tracer nunca derruba o pipeline.
* Lazy: ``requests`` é importado só no primeiro post (mesmo padrão do
  :class:`TelegramTransport`).

Config
------
``.aptdata/agents.yaml``::

    transports:
      telegram:
        chat_id: '<chat principal>'
        token_env: TELEGRAM_BOT_TOKEN
        tracing:
          enabled: true
          chat_id: '<chat rastreio>'    # default = chat_id principal
          events: [app.started, pipeline.error]   # default: ver DEFAULT_EVENTS
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

#: Eventos rastreados por padrão. Roteamento (``routing.decision``) fica
#: de fora — é muito ruidoso. ``agent.dispatch``/``agent.response`` são
#: includidos só quando falham (``ok=False``), pra evitar flood.
DEFAULT_EVENTS: tuple[str, ...] = (
    "app.started",
    "pipeline.error",
)

#: Máximo de caracteres por one-liner (Telegram aceita 4096, mas rastreio
#: é one-liner curto — cortar em 280 pra manter legível no celular).
MAX_MESSAGE_LEN = 280

API_BASE = "https://api.telegram.org"
DEFAULT_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"


# ---------------------------------------------------------------------------
# Formatação (pure function — testável sem rede)
# ---------------------------------------------------------------------------


def format_one_liner(
    kind: str,
    payload: dict[str, Any],
    agent_id: str | None = None,
) -> str | None:
    """Converte ``(kind, payload, agent_id)`` num one-liner humano.

    Retorna ``None`` quando o evento não gera rastreio (silêncio explícito
    — não é erro). Quem chama decide se posta ou não.

    Tom (persona APTData, ``docs/personas/APTData.md``): feminino, suave,
    muito explicativo, PT-BR informal.
    """
    if kind == "app.started":
        app = payload.get("app", "?")
        if app == "studio":
            host = payload.get("host", "?")
            port = payload.get("port", "?")
            return f"🔭 studio subiu em http://{host}:{port}"
        return f"🔭 {app} subiu"

    if kind == "pipeline.error":
        pipeline = payload.get("pipeline", "?")
        error = str(payload.get("error", "erro desconhecido"))
        return f"❌ pipeline `{pipeline}` falhou: {error[:140]}"

    if kind == "agent.dispatch" and payload.get("ok") is False:
        agent = agent_id or payload.get("agent_id", "?")
        return f"❌ dispatch pro `{agent}` falhou"

    if kind == "agent.response" and payload.get("ok") is False:
        agent = agent_id or payload.get("agent_id", "?")
        error = str(payload.get("error", "erro"))
        return f"❌ `{agent}` respondeu com erro: {error[:140]}"

    if kind == "permission.requested":
        decision_id = payload.get("decision_id", "?")
        agent = payload.get("agent_id", agent_id or "?")
        return f"⏳ confirmando roteamento p/ `{agent}` (decisão {decision_id})"

    if kind == "permission.resolved":
        agent = payload.get("agent_id", agent_id or "?")
        choice = payload.get("choice")
        if choice:
            return f"✅ decisão confirmada → `{choice}`"
        return f"✅ decisão confirmada p/ `{agent}`"

    return None


# ---------------------------------------------------------------------------
# Tracer
# ---------------------------------------------------------------------------


class TelegramTracer:
    """Assina o :class:`Observer` e posta one-liners num canal Telegram.

    Veja ``transports/telegram_tracer.py`` docstring pra config. Uso típico::

        from aptdata.transports.telegram_tracer import TelegramTracer

        tracer = TelegramTracer.from_agents_file("agents.yaml")
        if tracer is not None:
            tracer.install()   # vira subscriber do Observer
    """

    def __init__(
        self,
        *,
        chat_id: str,
        token: str,
        events: tuple[str, ...] = DEFAULT_EVENTS,
        api_base: str = API_BASE,
    ):
        if not chat_id:
            raise ValueError("TelegramTracer requer chat_id não-vazio.")
        if not token:
            raise ValueError("TelegramTracer requer token não-vazio.")
        self._chat_id = chat_id
        self._token = token
        self._events = tuple(events)
        self._api_base = api_base
        self._installed = False

    @property
    def installed(self) -> bool:
        return self._installed

    @property
    def chat_id(self) -> str:
        return self._chat_id

    @property
    def events(self) -> tuple[str, ...]:
        return self._events

    # -- factory -------------------------------------------------------------

    @classmethod
    def from_config(
        cls,
        tracing_cfg: dict[str, Any],
        *,
        default_chat_id: str | None = None,
        token_env: str = DEFAULT_TOKEN_ENV,
    ) -> TelegramTracer | None:
        """Constrói um tracer a partir de ``transports.telegram.tracing``.

        Retorna ``None`` quando:
        - ``tracing_cfg`` está vazio/ausente,
        - ``enabled`` é false,
        - token env não está definido,
        - não há chat_id (nem default, nem explícito).

        Não levanta — caller (CLI/studio) decide o que fazer com ``None``.
        """
        if not tracing_cfg:
            return None
        if not tracing_cfg.get("enabled", False):
            return None
        token = os.getenv(tracing_cfg.get("token_env", token_env))
        if not token:
            logger.debug("telegram tracer: token ausente, tracer desativado")
            return None
        chat_id = tracing_cfg.get("chat_id") or default_chat_id
        if not chat_id:
            logger.debug("telegram tracer: sem chat_id (nem default nem explícito)")
            return None
        events = tracing_cfg.get("events")
        if events and isinstance(events, list | tuple):
            events_tuple = tuple(str(e) for e in events)
        else:
            events_tuple = DEFAULT_EVENTS
        return cls(chat_id=chat_id, token=token, events=events_tuple)

    @classmethod
    def from_agents_file(cls, agents_file: str | None) -> TelegramTracer | None:
        """Lê config de um ``agents.yaml`` (opcional) e constrói o tracer.

        Procura ``transports.telegram.tracing`` no arquivo. Se o arquivo
        não existe ou não tem a seção, retorna ``None`` (silêncio).
        """
        if not agents_file:
            return None
        from pathlib import Path  # noqa: PLC0415

        path = Path(agents_file)
        if not path.is_file():
            return None
        try:
            import yaml  # noqa: PLC0415

            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as exc:  # noqa: BLE001
            logger.debug("telegram tracer: falhou ler %s: %s", agents_file, exc)
            return None
        transports = raw.get("transports") or {}
        telegram = transports.get("telegram") or {}
        tracing = telegram.get("tracing") or {}
        default_chat_id = telegram.get("chat_id")
        token_env = telegram.get("token_env", DEFAULT_TOKEN_ENV)
        return cls.from_config(
            tracing, default_chat_id=default_chat_id, token_env=token_env
        )

    # -- Observer subscribe --------------------------------------------------

    def install(self) -> None:
        """Vira subscriber do :class:`Observer` singleton (idempotente)."""
        if self._installed:
            return
        from aptdata.observability import Observer  # noqa: PLC0415

        Observer.get().subscribe(self.on_event)
        self._installed = True
        logger.debug(
            "telegram tracer instalado (chat=%s, events=%s)",
            self._chat_id,
            self._events,
        )

    def uninstall(self) -> None:
        """Remove o tracer do Observer (idempotente)."""
        if not self._installed:
            return
        from aptdata.observability import Observer  # noqa: PLC0415

        Observer.get().unsubscribe(self.on_event)
        self._installed = False

    # -- callback Observer ---------------------------------------------------

    def on_event(
        self,
        kind: str,
        payload: dict[str, Any],
        agent_id: str | None = None,
    ) -> None:
        """Callback registrado no :class:`Observer`. No-throw (best-effort)."""
        if kind not in self._events:
            return
        text = format_one_liner(kind, payload, agent_id=agent_id)
        if text is None:
            return
        if len(text) > MAX_MESSAGE_LEN:
            text = text[: MAX_MESSAGE_LEN - 1] + "…"
        try:
            self._post(text)
        except Exception as exc:  # noqa: BLE001 — no-throw, contrator do Observer
            logger.debug("telegram tracer post falhou (%s): %s", kind, exc)

    # -- Telegram API --------------------------------------------------------

    def _post(self, text: str) -> None:
        """POST sendMessage no Telegram. Importa requests lazy."""
        import requests  # noqa: PLC0415

        url = f"{self._api_base}/bot{self._token}/sendMessage"
        resp = requests.post(
            url,
            json={"chat_id": self._chat_id, "text": text},
            timeout=10,
        )
        if resp.status_code >= 400:
            logger.debug(
                "telegram tracer HTTP %d: %s",
                resp.status_code,
                resp.text[:200],
            )


__all__ = [
    "API_BASE",
    "DEFAULT_EVENTS",
    "DEFAULT_TOKEN_ENV",
    "MAX_MESSAGE_LEN",
    "TelegramTracer",
    "format_one_liner",
]
