"""``aptdata setup`` — diagnóstico transparente + configuração guiada.

O setup é o primeiro contato do usuário com o ecossistema: mostra com
transparência o que está pronto (agents.yaml, router, política, Telegram,
observabilidade, studio) e configura o canal Telegram em poucos passos.

Modos:
- ``aptdata setup``            → wizard interativo (questionary/typer).
- ``aptdata setup --check``    → não interativo (CI/painel/agentes), exit 1
  se algum item obrigatório falhar. ``--json`` para máquina.

Segredos NUNCA vão para arquivo: o token do Telegram fica em variável de
ambiente e o agents.yaml guarda apenas o NOME da variável (``token_env``).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import typer
import yaml

from aptdata.cli.interactive import _confirm, _text
from aptdata.cli.rendering.console import SmartConsole

DEFAULT_FILE = "agents.yaml"
ENV_VAR = "APTDATA_AGENTS_FILE"
TOKEN_ENV = "TELEGRAM_BOT_TOKEN"

_STARTER_AGENTS_YAML = """\
# agents.yaml — fonte única do ecossistema multi-agente (aptdata)
agents:
  gandalf:
    name: Gandalf
    type: claude_code
    role: porta_de_entrada
    capabilities: [chat, planning]
    weight: 10
    enabled: true

skills:
  - name: frontend
    keywords: [frontend, tela, pagina, css]
    backend: gandalf

routing:
  dispatch_above: 0.75
  guarded_capabilities: [deploy, ssh, docker, ops]
