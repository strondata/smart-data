"""CLI tests for ``aptdata monitor`` — TTY guard (regression).

O ``monitor`` abre um TUI Textual que crasha sujo (``ParseError: end of
file reached`` + exit 0 enganoso) quando stdin/stdout não são TTY. Este
teste garante que o guard aborta graciosamente com JSON no stderr e
exit 1, sem traceback.

Segue o padrão dos demais test_cli_*: CliRunner (mix_stderr=True —
stderr funde no stdout, então o JSON aparece em ``r.stdout``).
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from aptdata.cli.app import app

runner = CliRunner()


class TestMonitorHelp:
    def test_help_exits_zero(self):
        r = runner.invoke(app, ["monitor", "--help"])
        assert r.exit_code == 0
        assert "monitor" in r.stdout.lower()
        assert "--refresh" in r.stdout


class TestMonitorTTYGuard:
    """CliRunner usa pipes (não TTY) → o guard dispara sempre.

    Como ``mix_stderr=True`` (default do repo), o JSON do ``_emit(error=True)``
    aparece em ``r.stdout``, não em ``r.stderr``.
    """

    def test_no_tty_aborts_with_json_error(self):
        r = runner.invoke(app, ["monitor"])
        # exit 1 = runtime error (não 0 = traceback enganoso, não 2 = uso)
        assert r.exit_code == 1
        payload = json.loads(r.stdout)
        assert payload["event"] == "monitor.error"
        assert "TTY" in payload["error"] or "terminal" in payload["error"].lower()

    def test_no_tty_aborts_with_refresh_option(self):
        """O guard dispara antes de instanciar MonitorApp, ignorando --refresh."""
        r = runner.invoke(app, ["monitor", "--refresh", "0.5"])
        assert r.exit_code == 1
        payload = json.loads(r.stdout)
        assert payload["event"] == "monitor.error"

    def test_no_traceback_in_output(self):
        """Regression: antes do fix, stderr tinha um traceback textual sujo."""
        r = runner.invoke(app, ["monitor"])
        assert "Traceback" not in r.stdout
        assert "ParseError" not in r.stdout


class TestMonitorGuardContract:
    """Contrato estrutural do guard — não depende de TUI real."""

    def test_error_event_is_machine_readable(self):
        """Orquestradores/CI podem parsear a falha (motivo do fix)."""
        r = runner.invoke(app, ["monitor"])
        # JSON válido + chave canônica do evento
        payload = json.loads(r.stdout)
        assert payload["event"] == "monitor.error"
        assert isinstance(payload["error"], str) and len(payload["error"]) > 10
        # trace_id sempre presente (padrão _emit do CLI)
        assert "trace_id" in payload
