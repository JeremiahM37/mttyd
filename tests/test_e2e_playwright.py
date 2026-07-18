"""End-to-end browser tests for the mttyd terminal UI.

These drive a headless Chromium (via pytest-playwright) against a *real*
mttyd FastAPI server started on an ephemeral port. They mirror — and extend —
the intent of `.verify.yaml`'s headless-Chromium UI checks, but as committed,
runnable Playwright assertions so the "Playwright e2e tests" claim is true.

Run them with::

    pip install -e '.[e2e]'
    playwright install chromium
    pytest -m e2e                          # the whole e2e suite
    pytest -m e2e tests/test_e2e_playwright.py   # just this file

They are tagged with the ``e2e`` marker and are *deselected by default*
(see ``addopts`` in pyproject.toml) so the plain unit suite — and the
``.verify.yaml`` ``pytest -q`` step — stays fast and network-independent.

A throwaway WebSocket server stands in for ttyd on the configured port so the
page's per-tab WebSocket reaches OPEN/CONNECTING, letting the regression guard
assert real connection state. xterm.js and its addons are vendored into the
package and served by mttyd itself, so no internet connection is needed once
the Chromium browser has been installed.
"""
from __future__ import annotations

import asyncio
import socket
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest
import urllib.request
import urllib.error

# Skip the whole module cleanly if the optional e2e deps aren't installed,
# rather than erroring out collection for someone running just the unit suite.
pytest.importorskip("playwright.sync_api")
websockets = pytest.importorskip("websockets")

pytestmark = pytest.mark.e2e

REPO_ROOT = Path(__file__).resolve().parent.parent


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def ttyd_stub():
    """A minimal ttyd stand-in: a WebSocket server speaking the 'tty'
    subprotocol on a fixed port. The page connects to ws://127.0.0.1:<port>/ws;
    this just accepts the handshake (and drains messages) so the client-side
    WebSocket reaches OPEN instead of failing fast against a dead port.
    Yields the port it listens on."""
    port = _free_port()
    ready = threading.Event()
    holder: dict[str, object] = {}

    async def _handler(websocket):
        try:
            async for _ in websocket:  # drain client frames; never reply
                pass
        except Exception:
            pass

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def _serve():
            stop_evt = asyncio.Event()
            holder["loop"] = loop
            holder["stop"] = stop_evt
            async with websockets.serve(
                _handler, "127.0.0.1", port, subprotocols=["tty"]
            ):
                ready.set()
                await stop_evt.wait()  # run until torn down

        try:
            loop.run_until_complete(_serve())
        finally:
            ready.set()
            loop.close()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    assert ready.wait(timeout=10), "ttyd WebSocket stub failed to start"
    yield port

    loop = holder.get("loop")
    stop_evt = holder.get("stop")
    if loop and stop_evt:
        loop.call_soon_threadsafe(stop_evt.set)
    t.join(timeout=5)