"""


def _resolve_path(file: str | None) -> Path:
    """Locate ``agents.yaml`` from --file, env var, .aptdata/ dotdir, or CWD.

    ADR-002 §2.2: ``.aptdata/agents.yaml`` wins over the legacy root file.
    """
    if file:
        return Path(file).expanduser()
    env_value = os.getenv(ENV_VAR)
    if env_value:
        return Path(env_value).expanduser()
    from aptdata.config.loader import locate_project_optional  # noqa: PLC0415

    project = locate_project_optional()
    if project is not None and project.agents_yaml.is_file():
        return project.agents_yaml
    return Path(DEFAULT_FILE)


def _telegram_get_me(token: str) -> dict[str, Any]:
    """GET /getMe para validar o token (stubado nos testes)."""
    import requests  # noqa: PLC0415 - lazy

    resp = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
    return resp.json()


# ---------------------------------------------------------------------------
# --check: diagnóstico não interativo
# ---------------------------------------------------------------------------


def run_checks(file: str | None) -> dict[str, Any]:
    """Diagnóstico do setup; itens ``required`` decidem o ``ok`` geral."""
    path = _resolve_path(file)
    checks: list[dict[str, Any]] = []

    def check(cid: str, ok: bool, detail: str, *, required: bool = False) -> None:
        checks.append({"id": cid, "ok": ok, "required": required, "detail": detail})

    raw: dict[str, Any] = {}
    exists = path.is_file()
    check("agents_file", exists, str(path), required=True)

    router_ok, agents_count, skills_count = False, 0, 0
    if exists:
        try:
            from aptdata.agents import AgentRegistry, Router  # noqa: PLC0415

            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            agents_count = len(AgentRegistry.from_yaml(path))
            skills_count = len(Router.from_yaml(path).skills)
            router_ok = agents_count > 0
        except Exception as exc:  # noqa: BLE001 - diagnóstico reporta, não explode
            check("router", False, f"falha ao carregar: {exc}", required=True)
    if exists and router_ok:
        check(
            "router",
            True,
            f"{agents_count} agente(s), {skills_count} skill(s)",
            required=True,
        )
    elif not exists:
        check("router", False, "sem agents.yaml", required=True)

    check(
        "routing_policy",
        bool(raw.get("routing")),
        "bloco routing: presente (thresholds/guardrails)"
        if raw.get("routing")
        else "bloco routing: ausente (defaults em uso)",
    )

    transport = (raw.get("transports") or {}).get("telegram") or {}
    token_env = transport.get("token_env", TOKEN_ENV)
    check(
        "telegram_token",
        bool(os.getenv(token_env)),
        f"env {token_env} {'definida' if os.getenv(token_env) else 'ausente'}",
    )
    check(
        "telegram_transport",
        bool(transport.get("chat_id")),
        "transports.telegram configurado no agents.yaml"
        if transport
        else "transports.telegram ausente (rode `aptdata setup`)",
    )

    # Rastreio Telegram (canal próprio) — gap do PR4. Opcional.
    tracing = transport.get("tracing") or {}
    tracing_chat_id = tracing.get("chat_id") or transport.get("chat_id")
    if tracing.get("enabled") and tracing_chat_id:
        check(
            "telegram_tracing",
            True,
            f"rastreio habilitado p/ {tracing_chat_id}",
        )
    elif tracing.get("enabled"):
        check(
            "telegram_tracing",
            False,
            "tracing.enabled=true mas sem chat_id (deixe tracing.chat_id vazio "
            "p/ reusar transports.telegram.chat_id)",
        )
    else:
        check(
            "telegram_tracing",
            False,
            "rastreio Telegram desativado "
            "(transports.telegram.tracing.enabled=true "
            "p/ postar one-liners num canal próprio)",
        )

    try:
        from aptdata.observability import Observer  # noqa: PLC0415

        summary = Observer.get().summary()
        check("observability", True, f"event store ok ({summary['db']})")
    except Exception as exc:  # noqa: BLE001
        check("observability", False, f"event store indisponível: {exc}")

    static = Path(__file__).resolve().parents[2] / "studio" / "static" / "index.html"
    check("studio", static.is_file(), "frontend do aptdata studio embarcado")

    return {"ok": all(c["ok"] for c in checks if c["required"]), "checks": checks}


# ---------------------------------------------------------------------------
# wizard
# ---------------------------------------------------------------------------


def _wizard(console: SmartConsole, file: str | None) -> None:
    path = _resolve_path(file)
    report = run_checks(file)
    _render_checks(console, report)

    if not path.is_file() and _confirm(
        f"Criar um agents.yaml inicial em {path}?", default=True
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_STARTER_AGENTS_YAML, encoding="utf-8")
        console.success(f"agents.yaml criado em {path}")

    if path.is_file() and _confirm("Configurar o canal Telegram agora?", default=True):
        _wizard_telegram(console, path)

    console.print("\n[bold]Próximos passos[/bold]")
    console.print(f"  aptdata converse 'oi' -f {path}     # conversa headless")
    console.print(f"  aptdata studio -f {path}           # painel + traço ao vivo")
    console.print("  aptdata telegram                     # sobe o bot fino")
    console.print("  aptdata obs tail                     # traço de eventos")


def _wizard_telegram(console: SmartConsole, path: Path) -> None:
    token = os.getenv(TOKEN_ENV)
    if not token:
        console.warning(
            f"Defina a env {TOKEN_ENV} (token do @BotFather) e rode de novo —"
            " o token nunca é gravado em arquivo."
        )
        return
    me = None
    try:
        me = _telegram_get_me(token)
    except Exception as exc:  # noqa: BLE001 - sem rede o setup segue
        console.warning(f"Não consegui validar o token agora ({exc}); seguindo.")
    if me and me.get("ok"):
        console.success(f"Token válido: @{me['result'].get('username', '?')}")
    elif me is not None:
        console.error("Token inválido segundo a API do Telegram.")
        return

    chat_id = _text("Chat ID do canal/grupo (vazio para pular)", default="").strip()
    if not chat_id:
        return
    content = path.read_text(encoding="utf-8")
    if "transports:" in content:
        console.warning(
            "Bloco transports: já existe no agents.yaml — edite-o manualmente."
        )
        return
    block = (
        f"transports:\n  telegram:\n    chat_id: '{chat_id}'\n"
        f"    token_env: {TOKEN_ENV}\n"
    )
    path.write_text(content.rstrip() + "\n\n" + block, encoding="utf-8")
    console.success("transports.telegram gravado no agents.yaml (sem segredos).")


def _render_checks(console: SmartConsole, report: dict[str, Any]) -> None:
    for c in report["checks"]:
        mark = "✅" if c["ok"] else ("❌" if c["required"] else "⚠️ ")
        console.print(f"{mark} {c['id']}: {c['detail']}")
    console.print(
        f"[bold]{'setup ok' if report['ok'] else 'setup incompleto'}[/bold]\n"
    )


# ---------------------------------------------------------------------------
# comando
# ---------------------------------------------------------------------------


def setup_command(
    file: str = typer.Option(None, "--file", "-f", help="Path to agents.yaml."),
    check: bool = typer.Option(
        False, "--check", help="Non-interactive diagnosis (exit 1 when incomplete)."
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit JSON lines."),
) -> None:
    """Diagnose and configure the aptdata ecosystem (agents, Telegram, studio)."""
    console = SmartConsole(json_mode=json_mode)

    if check:
        report = run_checks(file)
        if json_mode:
            print(json.dumps(report, ensure_ascii=False), flush=True)
        else:
            _render_checks(console, report)
        if not report["ok"]:
            raise typer.Exit(1)
        return

    _wizard(console, file)
