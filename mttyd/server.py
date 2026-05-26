"""mttyd HTTP server.

Serves two things:
  GET /term/{ports}           HTML wrapper that connects xterm.js to ttyd. Ports
                              may be a single integer ("7681") OR a comma-
                              separated list ("7681,7691,7692") for multi-tab.
  GET /api/term/history?port  Ranked bash_history suggestions for the command bar

Configuration is a YAML file with a `ports` map:
    ports:
      7681:
        history: { file: ~/.bash_history }
      7682:
        history: { ssh: user@remote-host, path: ~/.bash_history }
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from .history import rank_commands, read_history

HERE = Path(__file__).parent
TEMPLATE = (HERE / "static" / "term.html").read_text()
CACHE_TTL = 300


def load_config(path: str | None) -> dict[int, dict[str, Any]]:
    """Load the ports config. Returns {port_int: source_dict}."""
    if not path:
        return {}
    data = yaml.safe_load(Path(path).read_text()) or {}
    return {int(k): v for k, v in (data.get("ports") or {}).items()}


def create_app(config_path: str | None = None) -> FastAPI:
    app = FastAPI(title="mttyd", version="0.1.0")
    ports = load_config(config_path)
    cache: dict[int, tuple[float, list[str]]] = {}

    @app.get("/term/{ports_spec}")
    async def term_page(ports_spec: str) -> HTMLResponse:
        """One tab per port. `ports_spec` is either '7681' or '7681,7691,7692'."""
        port_list: list[int] = []
        for raw in ports_spec.split(","):
            raw = raw.strip()
            if not raw.isdigit():
                raise HTTPException(400, f"invalid port: {raw!r}")
            port = int(raw)
            if ports and port not in ports:
                raise HTTPException(404, f"port {port} not in config")
            port_list.append(port)
        if not port_list:
            raise HTTPException(400, "no ports given")
        html = TEMPLATE.replace("__PORTS__", json.dumps(port_list))
        # Backward-compat: single-port pages historically also substituted
        # __PORT__. Leaving that supported costs nothing and helps anyone
        # who's edited the template for a single-port setup.
        html = html.replace("__PORT__", str(port_list[0]))
        return HTMLResponse(html)

    @app.get("/api/term/history")
    async def term_history(port: int) -> dict:
        if port not in ports:
            return {"commands": [], "cached": False}
        now = time.time()
        if hit := cache.get(port):
            if now - hit[0] < CACHE_TTL:
                return {"commands": hit[1], "cached": True}
        source = ports[port].get("history") or {}
        text = await read_history(source)
        commands = rank_commands(text)
        cache[port] = (now, commands)
        return {"commands": commands, "cached": False}

    @app.post("/api/term/kill")
    async def term_kill(session: str) -> dict:
        """Kill a local tmux session by name. Used by the page's `×` button
        on user-spawned tabs so closed claudes don't pile up as zombies.
        Rejects names that aren't [a-zA-Z0-9_-] (sanitization against
        command injection through whatever calls this endpoint).
        Refuses to kill names in a small reserved set so the page can't
        accidentally nuke the user's main session."""
        if not session or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in session):
            raise HTTPException(400, "invalid session name")
        if session in {"claude", "main", "default"}:
            raise HTTPException(403, "refusing to kill reserved session")
        proc = await asyncio.create_subprocess_exec(
            "tmux", "kill-session", "-t", session,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        _, err = await proc.communicate()
        return {"killed": proc.returncode == 0,
                "session": session,
                "error": err.decode().strip() or None}

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"ok": True, "ports": sorted(ports)}

    return app


def main() -> None:
    p = argparse.ArgumentParser(prog="mttyd")
    p.add_argument("--config", default=os.environ.get("MTTYD_CONFIG"),
                   help="Path to ports YAML config")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8080)
    args = p.parse_args()

    import uvicorn
    uvicorn.run(create_app(args.config), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
