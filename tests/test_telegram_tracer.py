"""Tests for aptdata.transports.telegram_tracer — rastreio Telegram.

Gap do PR4 (renome viz→studio): o plano original pedia que o
``transports/telegram.py`` assinasse o EventBus e postasse um one-liner
num canal próprio a cada ação relevante. Este teste cobre a peça que
faltava (assina o Observer, não o EventBus — ver ``telegram_tracer.py``).

Regra: API do Telegram sempre stubada (nunca rede). Usa ``monkeypatch``
pra fingir o ``requests.post``.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest

from aptdata.observability import Observer
from aptdata.transports.telegram_tracer import (
    MAX_MESSAGE_LEN,
    TelegramTracer,
    format_one_liner,
)

AGENTS_YAML_WITH_TRACING = textwrap.dedent(
    """
    agents:
      zeca:
        name: Zeca
        type: openclaw
        capabilities: [chat]
        weight: 10
        enabled: true
    transports:
      telegram:
        chat_id: '111'
        token_env: TELEGRAM_BOT_TOKEN
        tracing:
          enabled: true
          chat_id: '222'
          events: [app.started, pipeline.error]
    """
)

AGENTS_YAML_DISABLED = textwrap.dedent(
    """
    agents:
      zeca:
        name: Zeca
        type: openclaw
        capabilities: [chat]
        weight: 10
        enabled: true
    transports:
      telegram:
        chat_id: '111'
        token_env: TELEGRAM_BOT_TOKEN
        tracing:
          enabled: false
    """
)

AGENTS_YAML_REUSE_CHAT = textwrap.dedent(
    """
    agents:
      zeca:
        name: Zeca
        type: openclaw
        capabilities: [chat]
        weight: 10
        enabled: true
    transports:
      telegram:
        chat_id: '111'
        token_env: TELEGRAM_BOT_TOKEN
        tracing:
          enabled: true
    """
)


# ---------------------------------------------------------------------------
# format_one_liner (pure — sem rede)
# ---------------------------------------------------------------------------


class TestFormatOneLiner:
    def test_app_started_studio(self):
        text = format_one_liner(
            "app.started", {"app": "studio", "host": "0.0.0.0", "port": 4570}
        )
        assert text is not None
        assert "studio" in text
        assert "0.0.0.0:4570" in text

    def test_app_started_generic(self):
        text = format_one_liner("app.started", {"app": "telegram"})
        assert text is not None
        assert "telegram" in text

    def test_pipeline_error(self):
        text = format_one_liner(
            "pipeline.error", {"pipeline": "carga", "error": "boom"}
        )
        assert text is not None
        assert "carga" in text
        assert "boom" in text

    def test_pipeline_error_long_truncates(self):
        long_err = "x" * 500
        text = format_one_liner("pipeline.error", {"pipeline": "p", "error": long_err})
        assert text is not None
        # Trunca em ~140 chars (dentro do format_one_liner), antes do MAX_MESSAGE_LEN
        assert len(text) < len(long_err)

    def test_agent_dispatch_failure(self):
        text = format_one_liner("agent.dispatch", {"ok": False}, agent_id="darwin")
        assert text is not None
        assert "darwin" in text

    def test_agent_dispatch_success_no_trace(self):
        """Dispatch bem-sucedido não gera rastreio (silencioso)."""
        text = format_one_liner("agent.dispatch", {"ok": True}, agent_id="darwin")
        assert text is None

    def test_agent_response_failure(self):
        text = format_one_liner(
            "agent.response", {"ok": False, "error": "timeout"}, agent_id="zeca"
        )
        assert text is not None
        assert "zeca" in text
        assert "timeout" in text

    def test_permission_requested(self):
        text = format_one_liner(
            "permission.requested", {"decision_id": "dec1"}, agent_id="zeca"
        )
        assert text is not None
        assert "dec1" in text

    def test_permission_resolved_with_choice(self):
        text = format_one_liner(
            "permission.resolved", {"choice": "ondina"}, agent_id=None
        )
        assert text is not None
        assert "ondina" in text

    def test_routing_decision_no_trace_by_default(self):
        """routing.decision não gera rastreio por padrão (muito ruidoso)."""
        text = format_one_liner("routing.decision", {"mode": "skill"})
        assert text is None

    def test_unknown_kind_returns_none(self):
        assert format_one_liner("unknown.event", {}) is None


# ---------------------------------------------------------------------------
# TelegramTracer.from_config / from_agents_file (factory, sem rede)
# ---------------------------------------------------------------------------


class TestFromConfig:
    def test_enabled_with_token_and_chat(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "FAKE:TOKEN")
        cfg = {"enabled": True, "chat_id": "222"}
        tracer = TelegramTracer.from_config(cfg)
        assert tracer is not None
        assert tracer.chat_id == "222"
        assert "app.started" in tracer.events
        assert "pipeline.error" in tracer.events

    def test_disabled_returns_none(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "FAKE:TOKEN")
        tracer = TelegramTracer.from_config({"enabled": False})
        assert tracer is None

    def test_missing_token_returns_none(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        tracer = TelegramTracer.from_config({"enabled": True, "chat_id": "222"})
        assert tracer is None

    def test_missing_chat_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "FAKE:TOKEN")
        tracer = TelegramTracer.from_config({"enabled": True}, default_chat_id="111")
        assert tracer is not None
        assert tracer.chat_id == "111"

    def test_missing_chat_no_default_returns_none(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "FAKE:TOKEN")
        tracer = TelegramTracer.from_config({"enabled": True})
        assert tracer is None

    def test_custom_events_override(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "FAKE:TOKEN")
        tracer = TelegramTracer.from_config(
            {"enabled": True, "chat_id": "222", "events": ["app.started"]}
        )
        assert tracer is not None
        assert tracer.events == ("app.started",)

    def test_custom_token_env(self, monkeypatch):
        monkeypatch.setenv("DARWIN_TRACE_TOKEN", "FAKE:DARWIN")
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        tracer = TelegramTracer.from_config(
            {"enabled": True, "chat_id": "222", "token_env": "DARWIN_TRACE_TOKEN"}
        )
        assert tracer is not None

    def test_empty_config_returns_none(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "FAKE:TOKEN")
        assert TelegramTracer.from_config({}) is None
        assert TelegramTracer.from_config(None) is None  # type: ignore[arg-type]


class TestFromAgentsFile:
    def test_loads_tracing_config(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "FAKE:TOKEN")
        p = tmp_path / "agents.yaml"
        p.write_text(AGENTS_YAML_WITH_TRACING, encoding="utf-8")
        tracer = TelegramTracer.from_agents_file(str(p))
        assert tracer is not None
        assert tracer.chat_id == "222"  # explicit tracing.chat_id
        assert "app.started" in tracer.events
        assert "pipeline.error" in tracer.events

    def test_disabled_in_file_returns_none(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "FAKE:TOKEN")
        p = tmp_path / "agents.yaml"
        p.write_text(AGENTS_YAML_DISABLED, encoding="utf-8")
        tracer = TelegramTracer.from_agents_file(str(p))
        assert tracer is None

    def test_reuses_transport_chat_id_when_tracing_chat_id_absent(
        self, tmp_path: Path, monkeypatch
    ):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "FAKE:TOKEN")
        p = tmp_path / "agents.yaml"
        p.write_text(AGENTS_YAML_REUSE_CHAT, encoding="utf-8")
        tracer = TelegramTracer.from_agents_file(str(p))
        assert tracer is not None
        assert tracer.chat_id == "111"  # fallback to transports.telegram.chat_id

    def test_missing_file_returns_none(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "FAKE:TOKEN")
        assert TelegramTracer.from_agents_file("/nope/agents.yaml") is None

    def test_none_path_returns_none(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "FAKE:TOKEN")
        assert TelegramTracer.from_agents_file(None) is None

    def test_malformed_yaml_returns_none(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "FAKE:TOKEN")
        p = tmp_path / "agents.yaml"
        p.write_text("agents: [this is not valid yaml: {[", encoding="utf-8")
        # Não explode — retorna None (silêncio best-effort)
        assert TelegramTracer.from_agents_file(str(p)) is None


# ---------------------------------------------------------------------------
# install / uninstall + on_event (com Observer real + requests stub)
# ---------------------------------------------------------------------------


class TestInstallUnsubscribe:
    @pytest.fixture(autouse=True)
    def _reset_observer(self):
        Observer.reset()
        yield
        Observer.reset()

    def test_install_registers_subscriber(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "FAKE:TOKEN")
        tracer = TelegramTracer(chat_id="222", token="FAKE:TOKEN")
        assert not tracer.installed
        tracer.install()
        assert tracer.installed
        # Observer tem o subscriber na lista
        assert tracer.on_event in Observer.get()._subscribers

    def test_install_is_idempotent(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "FAKE:TOKEN")
        tracer = TelegramTracer(chat_id="222", token="FAKE:TOKEN")
        tracer.install()
        tracer.install()  # segundo install não duplica
        assert Observer.get()._subscribers.count(tracer.on_event) == 1

    def test_uninstall_removes_subscriber(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "FAKE:TOKEN")
        tracer = TelegramTracer(chat_id="222", token="FAKE:TOKEN")
        tracer.install()
        tracer.uninstall()
        assert not tracer.installed
        assert tracer.on_event not in Observer.get()._subscribers

    def test_uninstall_without_install_is_noop(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "FAKE:TOKEN")
        tracer = TelegramTracer(chat_id="222", token="FAKE:TOKEN")
        # Não explode
        tracer.uninstall()
        assert not tracer.installed


class TestOnEvent:
    """End-to-end: Observer.emit -> subscriber -> requests.post (stub)."""

    @pytest.fixture(autouse=True)
    def _reset_observer(self):
        Observer.reset()
        yield
        Observer.reset()

    @pytest.fixture()
    def stub_posts(self, monkeypatch):
        """Stub requests.post no módulo do tracer; captura todas as chamadas."""
        posts: list[dict[str, Any]] = []

        class FakeResp:
            status_code = 200
            text = '{"ok":true}'

        def fake_post(url, json=None, timeout=None):
            posts.append({"url": url, "json": json, "timeout": timeout})
            return FakeResp()

        # requests é importado lazy dentro de _post — patchear no sys.modules
        import sys

        class FakeRequests:
            post = staticmethod(fake_post)

        monkeypatch.setitem(sys.modules, "requests", FakeRequests)
        return posts

    def test_emit_routes_to_tracer(self, stub_posts, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "FAKE:TOKEN")
        tracer = TelegramTracer(chat_id="222", token="FAKE:TOKEN")
        tracer.install()

        Observer.get().emit(
            "app.started", {"app": "studio", "host": "0.0.0.0", "port": 4570}
        )

        assert len(stub_posts) == 1
        call = stub_posts[0]
        assert call["json"]["chat_id"] == "222"
        assert "studio" in call["json"]["text"]
        assert "0.0.0.0:4570" in call["json"]["text"]

    def test_unrelated_kind_does_not_post(self, stub_posts, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "FAKE:TOKEN")
        tracer = TelegramTracer(chat_id="222", token="FAKE:TOKEN")
        tracer.install()

        Observer.get().emit("routing.decision", {"mode": "skill"})

        # routing.decision não está em DEFAULT_EVENTS — não posta
        assert stub_posts == []

    def test_filtered_events_custom(self, stub_posts, monkeypatch):
        """Tracer com events custom só posta os seus."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "FAKE:TOKEN")
        tracer = TelegramTracer(
            chat_id="222", token="FAKE:TOKEN", events=("pipeline.error",)
        )
        tracer.install()

        # app.started está nos DEFAULT_EVENTS mas não neste tracer
        Observer.get().emit("app.started", {"app": "telegram"})
        assert stub_posts == []

        Observer.get().emit("pipeline.error", {"pipeline": "p", "error": "x"})
        assert len(stub_posts) == 1

    def test_post_failure_does_not_propagate(self, monkeypatch):
        """No-throw: requests.post explodindo não derruba o emit."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "FAKE:TOKEN")
        tracer = TelegramTracer(chat_id="222", token="FAKE:TOKEN")
        tracer.install()

        import sys

        class ExplodingRequests:
            @staticmethod
            def post(url, json=None, timeout=None):
                raise ConnectionError("boom")

        monkeypatch.setitem(sys.modules, "requests", ExplodingRequests)

        # Não explode — Observer.emit() é no-throw
        Observer.get().emit("app.started", {"app": "studio", "host": "h", "port": 1})

    def test_message_truncated_at_max_len(self, stub_posts, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "FAKE:TOKEN")
        # Força format_one_liner a retornar texto > MAX_MESSAGE_LEN pra exercitar
        # o truncamento no nível do _post (não no format_one_liner, que já corta).
        long_text = "z" * (MAX_MESSAGE_LEN + 100)
        monkeypatch.setattr(
            "aptdata.transports.telegram_tracer.format_one_liner",
            lambda k, p, agent_id=None: long_text,
        )
        tracer = TelegramTracer(chat_id="222", token="FAKE:TOKEN")
        tracer.install()

        Observer.get().emit("app.started", {"app": "x"})

        assert len(stub_posts) == 1
        text = stub_posts[0]["json"]["text"]
        assert len(text) <= MAX_MESSAGE_LEN
        assert text.endswith("…")


# ---------------------------------------------------------------------------
# Observer.subscribe / unsubscribe (pub-sub direto, sem tracer)
# ---------------------------------------------------------------------------


class TestObserverSubscribe:
    @pytest.fixture(autouse=True)
    def _reset_observer(self):
        Observer.reset()
        yield
        Observer.reset()

    def test_subscriber_receives_emissions(self, monkeypatch):
        calls: list[tuple[str, dict, str | None]] = []

        def cb(kind, payload, agent_id):
            calls.append((kind, payload, agent_id))

        Observer.get().subscribe(cb)
        Observer.get().emit("app.started", {"app": "x"})
        assert len(calls) == 1
        assert calls[0][0] == "app.started"
        assert calls[0][1] == {"app": "x"}
        assert calls[0][2] is None

    def test_agent_id_passed_through(self):
        calls: list[str | None] = []

        def cb(kind, payload, agent_id):
            calls.append(agent_id)

        Observer.get().subscribe(cb)
        Observer.get().emit("agent.dispatch", {}, agent_id="zeca")
        assert calls == ["zeca"]

    def test_unsubscribe_stops_callbacks(self):
        calls: list[str] = []

        def cb(kind, payload, agent_id):
            calls.append(kind)

        Observer.get().subscribe(cb)
        Observer.get().emit("app.started", {})
        Observer.get().unsubscribe(cb)
        Observer.get().emit("app.started", {})
        # Só a primeira emissão chegou
        assert calls == ["app.started"]

    def test_unsubscribe_without_subscribe_is_noop(self):
        def cb(kind, payload, agent_id):
            pass

        Observer.get().unsubscribe(cb)  # não explode

    def test_multiple_subscribers_all_receive(self):
        a: list[str] = []
        b: list[str] = []

        def cb_a(kind, payload, agent_id):
            a.append(kind)

        def cb_b(kind, payload, agent_id):
            b.append(kind)

        Observer.get().subscribe(cb_a)
        Observer.get().subscribe(cb_b)
        Observer.get().emit("app.started", {})
        assert a == ["app.started"]
        assert b == ["app.started"]

    def test_subscriber_exception_does_not_propagate(self):
        """No-throw: callback explodindo não derruba o emit nem próximos."""
        a_calls: list[str] = []
        b_calls: list[str] = []

        def cb_a_explode(kind, payload, agent_id):
            a_calls.append(kind)
            raise RuntimeError("boom")

        def cb_b(kind, payload, agent_id):
            b_calls.append(kind)

        Observer.get().subscribe(cb_a_explode)
        Observer.get().subscribe(cb_b)
        # Não explode — e o segundo subscriber ainda recebe
        Observer.get().emit("app.started", {})
        assert a_calls == ["app.started"]
        assert b_calls == ["app.started"]

    def test_disabled_observer_skips_subscribers(self, monkeypatch):
        """APTDATA_OBS_DISABLED=1 desliga tudo — subscribers nem são chamados."""
        monkeypatch.setenv("APTDATA_OBS_DISABLED", "1")
        calls: list[str] = []

        def cb(kind, payload, agent_id):
            calls.append(kind)

        Observer.get().subscribe(cb)
        Observer.get().emit("app.started", {})
        assert calls == []
