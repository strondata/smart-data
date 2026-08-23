"""Observer — façade best-effort de observabilidade do aptdata.

Contrato (docs/plans/observability.md):
- ``emit()`` NUNCA levanta exceção: telemetria quebrada não derruba negócio.
- Kill-switch: ``APTDATA_OBS_DISABLED=1`` desliga toda a emissão.
- Correlação: ``run_context()`` abre um ``run_id`` (contextvar) herdado por
  toda emissão aninhada — Router → Agent → Task compartilham o mesmo id.

Taxonomia de eventos (kinds):
- ``app.started``          — CLI/studio/MCP subiu
- ``routing.decision``     — RouteDecision completo (o "porquê" da rota)
- ``agent.dispatch``       — prompt saiu para um agente
- ``agent.response``       — resposta (ok, latency_ms, error)
- ``permission.requested`` / ``permission.resolved`` — loop de confirmação
  (usado pelo ConversationEngine)
"""

from __future__ import annotations

import contextlib
import contextvars
import logging
import os
import time
import uuid
from typing import Any

from aptdata.observability.store import ObservabilityStore

logger = logging.getLogger(__name__)

ENV_DISABLED = "APTDATA_OBS_DISABLED"

_current_run: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "aptdata_obs_run", default=None
)


def _disabled() -> bool:
    return os.getenv(ENV_DISABLED, "").lower() in ("1", "true", "yes")


def _current_trace_id() -> str | None:
    """trace_id do span OTel corrente, se houver (mesmo padrão do cli._emit)."""
    try:
        from opentelemetry import trace  # noqa: PLC0415

        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx and ctx.trace_id:
            return format(ctx.trace_id, "032x")
    except Exception:  # pragma: no cover - defensivo
        pass
    return None


class Observer:
    """Singleton fino sobre o :class:`ObservabilityStore`."""

    _instance: Observer | None = None

    def __init__(self, store: ObservabilityStore | None = None):
        self._store = store
        self._subscribers: list[Any] = []  # callbacks (kind, payload, agent_id)

    # -- ciclo de vida --------------------------------------------------------

    @classmethod
    def get(cls) -> Observer:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Descarta o singleton (testes / troca de APTDATA_OBS_DB)."""
        if cls._instance is not None and cls._instance._store is not None:
            with contextlib.suppress(Exception):
                cls._instance._store.close()
        cls._instance = None

    def _ensure_store(self) -> ObservabilityStore:
        if self._store is None:
            self._store = ObservabilityStore()
        return self._store

    # -- pub-sub -------------------------------------------------------------

    def subscribe(self, callback: Any) -> None:
        """Registra *callback(kind, payload, agent_id)* chamada após cada
        emissão persistida. Best-effort: exceções no callback são engolidas
        (não podem quebrar o pipeline nem o próximo subscriber).

        Caso de uso: rastreio Telegram (``TelegramTracer``), sinks externos,
        dashboards live, etc. O callback recebe os mesmos argumentos de
        :meth:`emit` — sem cópia — então não deve mutar ``payload``.
        """
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Any) -> None:
        """Remove *callback* (idempotente — sem erro se não estava registrado)."""
        with contextlib.suppress(ValueError):
            self._subscribers.remove(callback)

    # -- correlação ------------------------------------------------------------

    @staticmethod
    def current_run_id() -> str | None:
        return _current_run.get()

    @contextlib.contextmanager
    def run_context(self, run_id: str | None = None):
        """Abre (ou herda) um run_id para correlacionar as emissões aninhadas."""
        active = _current_run.get()
        if active is not None and run_id is None:
            yield active
            return
        rid = run_id or f"run_{time.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
        token = _current_run.set(rid)
        try:
            yield rid
        finally:
            _current_run.reset(token)

    # -- emissão (no-throw) ------------------------------------------------------

    def emit(
        self,
        kind: str,
        payload: dict[str, Any] | None = None,
        *,
        agent_id: str | None = None,
    ) -> None:
        if _disabled():
            return
        try:
            self._ensure_store().append(
                kind,
                payload,
                run_id=_current_run.get(),
                trace_id=_current_trace_id(),
                agent_id=agent_id,
            )
        except Exception as exc:
            logger.debug("observability emit dropped (%s: %s)", kind, exc)
            return  # store falhou — não notifica subscribers (estado inconsistente)
        # Pub-sub best-effort: cada callback no-throw (engolido aqui).
        for callback in list(self._subscribers):
            try:
                callback(kind, payload or {}, agent_id)
            except Exception as exc:  # noqa: BLE001 — ver docstring de subscribe
                logger.debug("observability subscriber failed (%s: %s)", kind, exc)

    # -- leitura ------------------------------------------------------------------

    def tail(
        self,
        limit: int = 50,
        *,
        kind: str | None = None,
        run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._ensure_store().tail(limit, kind=kind, run_id=run_id)

    def summary(self) -> dict[str, Any]:
        return self._ensure_store().summary()

    def since(
        self, last_id: int = 0, limit: int = 100
    ) -> tuple[int, list[dict[str, Any]]]:
        return self._ensure_store().since(last_id, limit)

    def last_id(self) -> int:
        return self._ensure_store().last_id()