@pytest.fixture(scope="session")
def mttyd_server(tmp_path_factory, ttyd_stub):
    """Start the real mttyd FastAPI app under uvicorn on an ephemeral port,
    with a temp config whose allowlist includes the stub ttyd port.
    Yields (base_url, ttyd_port)."""
    ttyd_port = ttyd_stub
    cfg_dir = tmp_path_factory.mktemp("mttyd_cfg")
    hist = cfg_dir / ".bash_history"
    hist.write_text("git status\ngit status\nls -la\n")
    config = cfg_dir / "mttyd.yaml"
    config.write_text(
        textwrap.dedent(
            f"""
            ports:
              {ttyd_port}:
                history: {{ file: {hist} }}
            """
        )
    )

    http_port = _free_port()
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "mttyd.server:create_app",
            "--factory",
            "--host", "127.0.0.1",
            "--port", str(http_port),
        ],
        cwd=str(REPO_ROOT),
        env={"MTTYD_CONFIG": str(config), "PATH": _path_env()},
    )

    base_url = f"http://127.0.0.1:{http_port}"
    deadline = time.time() + 30
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"mttyd server exited early ({proc.returncode})")
        try:
            with urllib.request.urlopen(base_url + "/healthz", timeout=1) as r:
                if r.status == 200:
                    break
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.2)
    else:
        proc.kill()
        raise RuntimeError("mttyd server did not become ready in time")

    yield base_url, ttyd_port

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def _path_env() -> str:
    import os
    return os.environ.get("PATH", "")


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Force a phone-sized viewport (mirrors .verify.yaml's 414x896)."""
    return {**browser_context_args, "viewport": {"width": 414, "height": 896}}


# ──────────────────────────────────────────────────────────────────────────


def test_term_page_loads_and_renders_xterm(page, mttyd_server):
    """200 + HTML contains createSession, and an .xterm canvas mounts."""
    base_url, port = mttyd_server
    resp = page.goto(f"{base_url}/term/{port}")
    assert resp is not None and resp.status == 200
    assert "createSession" in page.content()
    page.wait_for_selector(".xterm", timeout=10_000)
    assert page.locator(".xterm").first.is_visible()


def test_single_session_and_tab_api_present(page, mttyd_server):
    """Exactly one session boots, and the tab-management API is wired up
    (matches `() => sessions.length === 1` and `typeof active === 'function'`)."""
    base_url, port = mttyd_server
    page.goto(f"{base_url}/term/{port}")
    page.wait_for_selector(".xterm", timeout=10_000)
    assert page.evaluate("() => sessions.length") == 1
    assert page.evaluate("() => typeof active") == "function"
    assert page.evaluate("() => typeof createSession") == "function"
    assert page.evaluate("() => typeof setActive") == "function"


def test_toolbar_buttons_visible(page, mttyd_server):
    """The interactive control buttons render and are visible on mobile."""
    base_url, port = mttyd_server
    page.goto(f"{base_url}/term/{port}")
    page.wait_for_selector(".xterm", timeout=10_000)
    for sel in ("#tabAdd", "#searchBtn", "#copyBtn", "#pasteBtn", "#histBtn", "#settingsBtn"):
        assert page.locator(sel).is_visible(), f"{sel} not visible"


def test_multi_port_url_substitution(page, mttyd_server):
    """A comma-separated /term/<p>,<p> URL yields a PORTS array of length 2."""
    base_url, port = mttyd_server
    resp = page.goto(f"{base_url}/term/{port},{port}")
    assert resp is not None and resp.status == 200
    assert f"const PORTS = [{port}, {port}]" in page.content()
    page.wait_for_selector(".xterm", timeout=10_000)
    assert page.evaluate("() => PORTS.length") == 2


def test_invalid_port_path_returns_400(page, mttyd_server):
    """A non-numeric port path is rejected with HTTP 400."""
    base_url, _ = mttyd_server
    resp = page.goto(f"{base_url}/term/notaport")
    assert resp is not None and resp.status == 400


def test_page_init_no_infinite_loop_regression(page, mttyd_server):
    """Regression guard for the lockHelperAttrs / MutationObserver infinite
    loop (the project's signature bug): the page returned 200 with correct
    HTML, but the JS pinned the event loop before term.open() could run.

    Assert the loop is healthy: `sessions` declared, a live ws on session 0
    in OPEN/CONNECTING state, and a 250ms timer that resolves well under 600ms
    (a CPU-pinned event loop would block it for much longer)."""
    base_url, port = mttyd_server
    page.goto(f"{base_url}/term/{port}")
    page.wait_for_selector(".xterm", timeout=6_000)

    state = page.evaluate(
        """() => {
            if (typeof sessions === 'undefined')
              return { ok:false, detail:'sessions never declared — JS hung before tab init' };
            if (sessions.length < 1) return { ok:false, detail:'sessions.length=0' };
            const ws = sessions[0].ws;
            if (!ws) return { ok:false, detail:'no ws on session 0' };
            if (ws.readyState !== 1 && ws.readyState !== 0)
              return { ok:false, detail:`ws.readyState=${ws.readyState} (expected OPEN or CONNECTING)` };
            return { ok:true };
        }"""
    )
    assert state["ok"], state.get("detail")

    # The 250ms timer must fire promptly — a busy loop would block setTimeout.
    timing = page.evaluate(
        """() => {
            const t0 = performance.now();
            return new Promise(res => {
              setTimeout(() => {
                const dt = performance.now() - t0;
                res(dt < 600
                  ? { ok:true, dt }
                  : { ok:false, detail:`event loop stalled: 250ms timer took ${dt|0}ms` });
              }, 250);
            });
        }"""
    )
    assert timing["ok"], timing.get("detail")
