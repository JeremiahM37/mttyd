"""Endpoint behavior — port whitelist, history shape, HTML hooks."""
import textwrap
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from phonetty.server import create_app


@pytest.fixture
def app_with_history(tmp_path: Path):
    hist = tmp_path / ".bash_history"
    hist.write_text("git status\ngit status\ngit pull\nls -la\n")
    config = tmp_path / "phonetty.yaml"
    config.write_text(textwrap.dedent(f"""
        ports:
          7681:
            history: {{ file: {hist} }}
    """))
    return create_app(str(config))


def test_term_page_serves_html_with_xterm_and_command_bar(app_with_history):
    client = TestClient(app_with_history)
    r = client.get("/term/7681")
    assert r.status_code == 200
    body = r.text
    # The four behaviors we cant easily test in headless: prove they're at
    # least wired into the page so a future refactor cant silently strip them.
    assert "@xterm/xterm" in body            # xterm.js loaded
    assert "wireTouchScroll" in body         # mobile touch-scroll handler
    assert "cmdSuggest" in body              # custom suggestion dropdown
    assert 'autocomplete="off"' in body      # Gboard duplicate-word fix
    assert "const PORT = 7681" in body       # template substitution worked


def test_unknown_port_returns_404(app_with_history):
    client = TestClient(app_with_history)
    assert client.get("/term/9999").status_code == 404


def test_history_endpoint_returns_ranked_commands(app_with_history):
    client = TestClient(app_with_history)
    r = client.get("/api/term/history?port=7681")
    assert r.status_code == 200
    body = r.json()
    assert body["commands"][0] == "git status"   # most frequent
    assert "ls -la" in body["commands"]


def test_history_caches_second_call(app_with_history):
    client = TestClient(app_with_history)
    assert client.get("/api/term/history?port=7681").json()["cached"] is False
    assert client.get("/api/term/history?port=7681").json()["cached"] is True


def test_history_for_unknown_port_is_empty(app_with_history):
    client = TestClient(app_with_history)
    assert client.get("/api/term/history?port=9999").json()["commands"] == []


def test_healthz_lists_configured_ports(app_with_history):
    client = TestClient(app_with_history)
    body = client.get("/healthz").json()
    assert body["ok"] is True
    assert body["ports"] == [7681]


def test_empty_config_allows_any_port():
    app = create_app(None)
    client = TestClient(app)
    # No port whitelist → /term/{port} always 200, but history is empty.
    assert client.get("/term/12345").status_code == 200
    assert client.get("/api/term/history?port=12345").json()["commands"] == []
