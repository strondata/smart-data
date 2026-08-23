"""Servidor de leitura do aptdata studio (stdlib http.server, zero deps).

Endpoints:
- ``GET /``                 → frontend (static/index.html)
- ``GET /api/agents``       → registry (specs) — rápido, sem health
- ``GET /api/health``       → {id: "up"|"down"|"disabled"|"unknown"} (best-effort)
- ``GET /api/route?text=``  → decisão do Router para um prompt (503 se o
  router estiver indisponível ou falhar)
- ``GET /api/observability``→ resumo do event store (``Observer.summary()``)
- ``GET /api/events``       → **SSE** ao vivo do traço (``?backlog=N`` para
  reemitir os últimos N eventos ao conectar)
"""

from __future__ import annotations

import json
import mimetypes
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

STATIC_DIR = Path(__file__).parent / "static"
ENV_VAR = "APTDATA_AGENTS_FILE"
DEFAULT_FILE = "agents.yaml"


def _resolve_agents_file(file: str | None) -> Path:
    """Locate ``agents.yaml``: --file, env var, ``.aptdata/`` dotdir, or CWD.

    ADR-002 §2.2: ``.aptdata/agents.yaml`` wins over the legacy root file.
    """
    if file:
        return Path(file).expanduser()
    env_value = os.getenv(ENV_VAR)
    if env_value:
        return Path(env_value).expanduser()
    # ADR-002 §2.2: prefer the .aptdata/ dotdir over the legacy root file.
    from aptdata.config.loader import locate_project_optional  # noqa: PLC0415

    project = locate_project_optional()
    if project is not None and project.agents_yaml.is_file():
        return project.agents_yaml
    return Path(DEFAULT_FILE)


def _health_str(value: object) -> str:
    """Normaliza AgentHealth (enum) para string amigável ao front."""
    return str(getattr(value, "value", getattr(value, "name", value))).lower()


class StudioState:
    """Carrega registry/router do agents.yaml, recarregando se o arquivo mudar."""

    def __init__(self, agents_file: str | None):
        self.path = _resolve_agents_file(agents_file)
        self._mtime: float | None = None
        self._registry = None
        self._router = None
        self._lock = threading.Lock()

    def _maybe_reload(self):
        """Recarrega registry+router se o arquivo mudou.

        Serializado por lock (o servidor é thread-per-request): constrói os
        objetos novos localmente e só então publica os dois juntos — leitores
        concorrentes nunca veem registry novo com router velho.
        """
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            return
        with self._lock:
            if mtime == self._mtime and self._registry is not None:
                return
            from aptdata.agents import AgentRegistry, Router  # lazy

            registry = AgentRegistry.from_yaml(self.path)
            try:
                router = Router.from_yaml(self.path)
            except Exception:
                router = None
            self._registry = registry
            self._router = router
            self._mtime = mtime

    def agents(self) -> list[dict]:
        self._maybe_reload()
        if self._registry is None:
            return []
        rows = []
        for s in self._registry.specs(include_disabled=True):
            rows.append(
                {
                    "id": s.id,
                    "name": s.name,
                    "type": s.type,
                    "location": s.location,
                    "role": s.role,
                    "model": s.model,
                    "enabled": s.enabled,
                    "weight": s.weight,
                    "capabilities": list(s.capabilities),
                }
            )
        rows.sort(key=lambda r: (not r["enabled"], r["id"]))
        return rows

    def health(self) -> dict[str, str]:
        self._maybe_reload()
        if self._registry is None:
            return {}
        out = {}
        for s in self._registry.specs(include_disabled=True):
            try:
                out[s.id] = _health_str(self._registry.get(s.id).health())
            except Exception:
                out[s.id] = "unknown"
        return out

    def route(self, text: str) -> dict:
        self._maybe_reload()
        if self._router is None:
            return {"error": "router indisponível"}
        try:
            return self._router.route(text).to_dict()
        except Exception as exc:  # pragma: no cover - defensivo
            return {"error": str(exc)}


def _make_handler(state: StudioState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # silencia
            pass

        def _json(self, status: int, data: object):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"

            if path == "/api/agents":
                self._json(200, {"agents": state.agents()})
            elif path == "/api/health":
                self._json(200, {"health": state.health()})
            elif path == "/api/route":
                text = (parse_qs(parsed.query).get("text") or [""])[0]
                decision = state.route(text)
                # falha de roteamento não é sucesso: 503 em vez de 200
                self._json(503 if "error" in decision else 200, decision)
            elif path == "/api/observability":
                self._json(200, _observability())
            elif path == "/api/events":
                self._sse(parsed)
            else:
                self._serve_static(path)

        def _sse(self, parsed):
            """Stream do traço via Server-Sent Events (frontend fino, sem poll).

            Reemite os últimos ``backlog`` eventos ao conectar e segue
            entregando os novos até o cliente desconectar.
            """
            from aptdata.observability import Observer  # lazy

            obs = Observer.get()
            backlog = int((parse_qs(parsed.query).get("backlog") or ["10"])[0])
            cursor = max(0, obs.last_id() - max(0, backlog))

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                while True:
                    cursor, events = obs.since(cursor, limit=100)
                    for event in events:
                        body = json.dumps(event, ensure_ascii=False)
                        self.wfile.write(f"data: {body}\n\n".encode())
                    self.wfile.flush()
                    if not events:
                        time.sleep(0.5)
            except (BrokenPipeError, ConnectionResetError):
                pass  # cliente desconectou

        def _serve_static(self, path: str):
            rel = "index.html" if path == "/" else path.lstrip("/")
            static_root = STATIC_DIR.resolve()
            fp = (STATIC_DIR / rel).resolve()
            # segurança: fora do static → fallback pro index (SPA)
            if static_root != fp and static_root not in fp.parents:
                fp = static_root / "index.html"
            if not fp.is_file():
                fp = static_root / "index.html"
            if not fp.is_file():
                self._json(404, {"error": "not found"})
                return
            ctype, _ = mimetypes.guess_type(str(fp))
            data = fp.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype or "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return Handler


def _observability() -> dict:
    """Resumo do event store (Observer.summary()); nunca derruba o endpoint."""
    try:
        from aptdata.observability import Observer  # lazy

        return Observer.get().summary()
    except Exception as exc:  # noqa: BLE001 - studio é leitor, degrada com graça
        return {"available": False, "error": str(exc)}


def serve(agents_file: str | None = None, host: str = "0.0.0.0", port: int = 4570):
    state = StudioState(agents_file)
    httpd = ThreadingHTTPServer((host, port), _make_handler(state))
    # Rastreio Telegram (canal próprio) — gap do PR4. Best-effort, nunca derruba.
    try:
        from aptdata.transports.telegram_tracer import TelegramTracer  # noqa: PLC0415

        tracer = TelegramTracer.from_agents_file(agents_file)
        if tracer is not None:
            tracer.install()
    except Exception:  # noqa: BLE001
        pass
    try:  # traço de subida de app é best-effort
        from aptdata.observability import Observer  # noqa: PLC0415

        Observer.get().emit(
            "app.started", {"app": "studio", "host": host, "port": port}
        )
    except Exception:  # noqa: BLE001 - façade quebrado não pode vazar
        pass
    print(f"🔭 aptdata studio em http://{host}:{port} (agents: {state.path})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
