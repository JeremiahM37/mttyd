"""Phonetty HTTP server.

Serves two things:
  GET /term/{port}            HTML wrapper that connects xterm.js to ttyd at PORT
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
    app = FastAPI(title="phonetty", version="0.1.0")
    ports = load_config(config_path)
    cache: dict[int, tuple[float, list[str]]] = {}

    @app.get("/term/{port}")
    async def term_page(port: int) -> HTMLResponse:
        if ports and port not in ports:
            raise HTTPException(404, "port not in config")
        return HTMLResponse(TEMPLATE.replace("__PORT__", str(port)))

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

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"ok": True, "ports": sorted(ports)}

    return app


def main() -> None:
    p = argparse.ArgumentParser(prog="phonetty")
    p.add_argument("--config", default=os.environ.get("PHONETTY_CONFIG"),
                   help="Path to ports YAML config")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8080)
    args = p.parse_args()

    import uvicorn
    uvicorn.run(create_app(args.config), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
