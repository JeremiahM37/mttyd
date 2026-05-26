"""Endpoint behavior — port whitelist, history shape, HTML hooks."""
import textwrap
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mttyd.server import create_app


@pytest.fixture
def app_with_history(tmp_path: Path):
    hist = tmp_path / ".bash_history"
    hist.write_text("git status\ngit status\ngit pull\nls -la\n")
    config = tmp_path / "mttyd.yaml"
    config.write_text(textwrap.dedent(f"""
        ports:
          7681:
            history: {{ file: {hist} }}
    """))
    return create_app(str(config))


def test_term_page_serves_html_with_xterm_and_keyboard_fix(app_with_history):
    client = TestClient(app_with_history)
    r = client.get("/term/7681")
    assert r.status_code == 200
    body = r.text
    assert "@xterm/xterm" in body                  # xterm.js loaded
    assert "const PORT = 7681" in body             # template substitution
    assert "send('{'" in body                      # correct ttyd auth opcode
    assert "xterm-helper-textarea" in body         # Gboard duplicate-word fix
    assert "autocorrect: 'off'" in body            # ...same fix (in HELPER_ATTRS dict)
    assert "MutationObserver" in body              # observer keeps Gboard attrs locked


def test_term_page_has_smooth_pointer_scroll(app_with_history):
    # Smooth scroll via Pointer Events + setPointerCapture. Without this,
    # mobile scroll is choppy and sometimes drops events.
    client = TestClient(app_with_history)
    body = client.get("/term/7681").text
    assert "setPointerCapture" in body
    assert "pointerdown" in body and "pointermove" in body and "pointerup" in body
    assert "requestAnimationFrame" in body         # momentum/inertia step
    assert "FRICTION" in body                      # friction-based decay


def test_term_page_prevents_pull_to_refresh(app_with_history):
    # touch-action: none on body stops the browser from interpreting a
    # drag-down as pull-to-refresh, which otherwise reloads the page the
    # moment the user tries to scroll. overscroll-behavior: none doubles up
    # for older browsers that don't honor touch-action: none in this context.
    client = TestClient(app_with_history)
    body = client.get("/term/7681").text
    assert "touch-action: none" in body
    assert "overscroll-behavior: none" in body


def test_term_page_has_keybar_with_essentials(app_with_history):
    # Bottom key bar covers what phone keyboards either lack or hide:
    # arrows for TUI navigation, Tab for completion, Esc to back out,
    # ^C to interrupt running commands.
    client = TestClient(app_with_history)
    body = client.get("/term/7681").text
    assert 'id="keybar"' in body
    # arrow escape sequences (ESC [ A/B/C/D)
    assert "x1b[A" in body and "x1b[B" in body
    assert "x1b[C" in body and "x1b[D" in body
    # Tab + Esc + Ctrl-C
    assert r'data-seq="\t"' in body
    assert r'data-seq="\x1b"' in body
    assert r'data-seq="\x03"' in body
    # handler that wires button clicks to send()
    assert "querySelectorAll('.keybtn')" in body


def test_term_page_does_not_reintroduce_old_broken_hacks(app_with_history):
    # Old wireTouchScroll() with manual scrollLines was glitchy. Old
    # !important touch-action on .xterm-viewport / .xterm-screen fought
    # xterm.js's own mobile handling. Both replaced by the pointer-events
    # approach above — make sure they don't sneak back.
    client = TestClient(app_with_history)
    body = client.get("/term/7681").text
    assert "wireTouchScroll" not in body
    assert ".xterm-viewport" not in body           # no custom CSS targeting it
    assert ".xterm-screen" not in body             # ...or this


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
